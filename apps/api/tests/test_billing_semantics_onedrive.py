from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from conftest import ADMIN_ACTOR_ID, ESTABLISHMENT_ID, ORGANIZATION_ID, UNIT_ID
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from stk_os.fiscal_schemas import OneTimeBillingCreate
from stk_os.integrations import onedrive
from stk_os.models import (
    BillingItem,
    Company,
    FiscalArchiveJob,
    FiscalDocument,
    FiscalEstablishmentConfig,
    FiscalIssuance,
    IntegrationConnection,
)
from stk_os.routers.billing import billing_reference_fields


def command(**values: object) -> OneTimeBillingCreate:
    base = {
        "business_unit_id": UNIT_ID,
        "customer_company_id": uuid.uuid4(),
        "service_name": "Serviço sintético",
        "description": "Descrição fiscal preservada",
        "reference": "REF-1",
        "service_date": date(2026, 9, 1),
        "amount": Decimal("100.00"),
        "issuer_establishment_id": ESTABLISHMENT_ID,
    }
    return OneTimeBillingCreate.model_validate(base | values)


@pytest.mark.parametrize(
    ("origin", "reference", "position", "total", "origin_label", "reference_label"),
    [
        ("contract", "month", 10, 12, "Contrato", "Mês 10/12"),
        ("recurring_service", "installment", 7, 12, "Serviço recorrente", "Parcela 07 de 12"),
        ("recurring_service", "single", None, None, "Serviço recorrente", "Única"),
        ("one_time_service", "installment", 7, 12, "Serviço avulso", "Parcela 07 de 12"),
        ("one_time_service", "single", None, None, "Serviço avulso", "Única"),
    ],
)
def test_canonical_commercial_labels(
    origin: str,
    reference: str,
    position: int | None,
    total: int | None,
    origin_label: str,
    reference_label: str,
) -> None:
    item = BillingItem(
        origin_type=origin,
        reference_type=reference,
        reference_position=position,
        reference_total=total,
    )
    assert billing_reference_fields(item) == (
        origin,
        origin_label,
        reference,
        position,
        total,
        reference_label,
    )


@pytest.mark.parametrize("reference", ["installment", "single"])
def test_contract_rejects_non_month_reference(reference: str) -> None:
    values: dict[str, object] = {"origin_type": "contract", "reference_type": reference}
    if reference == "installment":
        values |= {"reference_position": 1, "reference_total": 2}
    with pytest.raises(ValidationError):
        command(**values)


def test_one_time_defaults_and_contract_without_contract_id() -> None:
    traditional = command()
    assert traditional.origin_type is None
    assert traditional.reference_type is None
    contract = command(
        origin_type="contract",
        reference_type="month",
        reference_position=7,
        reference_total=12,
    )
    assert contract.origin_type == "contract"
    assert contract.reference_type == "month"


def test_onedrive_endpoints_do_not_expose_tokens_or_issue_documents(
    client: TestClient, admin_headers: dict[str, str]
) -> None:
    response = client.get("/api/v1/integrations/onedrive/status", headers=admin_headers)
    assert response.status_code == 200
    assert response.json() == {
        "connected": False,
        "provider": "onedrive",
        "account_name": None,
        "status": "disconnected",
    }
    assert "token" not in response.text.lower()
    archived = client.post(
        "/api/v1/integrations/onedrive/archive-pending", headers=admin_headers
    )
    assert archived.status_code == 200
    assert archived.json() == {"completed": 0, "failed": 0}


def make_archive_fixture(session: Session) -> tuple[FiscalIssuance, FiscalArchiveJob]:
    company = Company(
        organization_id=ORGANIZATION_ID,
        legal_name="BSC Química Ltda",
        trade_name="BSC Química",
        tax_id="78530375000150",
        status="active",
    )
    session.add(company)
    session.flush()
    item = BillingItem(
        organization_id=ORGANIZATION_ID,
        business_unit_id=UNIT_ID,
        source_type="service_one_time",
        origin_type="one_time_service",
        reference_type="single",
        competence_month=date(2026, 9, 1),
        customer_company_id=company.id,
        issuer_establishment_id=ESTABLISHMENT_ID,
        currency="BRL",
        gross_amount=Decimal("800.00"),
        snapshot={},
        snapshot_sha256="a" * 64,
        status="completed",
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
        status="completed",
        series=1,
        dps_number=25,
        dps_id=f"DPS-{uuid.uuid4()}",
        snapshot={},
        snapshot_sha256="b" * 64,
        nfse_number="25",
        access_key=str(uuid.uuid4()),
        requested_by_actor_id=ADMIN_ACTOR_ID,
        correlation_id=uuid.uuid4(),
        completed_at=datetime.now(UTC),
    )
    session.add(issuance)
    session.flush()
    for kind, content_type, content in (
        ("nfse_xml", "application/xml", b"<NFSe/>"),
        ("danfse_pdf", "application/pdf", b"%PDF-synthetic"),
    ):
        session.add(
            FiscalDocument(
                issuance_id=issuance.id,
                document_type=kind,
                content_type=content_type,
                content_sha256="c" * 64,
                size_bytes=len(content),
                content_bytes=content,
                status="available",
            )
        )
    session.flush()
    job = onedrive.enqueue_archive(session, issuance)
    assert job is not None
    return issuance, job


def test_onedrive_failure_does_not_change_issuance_and_retry_is_idempotent(
    session_factory: sessionmaker[Session], monkeypatch: pytest.MonkeyPatch
) -> None:
    uploads: list[str] = []
    with session_factory() as session:
        issuance, job = make_archive_fixture(session)
        session.add(
            IntegrationConnection(
                organization_id=ORGANIZATION_ID,
                provider="onedrive",
                access_token_ciphertext=b"encrypted",
                access_token_nonce=b"nonce",
                refresh_token_ciphertext=b"encrypted",
                refresh_token_nonce=b"nonce",
                token_expires_at=datetime.now(UTC),
                scopes=onedrive.SCOPES,
                status="active",
            )
        )
        monkeypatch.setattr(onedrive, "access_token", lambda *_: "token")
        monkeypatch.setattr(onedrive, "_ensure_directory", lambda *_: None)
        monkeypatch.setattr(
            onedrive,
            "_put_file",
            lambda *_: (_ for _ in ()).throw(onedrive.OneDriveError("falha sintética")),
        )
        assert onedrive.process_pending(session, ORGANIZATION_ID) == (0, 1)
        assert session.get(FiscalIssuance, issuance.id).status == "completed"
        assert session.get(FiscalArchiveJob, job.id).status == "failed"
        monkeypatch.setattr(
            onedrive,
            "_put_file",
            lambda _token, path, _content, _content_type: uploads.append(path),
        )
        completed, failed = onedrive.process_pending(session, ORGANIZATION_ID)
        assert (completed, failed) == (1, 0)
        assert len(uploads) == 2
        assert all("MR Engenharia e Consultoria/2026/09 - Setembro" in path for path in uploads)
        assert {path.rsplit("/", 1)[-1] for path in uploads} == {
            "NFSE_25_BSC_Química.pdf",
            "NFSE_25_BSC_Química.xml",
        }
        assert session.get(FiscalIssuance, issuance.id).status == "completed"
        assert session.get(FiscalArchiveJob, job.id).status == "completed"
        assert onedrive.process_pending(session, ORGANIZATION_ID) == (0, 0)
        assert len(uploads) == 2
