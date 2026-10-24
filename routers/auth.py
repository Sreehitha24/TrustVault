
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, EmailStr, Field
from psycopg.errors import UniqueViolation

from services.db import get_db_connection
from services.auth import (
    hash_password,
    verify_password,
    create_access_token,
)

router = APIRouter(prefix="/auth", tags=["Authentication"])


class RegisterRequest(BaseModel):
    full_name: str = Field(min_length=2, max_length=100)
    email: EmailStr
    password: str = Field(min_length=12, max_length=128)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


@router.post("/register", status_code=201)
def register(data: RegisterRequest):
    try:
        with get_db_connection() as connection:
            user = connection.execute(
                """
                INSERT INTO users (
                    full_name,
                    email,
                    password_hash,
                    role
                )
                VALUES (%s, %s, %s, 'owner')
                RETURNING id, full_name, email, role
                """,
                (
                    data.full_name.strip(),
                    data.email.lower(),
                    hash_password(data.password),
                ),
            ).fetchone()

        return {"user": user}

    except UniqueViolation:
        raise HTTPException(
            status_code=409,
            detail="Email already registered",
        )


@router.post("/login")
def login(data: LoginRequest):
    with get_db_connection() as connection:
        user = connection.execute(
            """
            SELECT
                id,
                full_name,
                email,
                password_hash,
                role,
                is_active
            FROM users
            WHERE email = %s
            """,
            (data.email.lower(),),
        ).fetchone()

    if (
        not user
        or not user["is_active"]
        or not verify_password(
            data.password,
            user["password_hash"],
        )
    ):
        raise HTTPException(
            status_code=401,
            detail="Invalid email or password",
        )

    token = create_access_token(user["id"], user["role"])

    return {
        "access_token": token,
        "token_type": "bearer",
        "user": {
            "id": user["id"],
            "full_name": user["full_name"],
            "email": user["email"],
            "role": user["role"],
        },
    }
