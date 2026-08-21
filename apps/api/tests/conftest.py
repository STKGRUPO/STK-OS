from __future__ import annotations

import os
import uuid
from collections.abc import Iterator
from datetime import UTC, datetime

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
    FiscalEstablishmentConfig,
    LeadSource,
    LegalEntity,
    LossReason,
    Organization,
    Permission,
    Pipeline,
    PipelineStage,
    ProductService,
    Role,
    RolePermission,
    ServiceAccount,
    User,
)
from stk_os.security import hash_secret

ORGANIZATION_ID = uuid.UUID("10000000-0000-4000-8000-000000000001")
LEGAL_ENTITY_ID = uuid.UUID("20000000-0000-4000-8000-000000000001")
ESTABLISHMENT_ID = uuid.UUID("30000000-0000-4000-8000-000000000001")
SECOND_LEGAL_ENTITY_ID = uuid.UUID("20000000-0000-4000-8000-000000000002")
SECOND_ESTABLISHMENT_ID = uuid.UUID("30000000-0000-4000-8000-000000000003")
UNIT_ID = uuid.UUID("40000000-0000-4000-8000-000000000001")
LAB_UNIT_ID = uuid.UUID("40000000-0000-4000-8000-000000000002")
STELLI_UNIT_ID = uuid.UUID("40000000-0000-4000-8000-000000000003")
ADMIN_ACTOR_ID = uuid.UUID("60000000-0000-4000-8000-000000000001")
SERVICE_ACTOR_ID = uuid.UUID("60000000-0000-4000-8000-000000000002")
SOURCE_ID = uuid.UUID("71000000-0000-4000-8000-000000000001")
MR_PRODUCT_ID = uuid.UUID("72000000-0000-4000-8000-000000000001")
MR_PIPELINE_ID = uuid.UUID("73000000-0000-4000-8000-000000000001")
MR_STAGE_LEAD_ID = uuid.UUID("74000000-0000-4000-8000-000000000001")
MR_STAGE_PROPOSAL_ID = uuid.UUID("74000000-0000-4000-8000-000000000002")
MR_LOSS_REASON_ID = uuid.UUID("75000000-0000-4000-8000-000000000001")


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
            tax_id="12345678000190",
        )
        establishment = FiscalEstablishment(
            id=ESTABLISHMENT_ID,
            legal_entity_id=LEGAL_ENTITY_ID,
            code="matriz",
            name="Matriz sintética",
            kind="headquarters",
            tax_id="12345678000190",
        )
        second_entity = LegalEntity(
            id=SECOND_LEGAL_ENTITY_ID,
            organization_id=ORGANIZATION_ID,
            code="zz-st-servicos",
            registered_name="ST Serviços — sintética",
            trade_name="ST Serviços",
        )
        second_establishment = FiscalEstablishment(
            id=SECOND_ESTABLISHMENT_ID,
            legal_entity_id=SECOND_LEGAL_ENTITY_ID,
            code="matriz-st-servicos",
            name="Matriz ST Serviços sintética",
            kind="headquarters",
        )
        unit = BusinessUnit(
            id=UNIT_ID,
            organization_id=ORGANIZATION_ID,
            primary_establishment_id=ESTABLISHMENT_ID,
            code="mr",
            name="MR Engenharia e Consultoria",
        )
        lab_unit = BusinessUnit(
            id=LAB_UNIT_ID,
            organization_id=ORGANIZATION_ID,
            primary_establishment_id=ESTABLISHMENT_ID,
            code="stk-lab",
            name="STK Lab",
        )
        stelli_unit = BusinessUnit(
            id=STELLI_UNIT_ID,
            organization_id=ORGANIZATION_ID,
            primary_establishment_id=ESTABLISHMENT_ID,
            code="stelli",
            name="Stelli",
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
                "crm:read",
                "crm:write",
                "crm:import",
                "contracts:read",
                "contracts:create",
                "contracts:update",
                "contracts:version",
                "contracts:suspend",
                "contracts:resume",
                "contracts:terminate",
                "billing:read",
                "billing:generate",
                "billing:review",
                "billing:reprocess",
                "identity:manage",
                "services:read",
                "services:write",
                "fiscal:issue",
                "fiscal:read",
                "fiscal:reconcile",
            )
        }
        session.add_all(
            [
                organization,
                entity,
                establishment,
                second_entity,
                second_establishment,
                unit,
                lab_unit,
                stelli_unit,
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
                    password_set_at=datetime.now(UTC),
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
        for code in ("crm:read", "crm:write"):
            session.add(RolePermission(role_id=service_role.id, permission_id=permissions[code].id))
        session.add(
            RolePermission(role_id=service_role.id, permission_id=permissions["contracts:read"].id)
        )
        for code in ("billing:read", "billing:generate"):
            session.add(RolePermission(role_id=service_role.id, permission_id=permissions[code].id))
        for code in ("fiscal:issue", "fiscal:read"):
            session.add(RolePermission(role_id=service_role.id, permission_id=permissions[code].id))
        session.add(
            FiscalEstablishmentConfig(
                organization_id=ORGANIZATION_ID,
                establishment_id=ESTABLISHMENT_ID,
                environment="homologation",
                provider="sefin_nacional",
                emission_method="api_a1",
                endpoint="https://sefin.producaorestrita.nfse.gov.br/api/v1/dps",
                query_base_url="https://sefin.producaorestrita.nfse.gov.br/api/v1",
                certificate_secret_ref="vault://synthetic/a1",
                certificate_key_id="synthetic_a1",
                municipality_code="3550308",
                series=1,
                next_dps_number=1,
                service_code="010101",
                nbs_code="101010100",
                fiscal_rules={
                    "tax_regime": "lucro_presumido",
                    "service_profile": "servicos_profissionais",
                    "iss_percent": "2.00",
                },
            )
        )
        source = LeadSource(
            id=SOURCE_ID,
            organization_id=ORGANIZATION_ID,
            code="synthetic",
            name="Origem sintética",
        )
        session.add(source)
        for index, (unit_id, unit_code) in enumerate(
            ((UNIT_ID, "mr"), (LAB_UNIT_ID, "lab"), (STELLI_UNIT_ID, "stelli")), start=1
        ):
            product_id = MR_PRODUCT_ID if unit_id == UNIT_ID else uuid.uuid4()
            pipeline_id = MR_PIPELINE_ID if unit_id == UNIT_ID else uuid.uuid4()
            first_stage_id = MR_STAGE_LEAD_ID if unit_id == UNIT_ID else uuid.uuid4()
            second_stage_id = MR_STAGE_PROPOSAL_ID if unit_id == UNIT_ID else uuid.uuid4()
            session.add_all(
                [
                    ProductService(
                        id=product_id,
                        organization_id=ORGANIZATION_ID,
                        business_unit_id=unit_id,
                        code=f"service-{unit_code}",
                        name=f"Serviço {unit_code} sintético",
                    ),
                    Pipeline(
                        id=pipeline_id,
                        organization_id=ORGANIZATION_ID,
                        business_unit_id=unit_id,
                        code="sales",
                        name=f"Pipeline {unit_code}",
                    ),
                    PipelineStage(
                        id=first_stage_id,
                        pipeline_id=pipeline_id,
                        code="lead",
                        name="Lead",
                        position=1,
                    ),
                    PipelineStage(
                        id=second_stage_id,
                        pipeline_id=pipeline_id,
                        code="proposal",
                        name="Proposta",
                        position=2,
                    ),
                    LossReason(
                        id=MR_LOSS_REASON_ID if index == 1 else uuid.uuid4(),
                        organization_id=ORGANIZATION_ID,
                        business_unit_id=unit_id,
                        code="other",
                        name="Outro",
                    ),
                ]
            )

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
