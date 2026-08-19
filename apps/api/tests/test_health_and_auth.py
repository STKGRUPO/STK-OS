from fastapi.testclient import TestClient


def test_liveness_returns_version_and_correlation(client: TestClient) -> None:
    response = client.get("/health/live", headers={"X-Correlation-ID": "invalid"})
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert len(response.headers["X-Correlation-ID"]) == 36


def test_readiness_uses_database(client: TestClient) -> None:
    response = client.get("/health/ready")
    assert response.status_code == 200
    assert response.json() == {"status": "ready", "database": "ok"}


def test_user_login_rejects_wrong_password(client: TestClient) -> None:
    response = client.post(
        "/api/v1/auth/token",
        json={"email": "admin@example.test", "password": "wrong-password-value"},
    )
    assert response.status_code == 401
    assert "access_token" not in response.text


def test_protected_route_requires_token(client: TestClient) -> None:
    assert client.get("/api/v1/organization").status_code == 401
