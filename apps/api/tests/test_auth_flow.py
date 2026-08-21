from fastapi.testclient import TestClient
from scripts.bootstrap_identity import bootstrap_admin
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from stk_os.main import app
from stk_os.models import Organization, Role, User

API_ORIGIN = "https://app.stkgrupo.com.br"
BOOTSTRAP_EMAIL = "bootstrap.owner@example.test"
BOOTSTRAP_PASSWORD = "bootstrap-password-001"


def bootstrap_test_admin(session_factory: sessionmaker[Session]) -> None:
    with session_factory() as session, session.begin():
        organization = session.scalar(select(Organization).where(Organization.code == "grupo-stk"))
        assert organization is not None
        role = session.scalar(
            select(Role).where(
                Role.organization_id == organization.id,
                Role.code == "administrator",
            )
        )
        assert role is not None
        for _ in range(2):
            bootstrap_admin(
                session,
                organization=organization,
                role=role,
                email=BOOTSTRAP_EMAIL.upper(),
                name="Administrador bootstrap",
                password=BOOTSTRAP_PASSWORD,
            )
            session.flush()
        count = session.scalar(
            select(func.count()).select_from(User).where(User.email == BOOTSTRAP_EMAIL)
        )
        assert count == 1


def test_bootstrap_admin_and_invited_user_authenticate(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    bootstrap_test_admin(session_factory)
    admin_login = client.post(
        "/api/v1/auth/token",
        json={"email": BOOTSTRAP_EMAIL, "password": BOOTSTRAP_PASSWORD},
    )
    assert admin_login.status_code == 200, admin_login.text
    admin_headers = {"Authorization": f"Bearer {admin_login.json()['access_token']}"}

    roles = client.get("/api/v1/auth/roles", headers=admin_headers)
    assert roles.status_code == 200
    role = next(item for item in roles.json() if item["code"] == "administrator")
    invited = client.post(
        "/api/v1/auth/users/invite",
        headers=admin_headers,
        json={
            "email": "another.valid.user@example.test",
            "display_name": "Outro usuário válido",
            "role_id": role["id"],
            "business_unit_ids": [],
        },
    )
    assert invited.status_code == 201, invited.text
    defined = client.post(
        "/api/v1/auth/password/define",
        json={"token": invited.json()["token"], "password": "another-user-password-001"},
    )
    assert defined.status_code == 200, defined.text

    user_login = client.post(
        "/api/v1/auth/token",
        json={
            "email": "another.valid.user@example.test",
            "password": "another-user-password-001",
        },
    )
    assert user_login.status_code == 200, user_login.text
    me = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {user_login.json()['access_token']}"},
    )
    assert me.status_code == 200, me.text
    assert me.json()["email"] == "another.valid.user@example.test"


def test_unknown_user_and_wrong_password_are_indistinguishable(client: TestClient) -> None:
    unknown = client.post(
        "/api/v1/auth/token",
        json={"email": "missing@example.test", "password": "irrelevant-password-001"},
    )
    wrong = client.post(
        "/api/v1/auth/token",
        json={"email": "admin@example.test", "password": "wrong-password-value"},
    )
    assert unknown.status_code == wrong.status_code == 401
    assert unknown.json() == wrong.json() == {"detail": "Credencial inválida"}


def test_invalid_stored_hash_is_unauthorized(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    with session_factory() as session, session.begin():
        user = session.scalar(select(User).where(User.email == "admin@example.test"))
        assert user is not None
        user.password_hash = "incompatible-or-truncated-hash"
    response = client.post(
        "/api/v1/auth/token",
        json={"email": "admin@example.test", "password": "synthetic-admin-password"},
    )
    assert response.status_code == 401
    assert response.json() == {"detail": "Credencial inválida"}


def test_auth_errors_keep_production_cors_headers(client: TestClient, monkeypatch: object) -> None:
    unauthorized = client.post(
        "/api/v1/auth/token",
        headers={"Origin": API_ORIGIN},
        json={"email": "missing@example.test", "password": "irrelevant-password-001"},
    )
    assert unauthorized.status_code == 401
    assert unauthorized.headers["Access-Control-Allow-Origin"] == API_ORIGIN

    def fail_permissions(*args: object, **kwargs: object) -> frozenset[str]:
        raise RuntimeError("synthetic backend failure")

    monkeypatch.setattr("stk_os.routers.auth.permissions_for_actor", fail_permissions)
    with TestClient(app, raise_server_exceptions=False) as error_client:
        failure = error_client.post(
            "/api/v1/auth/token",
            headers={"Origin": API_ORIGIN},
            json={"email": "admin@example.test", "password": "synthetic-admin-password"},
        )
    assert failure.status_code == 500
    assert failure.headers["Access-Control-Allow-Origin"] == API_ORIGIN
