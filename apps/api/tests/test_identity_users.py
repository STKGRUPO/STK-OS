from fastapi.testclient import TestClient


def test_secure_invitation_first_access_reset_and_deactivation(
    client: TestClient, admin_headers: dict[str, str]
) -> None:
    roles = client.get("/api/v1/auth/roles", headers=admin_headers)
    assert roles.status_code == 200
    administrator = next(item for item in roles.json() if item["code"] == "administrator")
    assert "identity:manage" in administrator["capabilities"]

    invited = client.post(
        "/api/v1/auth/users/invite",
        headers=admin_headers,
        json={
            "email": "new.user@example.test",
            "display_name": "Usuário convidado sintético",
            "role_id": administrator["id"],
            "business_unit_ids": [],
        },
    )
    assert invited.status_code == 201, invited.text
    assert invited.json()["user"]["status"] == "disabled"
    assert invited.json()["user"]["first_access_completed"] is False
    assert len(invited.json()["token"]) >= 32

    denied = client.post(
        "/api/v1/auth/token",
        json={"email": "new.user@example.test", "password": "new-user-password-001"},
    )
    assert denied.status_code == 401

    defined = client.post(
        "/api/v1/auth/password/define",
        json={"token": invited.json()["token"], "password": "new-user-password-001"},
    )
    assert defined.status_code == 200
    assert (
        client.post(
            "/api/v1/auth/password/define",
            json={"token": invited.json()["token"], "password": "cannot-reuse-token-001"},
        ).status_code
        == 400
    )

    login = client.post(
        "/api/v1/auth/token",
        json={"email": "new.user@example.test", "password": "new-user-password-001"},
    )
    assert login.status_code == 200
    user_headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    me = client.get("/api/v1/auth/me", headers=user_headers)
    assert me.status_code == 200
    assert me.json()["first_access_completed"] is True
    assert "services:read" in me.json()["capabilities"]

    reset = client.post(
        f"/api/v1/auth/users/{invited.json()['user']['id']}/password-reset",
        headers=admin_headers,
    )
    assert reset.status_code == 200
    assert reset.json()["purpose"] == "password_reset"
    assert (
        client.post(
            "/api/v1/auth/password/define",
            json={"token": reset.json()["token"], "password": "new-user-password-002"},
        ).status_code
        == 200
    )

    deactivated = client.patch(
        f"/api/v1/auth/users/{invited.json()['user']['id']}/deactivate",
        headers=admin_headers,
    )
    assert deactivated.status_code == 200
    assert deactivated.json()["status"] == "disabled"
    assert (
        client.post(
            "/api/v1/auth/token",
            json={"email": "new.user@example.test", "password": "new-user-password-002"},
        ).status_code
        == 401
    )


def test_public_password_reset_does_not_disclose_accounts_or_tokens(client: TestClient) -> None:
    existing = client.post(
        "/api/v1/auth/password-reset/request", json={"email": "admin@example.test"}
    )
    missing = client.post(
        "/api/v1/auth/password-reset/request", json={"email": "missing@example.test"}
    )
    assert existing.status_code == missing.status_code == 200
    assert existing.json() == missing.json()
    assert "token" not in existing.text.lower()
