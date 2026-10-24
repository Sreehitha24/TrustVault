from fastapi.testclient import TestClient

from main import app


client = TestClient(app)


def test_home_endpoint():
    response = client.get("/")

    assert response.status_code == 200
    assert response.json()["app"] == "TrustVault"


def test_health_endpoint():
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_database_health_endpoint():
    response = client.get("/health/database")

    assert response.status_code == 200
    assert response.json()["database"] == "connected"