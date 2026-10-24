
import json
from pathlib import Path
from fastapi.responses import FileResponse
from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    UploadFile,
    File,
    Form,
    Request,
)
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from psycopg.types.json import Jsonb

from services.db import get_db_connection
from services.auth import decode_access_token
from services.documents import save_uploaded_file

router = APIRouter(prefix="/documents", tags=["Documents"])
security = HTTPBearer()


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
):
    try:
        claims = decode_access_token(credentials.credentials)
        user_id = int(claims["sub"])
    except Exception:
        raise HTTPException(
            status_code=401,
            detail="Invalid or expired authentication token",
        )

    with get_db_connection() as connection:
        user = connection.execute(
            """
            SELECT id, full_name, email, role, is_active
            FROM users
            WHERE id = %s
            """,
            (user_id,),
        ).fetchone()

    if not user or not user["is_active"]:
        raise HTTPException(
            status_code=401,
            detail="User account is unavailable",
        )

    return user


def record_audit(
    connection,
    actor_id: int,
    action: str,
    outcome: str,
    document_id: int | None = None,
    details: dict | None = None,
    ip_address: str | None = None,
):
    connection.execute(
        """
        INSERT INTO audit_logs (
            actor_id, action, outcome, document_id,
            details, ip_address
        )
        VALUES (%s, %s, %s, %s, %s, %s)
        """,
        (
            actor_id,
            action,
            outcome,
            document_id,
            Jsonb(details or {}),
            ip_address,
        ),
    )


@router.get("/")
def list_documents(user=Depends(get_current_user)):
    """List documents owned by the authenticated user."""
    with get_db_connection() as connection:
        documents = connection.execute(
            """
            SELECT id, title, original_filename, category,
                   owner_id, file_size, content_type,
                   created_at, updated_at
            FROM documents
            WHERE owner_id = %s
            ORDER BY created_at DESC
            """,
            (user["id"],),
        ).fetchall()

    return {"documents": documents}


@router.post("/upload", status_code=201)
async def upload_document(
    request: Request,
    title: str = Form(..., min_length=1, max_length=255),
    category: str = Form(default="General", max_length=100),
    file: UploadFile = File(...),
    user=Depends(get_current_user),
):
    """Upload a private document and save its metadata."""
    title = title.strip()
    if not title:
        raise HTTPException(status_code=400, detail="Title is required")

    saved_file = await save_uploaded_file(file)
    storage_path = Path(saved_file["storage_path"])

    try:
        with get_db_connection() as connection:
            document = connection.execute(
                """
                INSERT INTO documents (
                    title, original_filename, storage_path,
                    category, owner_id, file_size, content_type
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                RETURNING id, title, original_filename, category,
                          owner_id, file_size, content_type,
                          created_at, updated_at
                """,
                (
                    title,
                    saved_file["original_filename"],
                    str(storage_path),
                    category.strip() or "General",
                    user["id"],
                    saved_file["file_size"],
                    saved_file["content_type"],
                ),
            ).fetchone()

            record_audit(
                connection=connection,
                actor_id=user["id"],
                action="document_upload",
                outcome="success",
                document_id=document["id"],
                details={"filename": saved_file["original_filename"]},
                ip_address=(
                    request.client.host if request.client else None
                ),
            )

        return {"document": document}

    except Exception:
        storage_path.unlink(missing_ok=True)
        raise
@router.get("/{document_id}/download")
def download_document(
    document_id: int,
    request: Request,
    user=Depends(get_current_user),
):
    """Download a document only if the user is allowed to read it."""

    with get_db_connection() as connection:
        document = connection.execute(
            """
            SELECT d.id, d.title, d.original_filename, d.storage_path,
                   d.owner_id
            FROM documents d
            WHERE d.id = %s
            """,
            (document_id,),
        ).fetchone()

        if not document:
            record_audit(
                connection=connection,
                actor_id=user["id"],
                action="document_download",
                outcome="denied",
                document_id=None,
                details={"requested_document_id": document_id},
                ip_address=request.client.host if request.client else None,
            )
            raise HTTPException(status_code=404, detail="Document not found")

        permission = connection.execute(
            """
            SELECT can_read
            FROM document_permissions
            WHERE document_id = %s AND user_id = %s
            """,
            (document_id, user["id"]),
        ).fetchone()

        allowed = (
            user["role"] == "admin"
            or document["owner_id"] == user["id"]
            or (permission is not None and permission["can_read"])
        )

        if not allowed:
            record_audit(
                connection=connection,
                actor_id=user["id"],
                action="document_download",
                outcome="denied",
                document_id=document_id,
                ip_address=request.client.host if request.client else None,
            )
            raise HTTPException(status_code=403, detail="Access denied")

        storage_path = Path(document["storage_path"]).resolve()
        upload_root = (Path(__file__).resolve().parent.parent / "private_uploads").resolve()

        if not storage_path.is_relative_to(upload_root) or not storage_path.is_file():
            raise HTTPException(status_code=404, detail="Stored file not found")

        record_audit(
            connection=connection,
            actor_id=user["id"],
            action="document_download",
            outcome="success",
            document_id=document_id,
            ip_address=request.client.host if request.client else None,
        )

    return FileResponse(
        path=storage_path,
        filename=document["original_filename"],
    )
