from __future__ import annotations

import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from pathlib import Path
from types import SimpleNamespace

import pytest
from conftest import ADMIN_ACTOR_ID, ESTABLISHMENT_ID, MR_PRODUCT_ID, UNIT_ID
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker
from test_billing import create_billable_contract, generate, month_start

from stk_os.fiscal.provider import ProviderDocument, ProviderResult
from stk_os.fiscal.runtime import get_fiscal_runtime
from stk_os.fiscal.storage import PrivateFilesystemDocumentStore
from stk_os.main import fastapi_app
from stk_os.models import (
    BillingItem,
    FiscalAttempt,
    FiscalDocument,
    FiscalEstablishmentConfig,
    FiscalIssuance,
)


def command_headers(headers: dict[str, str], key: str) -> dict[str, str]:
    return {**headers, "Idempotency-Key": key}


class FakeGateway:
    def __init__(self) -> None:
        self.issue_status = "completed"
        self.reconcile_status = "completed"
        self.issue_calls = 0
        self.reconcile_calls = 0
        self.lock = threading.Lock()
        self.issue_entered: threading.Event | None = None
        self.issue_release: threading.Event | None = None

    def result(self, status: str, dps_id: str) -> ProviderResult:
        if status == "completed":
            return ProviderResult(
                status="completed",
                http_status=201,
                nfse_number=f"NF-{dps_id[-6:]}",
                access_key=f"KEY-{dps_id}",
                provider_reference=dps_id,
                documents=(
                    ProviderDocument("nfse_xml", "application/xml", b"<NFSe synthetic='true'/>"),
                    ProviderDocument("danfse_pdf", "application/pdf", b"%PDF-1.4 synthetic"),
                ),
            )
        if status == "uncertain":
            return ProviderResult(status="uncertain", error_code="TRANSMISSION_UNCERTAIN")
        if status == "rejected":
            return ProviderResult(
                status="rejected",
                http_status=422,
                error_code="E_FISCAL_SYNTHETIC",
                detail="Rejeição fiscal sintética",
            )
        if status == "not_found":
            return ProviderResult(status="not_found", http_status=404)
        return ProviderResult(status="external_unavailable", http_status=503)

    def issue(self, *, endpoint: str, dps_id: str, signed_xml: bytes) -> ProviderResult:
        assert endpoint.startswith("https://")
        assert signed_xml.startswith(b"<?xml")
        with self.lock:
            self.issue_calls += 1
        if self.issue_entered and self.issue_release:
            self.issue_entered.set()
            assert self.issue_release.wait(timeout=5)
        return self.result(self.issue_status, dps_id)

    def reconcile(self, *, query_base_url: str, dps_id: str) -> ProviderResult:
        assert query_base_url.startswith("https://")
        with self.lock:
            self.reconcile_calls += 1
        return self.result(self.reconcile_status, dps_id)


class FakeSigner:
    def sign(self, xml: bytes, material: object) -> bytes:
        del material
        return xml


@pytest.fixture
def fake_gateway(tmp_path: Path) -> FakeGateway:
    gateway = FakeGateway()
    runtime = SimpleNamespace(
        signer=FakeSigner(),
        secret_resolver=SimpleNamespace(resolve=lambda key_id: key_id),
        document_store=PrivateFilesystemDocumentStore(tmp_path / "documents"),
        gateway_for=lambda session, config: gateway,
    )
    fastapi_app.dependency_overrides[get_fiscal_runtime] = lambda: runtime
    yield gateway
    fastapi_app.dependency_overrides.pop(get_fiscal_runtime, None)


def create_contract_item(
    client: TestClient, headers: dict[str, str], suffix: str
) -> dict[str, object]:
    competence = month_start()
    create_billable_contract(client, headers, suffix=suffix, start_on=competence)
    run = generate(client, headers, key=f"run-{suffix}", competence=competence)
    assert run.status_code == 201, run.text
    items = client.get(
        f"/api/v1/billing/items?competence_month={competence:%Y-%m}", headers=headers
    ).json()
    return next(item for item in items if item["customer_name"] == f"Faturamento {suffix}")


def issue(client: TestClient, headers: dict[str, str], item_id: str, key: str):
    return client.post(
        f"/api/v1/billing/items/{item_id}/issue",
        headers=command_headers(headers, key),
    )


