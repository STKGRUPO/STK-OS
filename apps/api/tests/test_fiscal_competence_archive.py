from __future__ import annotations

import io
import uuid
import zipfile
from datetime import UTC, date, datetime
from decimal import Decimal

from conftest import (
    ADMIN_ACTOR_ID,
    ESTABLISHMENT_ID,
    LAB_UNIT_ID,
    ORGANIZATION_ID,
    UNIT_ID,
)
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from stk_os.models import (
    Actor,
    ActorRole,
    BillingItem,
    Company,
    FiscalDocument,
    FiscalEstablishmentConfig,
    FiscalIssuance,
    Permission,
    Role,
    RolePermission,
)
from stk_os.security import create_access_token

COMPETENCE = date(2026, 9, 1)


def add_issuance(
    session: Session,
    *,
    number: str,
    customer_name: str,
    status: str = "completed",
    unit_id: uuid.UUID = UNIT_ID,
    documents: tuple[str, ...] = ("danfse_pdf", "nfse_xml"),
    content: bool = True,
) -> FiscalIssuance:
    company = Company(
        organization_id=ORGANIZATION_ID,
        legal_name=f"{customer_name} LTDA",
        trade_name=customer_name,
        status="active",
    )
    session.add(company)
    session.flush()
    item = BillingItem(
        organization_id=ORGANIZATION_ID,
        business_unit_id=unit_id,
        source_type="service_one_time",
        origin_type="one_time_service",
        reference_type="single",
        competence_month=COMPETENCE,
        customer_company_id=company.id,
        issuer_establishment_id=ESTABLISHMENT_ID,
        currency="BRL",
        gross_amount=Decimal("100.00"),
        snapshot={},
        snapshot_sha256="a" * 64,
        status="completed" if status == "completed" else "requested",
        correlation_id=uuid.uuid4(),
        created_by_actor_id=ADMIN_ACTOR_ID,
    )
    session.add(item)
    session.flush()
    config = session.scalar(select(FiscalEstablishmentConfig))
    assert config is not None
    issuance = FiscalIssuance(
        organization_id=ORGANIZATION_ID,
        billing_item_id=item.id,
        establishment_config_id=config.id,
        environment="homologation",
        status=status,
        series=1,
        dps_number=900 + int(number),
        dps_id=f"DPS-ARCHIVE-{uuid.uuid4()}",
        snapshot={},
        snapshot_sha256="b" * 64,
        nfse_number=number,
        access_key=f"{int(number):050d}",
        requested_by_actor_id=ADMIN_ACTOR_ID,
        correlation_id=uuid.uuid4(),
        completed_at=datetime.now(UTC) if status == "completed" else None,
    )
    session.add(issuance)
    session.flush()
    for kind in documents:
        payload = (
            (b"%PDF-synthetic" if kind == "danfse_pdf" else b"<NFSe/>")
            if content
            else None
        )
        session.add(
            FiscalDocument(
                issuance_id=issuance.id,
                document_type=kind,
                content_type="application/pdf" if kind == "danfse_pdf" else "application/xml",
                content_sha256="c" * 64 if payload else None,
                size_bytes=len(payload) if payload else None,
                content_bytes=payload,
                status="available",
            )
        )
    session.flush()
    return issuance


def archive(client: TestClient, headers: dict[str, str], unit_id: uuid.UUID = UNIT_ID):
    return client.get(
        "/api/v1/fiscal/documents/archive",
        params={"business_unit_id": str(unit_id), "competence_month": "2026-09"},
        headers=headers,
    )


def test_archive_contains_only_completed_documents_for_unit_and_uses_nfse_number(
    client: TestClient,
    admin_headers: dict[str, str],
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        add_issuance(session, number="25", customer_name="BSC Química")
        add_issuance(session, number="26", customer_name="Tigre Materiais")
        add_issuance(session, number="27", customer_name="Rejeitada", status="rejected")
        add_issuance(session, number="28", customer_name="Outra Unidade", unit_id=LAB_UNIT_ID)
        session.commit()

    response = archive(client, admin_headers)
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/zip"
    assert response.headers["content-disposition"] == (
        'attachment; filename="NFSE_MR_ENGENHARIA_E_CONSULTORIA_2026-09.zip"'
    )
    with zipfile.ZipFile(io.BytesIO(response.content)) as bundle:
        assert set(bundle.namelist()) == {
            "NFSE_25_BSC_QUIMICA.pdf",
            "NFSE_25_BSC_QUIMICA.xml",
            "NFSE_26_TIGRE_MATERIAIS.pdf",
            "NFSE_26_TIGRE_MATERIAIS.xml",
        }
        assert not any("925" in name or "926" in name for name in bundle.namelist())


def test_archive_includes_available_files_and_pending_manifest(
    client: TestClient,
    admin_headers: dict[str, str],
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        add_issuance(session, number="30", customer_name="Cliente X", documents=("nfse_xml",))
        add_issuance(session, number="31", customer_name="Cliente Y", documents=("danfse_pdf",))
        session.commit()

    response = archive(client, admin_headers)
    assert response.status_code == 200
    with zipfile.ZipFile(io.BytesIO(response.content)) as bundle:
        assert set(bundle.namelist()) == {
            "NFSE_30_CLIENTE_X.xml",
            "NFSE_31_CLIENTE_Y.pdf",
            "PENDENCIAS.txt",
        }
        pending = bundle.read("PENDENCIAS.txt").decode()
        assert "NFS-e 30 - Cliente X - PDF não disponível" in pending
        assert "NFS-e 31 - Cliente Y - XML não disponível" in pending


def test_archive_without_persisted_content_returns_404(
    client: TestClient,
    admin_headers: dict[str, str],
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        add_issuance(session, number="32", customer_name="Sem Conteúdo", content=False)
        session.commit()
    response = archive(client, admin_headers)
    assert response.status_code == 404
    assert response.json()["detail"] == "Nenhum documento fiscal disponível para esta competência."


def test_archive_respects_unit_scope(
    client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    actor_id = uuid.uuid4()
    with session_factory() as session:
        role = Role(
            organization_id=ORGANIZATION_ID,
            code=f"archive-{uuid.uuid4()}",
            name="Leitor fiscal restrito",
        )
        actor = Actor(
            id=actor_id,
            organization_id=ORGANIZATION_ID,
            kind="user",
            display_name="Leitor fiscal",
        )
        permission = session.scalar(select(Permission).where(Permission.code == "fiscal:read"))
        assert permission is not None
        session.add_all([role, actor])
        session.flush()
        session.add_all(
            [
                RolePermission(role_id=role.id, permission_id=permission.id),
                ActorRole(actor_id=actor.id, role_id=role.id, business_unit_id=UNIT_ID),
            ]
        )
        add_issuance(session, number="33", customer_name="Unidade Permitida")
        session.commit()
    token = create_access_token(
        actor_id=actor_id,
        actor_kind="user",
        permissions={"fiscal:read"},
    )
    headers = {"Authorization": f"Bearer {token}"}
    assert archive(client, headers).status_code == 200
    assert archive(client, headers, LAB_UNIT_ID).status_code == 404