@router.put("/{document_id}/permissions/{target_user_id}")
def grant_document_permission(
    document_id: int,
    target_user_id: int,
    can_read: bool = Form(...),
    can_edit: bool = Form(False),
    request: Request = None,
    user=Depends(get_current_user),
):
    """Grant or update document access. Only the owner or admin can do this."""
    if can_edit and not can_read:
        raise HTTPException(
            status_code=400,
            detail="Edit permission requires read permission",
        )

    with get_db_connection() as connection:
        document = connection.execute(
            "SELECT id, owner_id FROM documents WHERE id = %s",
            (document_id,),
        ).fetchone()

        if not document:
            raise HTTPException(status_code=404, detail="Document not found")

        if user["role"] != "admin" and document["owner_id"] != user["id"]:
            record_audit(
                connection=connection,
                actor_id=user["id"],
                action="permission_grant",
                outcome="denied",
                document_id=document_id,
                details={"target_user_id": target_user_id},
                ip_address=request.client.host if request and request.client else None,
            )
            raise HTTPException(status_code=403, detail="Only the owner or admin can grant access")

        target = connection.execute(
            "SELECT id FROM users WHERE id = %s AND is_active = TRUE",
            (target_user_id,),
        ).fetchone()

        if not target:
            raise HTTPException(status_code=404, detail="Target user not found")

        permission = connection.execute(
            """
            INSERT INTO document_permissions
                (document_id, user_id, can_read, can_edit, granted_by)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (document_id, user_id)
            DO UPDATE SET
                can_read = EXCLUDED.can_read,
                can_edit = EXCLUDED.can_edit,
                granted_by = EXCLUDED.granted_by,
                granted_at = NOW()
            RETURNING document_id, user_id, can_read, can_edit, granted_by, granted_at
            """,
            (document_id, target_user_id, can_read, can_edit, user["id"]),
        ).fetchone()

        record_audit(
            connection=connection,
            actor_id=user["id"],
            action="permission_grant",
            outcome="success",
            document_id=document_id,
            details={
                "target_user_id": target_user_id,
                "can_read": can_read,
                "can_edit": can_edit,
            },
            ip_address=request.client.host if request and request.client else None,
        )

    return {"permission": permission}


@router.delete("/{document_id}/permissions/{target_user_id}")
def revoke_document_permission(
    document_id: int,
    target_user_id: int,
    request: Request,
    user=Depends(get_current_user),
):
    """Revoke document access. Only the owner or admin can do this."""
    with get_db_connection() as connection:
        document = connection.execute(
            "SELECT id, owner_id FROM documents WHERE id = %s",
            (document_id,),
        ).fetchone()

        if not document:
            raise HTTPException(status_code=404, detail="Document not found")

        if user["role"] != "admin" and document["owner_id"] != user["id"]:
            record_audit(
                connection=connection,
                actor_id=user["id"],
                action="permission_revoke",
                outcome="denied",
                document_id=document_id,
                details={"target_user_id": target_user_id},
                ip_address=request.client.host if request.client else None,
            )
            raise HTTPException(status_code=403, detail="Only the owner or admin can revoke access")

        deleted = connection.execute(
            """
            DELETE FROM document_permissions
            WHERE document_id = %s AND user_id = %s
            RETURNING user_id
            """,
            (document_id, target_user_id),
        ).fetchone()

        if not deleted:
            raise HTTPException(status_code=404, detail="Permission not found")

        record_audit(
            connection=connection,
            actor_id=user["id"],
            action="permission_revoke",
            outcome="success",
            document_id=document_id,
            details={"target_user_id": target_user_id},
            ip_address=request.client.host if request.client else None,
        )

    return {"message": "Document permission revoked"}
@router.get("/search")
def search_documents(
    q: str = "",
    category: str | None = None,
    user=Depends(get_current_user),
):
    """Search documents accessible to the authenticated user."""
    conditions = [
        """
        (
            d.owner_id = %s
            OR EXISTS (
                SELECT 1
                FROM document_permissions p
                WHERE p.document_id = d.id
                  AND p.user_id = %s
                  AND p.can_read = TRUE
            )
        )
        """
    ]
    params = [user["id"], user["id"]]

    if q.strip():
        conditions.append(
            "(d.title ILIKE %s OR d.original_filename ILIKE %s)"
        )
        search_term = f"%{q.strip()}%"
        params.extend([search_term, search_term])

    if category and category.strip():
        conditions.append("d.category ILIKE %s")
        params.append(category.strip())

    query = f"""
        SELECT d.id, d.title, d.original_filename, d.category,
               d.owner_id, d.file_size, d.content_type,
               d.created_at, d.updated_at
        FROM documents d
        WHERE {" AND ".join(conditions)}
        ORDER BY d.created_at DESC
        LIMIT 100
    """

    with get_db_connection() as connection:
        documents = connection.execute(query, params).fetchall()

    return {"documents": documents}