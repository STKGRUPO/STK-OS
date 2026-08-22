import pytest
from conftest import LAB_UNIT_ID, UNIT_ID
from fastapi.testclient import TestClient
from sqlalchemy import delete, select
from sqlalchemy.orm import Session, sessionmaker

from stk_os.models import Actor, ActorRole, Organization, Permission, Role, RolePermission, User
from stk_os.routers.auth import registration_rate_limiter
from stk_os.security import hash_secret


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


def test_user_profile_and_multiple_units_can_be_updated(
    client: TestClient, admin_headers: dict[str, str]
) -> None:
    roles = client.get("/api/v1/auth/roles", headers=admin_headers).json()
    standard = next(item for item in roles if item["code"] == "user")
    invited = client.post(
        "/api/v1/auth/users/invite",
        headers=admin_headers,
        json={
            "email": "scoped.user@example.test",
            "display_name": "Usuário com escopo",
            "role_id": standard["id"],
            "business_unit_ids": [str(UNIT_ID)],
        },
    )
    assert invited.status_code == 201, invited.text

    updated = client.patch(
        f"/api/v1/auth/users/{invited.json()['user']['id']}/access",
        headers=admin_headers,
        json={
            "role_id": standard["id"],
            "business_unit_ids": [str(UNIT_ID), str(LAB_UNIT_ID)],
        },
    )
    assert updated.status_code == 200, updated.text
    assert [role["code"] for role in updated.json()["roles"]] == ["user"]
    assert set(updated.json()["business_unit_ids"]) == {str(UNIT_ID), str(LAB_UNIT_ID)}


def test_scoped_profile_requires_units_and_group_admin_is_organization_wide(
    client: TestClient, admin_headers: dict[str, str]
) -> None:
    roles = client.get("/api/v1/auth/roles", headers=admin_headers).json()
    standard = next(item for item in roles if item["code"] == "user")
    administrator = next(item for item in roles if item["code"] == "administrator")

    missing_scope = client.post(
        "/api/v1/auth/users/invite",
        headers=admin_headers,
        json={
            "email": "missing.scope@example.test",
            "display_name": "Sem escopo",
            "role_id": standard["id"],
            "business_unit_ids": [],
        },
    )
    invalid_admin_scope = client.post(
        "/api/v1/auth/users/invite",
        headers=admin_headers,
        json={
            "email": "admin.scope@example.test",
            "display_name": "Admin com escopo inválido",
            "role_id": administrator["id"],
            "business_unit_ids": [str(UNIT_ID)],
        },
    )
    assert missing_scope.status_code == 422
    assert invalid_admin_scope.status_code == 422


def test_last_active_group_admin_cannot_lose_profile(
    client: TestClient, admin_headers: dict[str, str]
) -> None:
    roles = client.get("/api/v1/auth/roles", headers=admin_headers).json()
    standard = next(item for item in roles if item["code"] == "user")
    users = client.get("/api/v1/auth/users", headers=admin_headers).json()
    administrator = next(user for user in users if user["email"] == "admin@example.test")

    response = client.patch(
        f"/api/v1/auth/users/{administrator['id']}/access",
        headers=admin_headers,
        json={"role_id": standard["id"], "business_unit_ids": [str(UNIT_ID)]},
    )
    assert response.status_code == 409
    assert "último Administrador do Grupo ativo" in response.json()["detail"]


def test_last_active_group_admin_cannot_be_deactivated_by_another_manager(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    with session_factory() as session, session.begin():
        organization = session.scalar(select(Organization))
        permission = session.scalar(select(Permission).where(Permission.code == "identity:manage"))
        manager_role = Role(
            organization_id=organization.id,
            code="identity_manager_test",
            name="Gestor de identidade de teste",
        )
        manager_actor = Actor(
            organization_id=organization.id,
            kind="user",
            display_name="Gestor de identidade",
        )
        session.add_all([manager_role, manager_actor])
        session.flush()
        session.add_all(
            [
                RolePermission(role_id=manager_role.id, permission_id=permission.id),
                ActorRole(
                    actor_id=manager_actor.id,
                    role_id=manager_role.id,
                    business_unit_id=UNIT_ID,
                ),
                User(
                    actor_id=manager_actor.id,
                    email="identity.manager@example.test",
                    password_hash=hash_secret("identity-manager-password-001"),
                ),
            ]
        )

    login = client.post(
        "/api/v1/auth/token",
        json={
            "email": "identity.manager@example.test",
            "password": "identity-manager-password-001",
        },
    )
    manager_headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    users = client.get("/api/v1/auth/users", headers=manager_headers).json()
    administrator = next(user for user in users if user["email"] == "admin@example.test")
    response = client.patch(
        f"/api/v1/auth/users/{administrator['id']}/deactivate",
        headers=manager_headers,
    )
    assert response.status_code == 409
    assert "último Administrador do Grupo ativo" in response.json()["detail"]


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


def test_public_registration_uses_existing_inactive_organization(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    with session_factory() as session, session.begin():
        organization = session.query(Organization).one()
        organization.status = "inactive"
        session.execute(delete(Role).where(Role.code == "user"))

    created = client.post(
        "/api/v1/auth/password/define",
        json={
            "email": "inactive.organization@example.test",
            "password": "inactive-organization-password-001",
        },
    )
    assert created.status_code == 200, created.text


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