def test_contract_issuance_is_idempotent_and_persists_documents(
    client: TestClient,
    admin_headers: dict[str, str],
    fake_gateway: FakeGateway,
    session_factory: sessionmaker[Session],
) -> None:
    item = create_contract_item(client, admin_headers, "FISCAL-CONTRACT")
    first = issue(client, admin_headers, item["id"], "issue-contract-1")
    replay = issue(client, admin_headers, item["id"], "issue-contract-2")
    assert first.status_code == replay.status_code == 202
    assert first.json()["status"] == replay.json()["status"] == "completed"
    assert first.json()["issuer_establishment_id"] == str(ESTABLISHMENT_ID)
    assert first.json()["nfse_number"]
    assert {document["document_type"] for document in first.json()["documents"]} == {
        "nfse_xml",
        "danfse_pdf",
    }
    assert fake_gateway.issue_calls == 1
    document_path = first.json()["documents"][0]["download_path"]
    downloaded = client.get(document_path, headers=admin_headers)
    assert downloaded.status_code == 200
    with session_factory() as session:
        assert (
            session.scalar(
                select(BillingItem).where(BillingItem.id == uuid.UUID(str(item["id"])))
            ).status
            == "completed"
        )
        assert len(session.scalars(select(FiscalIssuance)).all()) == 1
        assert len(session.scalars(select(FiscalAttempt)).all()) == 1
        assert len(session.scalars(select(FiscalDocument)).all()) == 2


def test_missing_required_fiscal_config_blocks_before_number_and_transport(
    client: TestClient,
    admin_headers: dict[str, str],
    fake_gateway: FakeGateway,
    session_factory: sessionmaker[Session],
) -> None:
    item = create_contract_item(client, admin_headers, "FISCAL-INVALID-CONFIG")
    with session_factory() as session:
        config = session.scalar(
            select(FiscalEstablishmentConfig).where(
                FiscalEstablishmentConfig.establishment_id == ESTABLISHMENT_ID
            )
        )
        assert config is not None
        initial_number = config.next_dps_number
        config.fiscal_rules = {**config.fiscal_rules, "reg_esp_trib": None}
        session.commit()
    response = issue(client, admin_headers, item["id"], "issue-invalid-config")
    assert response.status_code == 422
    with session_factory() as session:
        config = session.scalar(
            select(FiscalEstablishmentConfig).where(
                FiscalEstablishmentConfig.establishment_id == ESTABLISHMENT_ID
            )
        )
        assert config is not None and config.next_dps_number == initial_number
        assert session.scalar(select(FiscalIssuance).where(
            FiscalIssuance.billing_item_id == uuid.UUID(str(item["id"]))
        )) is None
    assert fake_gateway.issue_calls == 0


def test_timeout_is_reconciled_without_second_issue(
    client: TestClient,
    admin_headers: dict[str, str],
    fake_gateway: FakeGateway,
) -> None:
    fake_gateway.issue_status = "uncertain"
    item = create_contract_item(client, admin_headers, "FISCAL-TIMEOUT")
    uncertain = issue(client, admin_headers, item["id"], "issue-timeout")
    assert uncertain.status_code == 202
    assert uncertain.json()["status"] == "uncertain"
    reconciled = client.post(
        f"/api/v1/fiscal/issuances/{uncertain.json()['id']}/reconcile",
        headers=command_headers(admin_headers, "reconcile-timeout"),
        json={"resend_if_confirmed_not_found": False},
    )
    assert reconciled.status_code == 200
    assert reconciled.json()["status"] == "completed"
    assert fake_gateway.issue_calls == 1
    assert fake_gateway.reconcile_calls == 1


def test_concurrent_requests_create_one_external_effect(
    client: TestClient,
    admin_headers: dict[str, str],
    fake_gateway: FakeGateway,
) -> None:
    item = create_contract_item(client, admin_headers, "FISCAL-CONCURRENT")
    fake_gateway.issue_entered = threading.Event()
    fake_gateway.issue_release = threading.Event()
    with ThreadPoolExecutor(max_workers=2) as pool:
        first_future = pool.submit(
            issue, client, admin_headers, item["id"], "issue-concurrent-first"
        )
        assert fake_gateway.issue_entered.wait(timeout=5)
        second = issue(client, admin_headers, item["id"], "issue-concurrent-second")
        fake_gateway.issue_release.set()
        first = first_future.result(timeout=5)
    assert first.status_code == second.status_code == 202
    assert {first.json()["status"], second.json()["status"]} == {"completed", "processing"}
    assert fake_gateway.issue_calls == 1


