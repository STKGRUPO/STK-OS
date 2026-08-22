import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete
from sqlalchemy.orm import Session, sessionmaker

from stk_os.models import Organization, Role
from stk_os.routers.auth import registration_rate_limiter


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
        json={
            "email": "new.user@example.test",
            "token": invited.json()["token"],
            "password": "new-user-password-001",
        },
    )
    assert defined.status_code == 200
    assert (
        client.post(
            "/api/v1/auth/password/define",
            json={
                "email": "new.user@example.test",
                "token": invited.json()["token"],
                "password": "cannot-reuse-token-001",
            },
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
            json={
                "email": "new.user@example.test",
                "token": reset.json()["token"],
                "password": "new-user-password-002",
            },
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


def test_public_self_registration_login_and_me(client: TestClient) -> None:
    created = client.post(
        "/api/v1/auth/password/define",
        json={
            "email": "self.registered@example.test",
            "password": "self-registration-password-001",
        },
    )
    assert created.status_code == 200, created.text
    assert created.json() == {"message": "Acesso criado com sucesso."}

    duplicate = client.post(
        "/api/v1/auth/password/define",
        json={
            "email": "SELF.REGISTERED@example.test",
            "password": "self-registration-password-002",
            "token": "",
        },
    )
    assert duplicate.status_code == 409
    assert duplicate.json() == {"detail": "Não foi possível criar o acesso."}

    login = client.post(
        "/api/v1/auth/token",
        json={
            "email": "self.registered@example.test",
            "password": "self-registration-password-001",
        },
    )
    assert login.status_code == 200, login.text
    me = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {login.json()['access_token']}"},
    )
    assert me.status_code == 200, me.text
    assert me.json()["status"] == "active"
    assert me.json()["first_access_completed"] is True
    assert [role["code"] for role in me.json()["roles"]] == ["user"]


def test_public_registration_repairs_missing_context(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    with session_factory() as session, session.begin():
        session.execute(delete(Role))
        session.execute(delete(Organization))

    created = client.post(
        "/api/v1/auth/password/define",
        json={
            "email": "empty.database@example.test",
            "password": "empty-database-password-001",
        },
    )
    assert created.status_code == 200, created.text

    login = client.post(
        "/api/v1/auth/token",
        json={
            "email": "empty.database@example.test",
            "password": "empty-database-password-001",
        },
    )
    assert login.status_code == 200, login.text
    me = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {login.json()['access_token']}"},
    )
    assert me.status_code == 200, me.text
    assert [role["code"] for role in me.json()["roles"]] == ["user"]


def test_public_registration_is_rate_limited(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    with registration_rate_limiter._lock:
        registration_rate_limiter._attempts.clear()
    monkeypatch.setattr(registration_rate_limiter, "max_attempts", 1)
    try:
        first = client.post(
            "/api/v1/auth/password/define",
            json={
                "email": "rate.first@example.test",
                "password": "rate-limit-password-001",
            },
        )
        limited = client.post(
            "/api/v1/auth/password/define",
            json={
                "email": "rate.second@example.test",
                "password": "rate-limit-password-002",
            },
        )
        assert first.status_code == 200, first.text
        assert limited.status_code == 429
        assert int(limited.headers["Retry-After"]) >= 1
    finally:
        with registration_rate_limiter._lock:
            registration_rate_limiter._attempts.clear()
