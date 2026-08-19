from __future__ import annotations

import os
import uuid
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

os.environ["STK_JWT_SECRET"] = "test-only-secret-with-at-least-thirty-two-characters"
os.environ["STK_JWT_ISSUER"] = "stk-os-test"

from stk_os.database import get_session
from stk_os.main import app
from stk_os.models import (
    Actor,
    ActorRole,
    Base,
    BusinessUnit,
    FiscalEstablishment,
    LegalEntity,
    Organization,
    Permission,
    Role,
    RolePermission,
    ServiceAccount,
    User,
)
from stk_os.security import hash_secret

ORGANIZATION_ID = uuid.UUID("10000000-0000-4000-8000-000000000001")
LEGAL_ENTITY_ID = uuid.UUID("20000000-0000-4000-8000-000000000001")
ESTABLISHMENT_ID = uuid.UUID("30000000-0000-4000-8000-000000000001")
UNIT_ID = uuid.UUID("40000000-0000-4000-8000-000000000001")
ADMIN_ACTOR_ID = uuid.UUID("60000000-0000-4000-8000-000000000001")
SERVICE_ACTOR_ID = uuid.UUID("60000000-0000-4000-8000-000000000002")


@pytest.fixture(scope="session")
def session_factory() -> sessionmaker[Session]:
    engine = create_engine(
        "sqlite+pysqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)


@pytest.fixture(autouse=True)
def clean_database(session_factory: sessionmaker[Session]) -> Iterator[None]:
    engine = session_factory.kw["bind"]
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    with session_factory() as session, session.begin():
        organization = Organization(id=ORGANIZATION_ID, code="grupo-stk", name="Grupo STK")
        entity = LegalEntity(
            id=LEGAL_ENTITY_ID,
            organization_id=ORGANIZATION_ID,
            code="stk-solucoes",
            registered_name="STK Soluções — sintética",
            trade_name="MR",
        )
        establishment = FiscalEstablishment(
            id=ESTABLISHMENT_ID,
            legal_entity_id=LEGAL_ENTITY_ID,
            code="matriz",
            name="Matriz sintética",
            kind="headquarters",
        )
        unit = BusinessUnit(
            id=UNIT_ID,
            organization_id=ORGANIZATION_ID,
            primary_establishment_id=ESTABLISHMENT_ID,
            code="mr",
            name="MR Engenharia e Consultoria",
        )
        admin_actor = Actor(
            id=ADMIN_ACTOR_ID,
            organization_id=ORGANIZATION_ID,
            kind="user",
            display_name="Administrador de teste",
        )
        service_actor = Actor(
            id=SERVICE_ACTOR_ID,
            organization_id=ORGANIZATION_ID,
            kind="service_account",
            display_name="Integração de teste",
        )
        admin_role = Role(
            id=uuid.uuid4(), organization_id=ORGANIZATION_ID, code="administrator", name="Admin"
        )
        service_role = Role(
            id=uuid.uuid4(), organization_id=ORGANIZATION_ID, code="integration", name="Integration"
        )
        permissions = {
            code: Permission(id=uuid.uuid4(), code=code, description=code)
            for code in (
                "organization:read",
                "organization:write",
                "audit:read",
                "events:ingest",
                "exceptions:write",
            )
        }
        session.add_all(
            [
                organization,
                entity,
                establishment,
                unit,
                admin_actor,
                service_actor,
                admin_role,
                service_role,
                *permissions.values(),
            ]
        )
        session.flush()
        session.add_all(
            [
                User(
                    actor_id=ADMIN_ACTOR_ID,
                    email="admin@example.test",
                    password_hash=hash_secret("synthetic-admin-password"),
                ),
                ServiceAccount(
                    actor_id=SERVICE_ACTOR_ID,
                    client_id="test-integration",
                    secret_hash=hash_secret("synthetic-service-secret"),
                ),
                ActorRole(actor_id=ADMIN_ACTOR_ID, role_id=admin_role.id),
                ActorRole(actor_id=SERVICE_ACTOR_ID, role_id=service_role.id),
            ]
        )
        for permission in permissions.values():
            session.add(RolePermission(role_id=admin_role.id, permission_id=permission.id))
        for code in ("organization:read", "events:ingest", "exceptions:write"):
            session.add(RolePermission(role_id=service_role.id, permission_id=permissions[code].id))

    def override_session() -> Iterator[Session]:
        with session_factory() as session:
            yield session

    app.dependency_overrides[get_session] = override_session
    yield
    app.dependency_overrides.clear()


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture
def admin_headers(client: TestClient) -> dict[str, str]:
    response = client.post(
        "/api/v1/auth/token",
        json={"email": "admin@example.test", "password": "synthetic-admin-password"},
    )
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


@pytest.fixture
def service_headers(client: TestClient) -> dict[str, str]:
    response = client.post(
        "/api/v1/auth/service-token",
        json={"client_id": "test-integration", "client_secret": "synthetic-service-secret"},
    )
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}