def create_fiscal_customer(
    client: TestClient, headers: dict[str, str], suffix: str
) -> dict[str, object]:
    response = client.post(
        "/api/v1/crm/companies",
        headers=command_headers(headers, f"customer-{suffix}"),
        json={
            "legal_name": f"Cliente Fiscal {suffix} Ltda.",
            "trade_name": f"Fiscal {suffix}",
            "tax_id": f"28000000{len(suffix):06d}",
            "address_line": "Avenida Sintética, 200",
            "city": "São Paulo",
            "state_code": "SP",
            "municipality_code": "3550308",
            "postal_code": "01001000",
            "business_unit_ids": [str(UNIT_ID)],
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_recurring_without_contract_and_one_time_flow_are_issued(
    client: TestClient,
    admin_headers: dict[str, str],
    fake_gateway: FakeGateway,
) -> None:
    customer = create_fiscal_customer(client, admin_headers, "SERVICES")
    service = client.post(
        "/api/v1/client-services",
        headers=admin_headers,
        json={
            "business_unit_id": str(UNIT_ID),
            "customer_company_id": customer["id"],
            "product_service_id": str(MR_PRODUCT_ID),
            "name": "Serviço recorrente fiscal",
            "description": "Consultoria mensal sintética",
            "service_type": "recurring",
            "recurrence": "monthly",
            "start_date": date.today().isoformat(),
            "owner_actor_id": str(ADMIN_ACTOR_ID),
            "amount": "800.00",
        },
    )
    assert service.status_code == 201, service.text
    generated = client.post(
        f"/api/v1/client-services/{service.json()['id']}/occurrences/generate",
        headers=command_headers(admin_headers, "generate-fiscal-recurring"),
        json={"through": date.today().isoformat()},
    )
    occurrence = generated.json()["occurrences"][0]
    billing = client.post(
        f"/api/v1/client-services/{service.json()['id']}/occurrences/{occurrence['id']}/billing-item",
        headers=command_headers(admin_headers, "bill-fiscal-recurring"),
    )
    recurring = issue(client, admin_headers, billing.json()["id"], "issue-fiscal-recurring")
    assert recurring.json()["status"] == "completed"

    one_time = client.post(
        "/api/v1/billing/one-time",
        headers=command_headers(admin_headers, "one-time-fiscal"),
        json={
            "business_unit_id": str(UNIT_ID),
            "customer_company_id": customer["id"],
            "product_service_id": str(MR_PRODUCT_ID),
            "service_name": "Laudo pontual",
            "description": "Emissão de laudo técnico sintético",
            "reference": "OS-AVULSA-001",
            "service_date": date.today().isoformat(),
            "amount": "450.00",
            "issuer_establishment_id": str(ESTABLISHMENT_ID),
        },
    )
    assert one_time.status_code == 201, one_time.text
    assert one_time.json()["billing_status"] == "ready"
    emitted = issue(
        client, admin_headers, one_time.json()["billing_item_id"], "issue-one-time-fiscal"
    )
    assert emitted.json()["status"] == "completed"
    assert fake_gateway.issue_calls == 2


def test_known_fiscal_error_is_auditable_and_not_retried(
    client: TestClient,
    admin_headers: dict[str, str],
    fake_gateway: FakeGateway,
) -> None:
    fake_gateway.issue_status = "rejected"
    item = create_contract_item(client, admin_headers, "FISCAL-REJECT")
    rejected = issue(client, admin_headers, item["id"], "issue-rejected")
    repeated = issue(client, admin_headers, item["id"], "issue-rejected-again")
    assert rejected.json()["status"] == repeated.json()["status"] == "rejected"
    assert rejected.json()["error_code"] == "E_FISCAL_SYNTHETIC"
    assert fake_gateway.issue_calls == 1


def test_one_time_blocks_incomplete_crm_customer(
    client: TestClient, admin_headers: dict[str, str], fake_gateway: FakeGateway
) -> None:
    customer = client.post(
        "/api/v1/crm/companies",
        headers=command_headers(admin_headers, "customer-incomplete-fiscal"),
        json={
            "legal_name": "Cliente Incompleto Fiscal Ltda.",
            "business_unit_ids": [str(UNIT_ID)],
        },
    ).json()
    one_time = client.post(
        "/api/v1/billing/one-time",
        headers=command_headers(admin_headers, "one-time-blocked"),
        json={
            "business_unit_id": str(UNIT_ID),
            "customer_company_id": customer["id"],
            "service_name": "Serviço bloqueado",
            "description": "Dados fiscais incompletos",
            "reference": "BLOCK-001",
            "service_date": date.today().isoformat(),
            "amount": "100.00",
            "issuer_establishment_id": str(ESTABLISHMENT_ID),
        },
    )
    assert one_time.status_code == 201
    assert one_time.json()["billing_status"] == "blocked"
    blocked_issue = issue(
        client, admin_headers, one_time.json()["billing_item_id"], "issue-blocked-item"
    )
    assert blocked_issue.status_code == 409
    assert fake_gateway.issue_calls == 0
