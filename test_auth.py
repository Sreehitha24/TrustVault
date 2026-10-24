
import uuid

import pytest
from fastapi.testclient import TestClient

from main import app
from services.auth import (
    hash_password,
    verify_password,
    create_access_token,
    decode_access_token,
)


def test_password_hashing():
    password = "TestPass123!"
    hashed = hash_password(password)

    assert hashed != password
    assert verify_password(password, hashed)


def test_wrong_password_rejected():
    hashed = hash_password("TestPass123!")

    assert not verify_password("WrongPass123!", hashed)


def test_access_token_valid():
    token = create_access_token(1, "owner")
    claims = decode_access_token(token)

    assert claims["sub"] == "1"
    assert claims["role"] == "owner"
    assert "jti" in claims
    assert "exp" in claims


def test_invalid_token_rejected():
    with pytest.raises(Exception):
        decode_access_token("this.is.not-a-valid-token")


def test_register_and_login():
    email = f"test-{uuid.uuid4().hex}@example.com"
    password = "TestPass123!Secure"

    with TestClient(app) as client:
        register_response = client.post(
            "/auth/register",
            json={
                "full_name": "Automated Test Owner",
                "email": email,
                "password": password,
            },
        )

        assert register_response.status_code == 201

        registered_user = register_response.json()["user"]
        assert registered_user["email"] == email
        assert registered_user["role"] == "owner"
        assert "password_hash" not in registered_user

        login_response = client.post(
            "/auth/login",
            json={"email": email, "password": password},
        )

        assert login_response.status_code == 200

        login_data = login_response.json()
        assert login_data["token_type"] == "bearer"
        assert login_data["user"]["email"] == email
        assert login_data["user"]["role"] == "owner"
        assert decode_access_token(login_data["access_token"])["sub"] == str(
            registered_user["id"]
        )


def test_login_wrong_password_rejected():
    email = f"test-{uuid.uuid4().hex}@example.com"
    password = "TestPass123!Secure"

    with TestClient(app) as client:
        register_response = client.post(
            "/auth/register",
            json={
                "full_name": "Automated Test Owner",
                "email": email,
                "password": password,
            },
        )

        assert register_response.status_code == 201

        login_response = client.post(
            "/auth/login",
            json={"email": email, "password": "WrongPassword123!"},
        )

        assert login_response.status_code == 401
        assert login_response.json()["detail"] == "Invalid email or password"
