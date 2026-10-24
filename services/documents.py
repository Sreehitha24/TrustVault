from pathlib import Path
import os
import uuid

from fastapi import HTTPException, UploadFile

# Store uploaded files inside the project directory.
BASE_DIR = Path(__file__).resolve().parent.parent
UPLOAD_DIR = BASE_DIR / "private_uploads"

# Only allow common document formats.
ALLOWED_EXTENSIONS = {
    ".pdf",
    ".txt",
    ".docx",
    ".png",
    ".jpg",
    ".jpeg",
}

MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB


async def save_uploaded_file(file: UploadFile) -> dict:
    """Validate and save an uploaded file with a random filename."""

    original_name = Path(file.filename or "").name
    extension = Path(original_name).suffix.lower()

    if not original_name or extension not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail="Unsupported file type",
        )

    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

    stored_name = f"{uuid.uuid4().hex}{extension}"
    storage_path = UPLOAD_DIR / stored_name
    file_size = 0

    try:
        with storage_path.open("xb") as destination:
            while True:
                chunk = await file.read(1024 * 1024)

                if not chunk:
                    break

                file_size += len(chunk)

                if file_size > MAX_FILE_SIZE:
                    raise HTTPException(
                        status_code=413,
                        detail="File exceeds the 10 MB limit",
                    )

                destination.write(chunk)

        if file_size == 0:
            storage_path.unlink(missing_ok=True)
            raise HTTPException(
                status_code=400,
                detail="Empty files are not allowed",
            )

        return {
            "original_filename": original_name,
            "storage_path": str(storage_path),
            "file_size": file_size,
            "content_type": file.content_type,
        }

    except Exception:
        storage_path.unlink(missing_ok=True)
        raise

    finally:
        await file.close()