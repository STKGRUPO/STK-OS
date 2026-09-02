from __future__ import annotations

import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from pathlib import Path
from types import SimpleNamespace

import pytest
from conftest import (
    ADMIN_ACTOR_ID,
    ESTABLISHMENT_ID,
    LEGAL_ENTITY_ID,
    MR_PRODUCT_ID,
    SECOND_ESTABLISHMENT_ID,
    UNIT_ID,
)
from fastapi.testclient import TestClient
from lxml import etree
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker
from test_billing import create_billable_contract, generate, month_start

from stk_os.fiscal.provider import ProviderDocument, ProviderResult
from stk_os.fiscal.runtime import get_fiscal_runtime
from stk_os.fiscal.storage import PrivateFilesystemDocumentStore
from stk_os.main import fastapi_app
from stk_os.models import (
    Actor,
    ActorRole,
    BillingItem,
    FiscalAttempt,
    FiscalDocument,
    FiscalEstablishment,
    FiscalEstablishmentConfig,
    FiscalIssuance,
    LegalEntity,
    Organization,
    Permission,
    Role,
    RolePermission,
)
from stk_os.security import create_access_token

AUTHORIZED_NFSE_XML = (
    Path(__file__).parent / "fixtures" / "nfse_13_authorized_without_signatures.xml"
).read_bytes()


def command_headers(headers: dict[str, str], key: str) -> dict[str, str]:
    return {**headers, "Idempotency-Key": key}


class FakeGateway:
    def __init__(self) -> None:
        self.issue_status = "completed"
        self.issue_statuses: list[str] = []
        self.reconcile_status = "completed"
        self.issue_calls = 0
        self.reconcile_calls = 0
        self.document_fetch_calls = 0
        self.document_xml_override: bytes | None = None
        self.issued_xmls: list[bytes] = []
        self.lock = threading.Lock()
        self.issue_entered: threading.Event | None = None
        self.issue_release: threading.Event | None = None

    def result(self, status: str, dps_id: str) -> ProviderResult:
        if status == "completed":
            sequence = max(self.issue_calls, 1)
            nfse_number = str(12 + sequence)
            access_key = str(
                int("42091022239813375000106000000000001326090584825643") + sequence - 1
            )
            authorized_xml = AUTHORIZED_NFSE_XML.replace(
                b"<nNFSe>13</nNFSe>", f"<nNFSe>{nfse_number}</nNFSe>".encode()
            ).replace(
                b"42091022239813375000106000000000001326090584825643",
                access_key.encode(),
            )
            return ProviderResult(
                status="completed",
                http_status=201,
                nfse_number=nfse_number,
                access_key=access_key,
                provider_reference=dps_id,
                documents=(ProviderDocument("nfse_xml", "application/xml", authorized_xml),),
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
        self.issued_xmls.append(signed_xml)
        with self.lock:
            self.issue_calls += 1
        if self.issue_entered and self.issue_release:
            self.issue_entered.set()
            assert self.issue_release.wait(timeout=5)
        status = self.issue_statuses.pop(0) if self.issue_statuses else self.issue_status
        return self.result(status, dps_id)

    def reconcile(self, *, query_base_url: str, dps_id: str) -> ProviderResult:
        assert query_base_url.startswith("https://")
        with self.lock:
            self.reconcile_calls += 1
        return self.result(self.reconcile_status, dps_id)

    def fetch_authorized_nfse(
        self, *, query_base_url: str, access_key: str, dps_id: str
    ) -> ProviderResult:
        assert query_base_url.startswith("https://")
        with self.lock:
            self.document_fetch_calls += 1
        if self.document_xml_override is not None:
            return ProviderResult(
                status="completed",
                http_status=200,
                nfse_number="13",
                access_key=access_key,
                provider_reference=dps_id,
                documents=(
                    ProviderDocument(
                        "nfse_xml", "application/xml", self.document_xml_override
                    ),
                ),
            )
        result = self.result("completed", dps_id)
        assert result.access_key == access_key
        return result


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


def create_contract_items(
    client: TestClient, headers: dict[str, str], suffixes: tuple[str, ...]
) -> list[dict[str, object]]:
    competence = month_start()
    for suffix in suffixes:
        create_billable_contract(client, headers, suffix=suffix, start_on=competence)
    run = generate(client, headers, key=f"run-{'-'.join(suffixes)}", competence=competence)
    assert run.status_code == 201, run.text
    items = client.get(
        f"/api/v1/billing/items?competence_month={competence:%Y-%m}", headers=headers
    ).json()
    by_customer = {item["customer_name"]: item for item in items}
    return [by_customer[f"Faturamento {suffix}"] for suffix in suffixes]


def issue(client: TestClient, headers: dict[str, str], item_id: str, key: str):
    return client.post(
        f"/api/v1/billing/items/{item_id}/issue",
        headers=command_headers(headers, key),
    )


def configure_nfse_13_issuer(session_factory: sessionmaker[Session]) -> None:
    with session_factory() as session:
        establishment = session.get(FiscalEstablishment, ESTABLISHMENT_ID)
        entity = session.get(LegalEntity, LEGAL_ENTITY_ID)
        config = session.scalar(
            select(FiscalEstablishmentConfig).where(
                FiscalEstablishmentConfig.establishment_id == ESTABLISHMENT_ID
            )
        )
        assert establishment is not None and entity is not None and config is not None
        establishment.tax_id = "39813375000106"
        entity.tax_id = "39813375000106"
        config.next_dps_number = 13
        session.commit()


def other_organization_headers(session_factory: sessionmaker[Session]) -> dict[str, str]:
    organization_id = uuid.UUID("10000000-0000-4000-8000-000000000099")
    actor_id = uuid.UUID("60000000-0000-4000-8000-000000000099")
    role_id = uuid.UUID("50000000-0000-4000-8000-000000000099")
    with session_factory() as session:
        session.add_all(
            [
                Organization(id=organization_id, code="other-org", name="Outra organização"),
                Actor(
                    id=actor_id,
                    organization_id=organization_id,
                    kind="user",
                    display_name="Outro administrador",
                ),
                Role(
                    id=role_id,
                    organization_id=organization_id,
                    code="fiscal-reviewer",
                    name="Fiscal reviewer",
                ),
            ]
        )
        session.flush()
        for code in ("fiscal:read", "fiscal:reconcile"):
            permission = session.scalar(select(Permission).where(Permission.code == code))
            assert permission is not None
            session.add(RolePermission(role_id=role_id, permission_id=permission.id))
        session.add(ActorRole(actor_id=actor_id, role_id=role_id))
        session.commit()
    token = create_access_token(
        actor_id=actor_id,
        actor_kind="user",
        permissions={"fiscal:read", "fiscal:reconcile"},
    )
    return {"Authorization": f"Bearer {token}"}


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
    assert first.json()["nfse_number"] == "13"
    assert first.json()["access_key"] == "42091022239813375000106000000000001326090584825643"
    assert {document["document_type"] for document in first.json()["documents"]} == {
        "nfse_xml",
        "danfse_pdf",
    }
    assert fake_gateway.issue_calls == 1
    documents = {document["document_type"]: document for document in first.json()["documents"]}
    assert documents["nfse_xml"]["filename"] == "NFSE_13_FATURAMENTO_FISCAL_CONTRACT.xml"
    assert documents["danfse_pdf"]["filename"] == "NFSE_13_FATURAMENTO_FISCAL_CONTRACT.pdf"
    downloaded_xml = client.get(documents["nfse_xml"]["download_path"], headers=admin_headers)
    assert downloaded_xml.status_code == 200
    assert downloaded_xml.content == AUTHORIZED_NFSE_XML
    assert (
        'filename="NFSE_13_FATURAMENTO_FISCAL_CONTRACT.xml"'
        in downloaded_xml.headers["content-disposition"]
    )
    downloaded_pdf = client.get(documents["danfse_pdf"]["download_path"], headers=admin_headers)
    assert downloaded_pdf.status_code == 200
    assert downloaded_pdf.content.startswith(b"%PDF-")
    assert (
        'filename="NFSE_13_FATURAMENTO_FISCAL_CONTRACT.pdf"'
        in downloaded_pdf.headers["content-disposition"]
    )
    with session_factory() as session:
        assert (
            session.scalar(
                select(BillingItem).where(BillingItem.id == uuid.UUID(str(item["id"])))
            ).status
            == "completed"
        )
        assert len(session.scalars(select(FiscalIssuance)).all()) == 1
        assert len(session.scalars(select(FiscalAttempt)).all()) == 1
        persisted_documents = list(session.scalars(select(FiscalDocument)).all())
        assert len(persisted_documents) == 2
        assert all(document.content_bytes for document in persisted_documents)


def test_completed_nfse_13_document_recovery_is_idempotent_and_scoped(
    client: TestClient,
    admin_headers: dict[str, str],
    fake_gateway: FakeGateway,
    session_factory: sessionmaker[Session],
) -> None:
    configure_nfse_13_issuer(session_factory)
    item = create_contract_item(client, admin_headers, "DOCUMENT-RECOVERY")
    issued = issue(client, admin_headers, item["id"], "issue-document-recovery")
    assert issued.status_code == 202
    original = issued.json()
    assert original["status"] == "completed"
    assert original["dps_number"] == 13
    assert original["nfse_number"] == "13"
    assert original["access_key"] == "42091022239813375000106000000000001326090584825643"

    issuance_id = uuid.UUID(original["id"])
    with session_factory() as session:
        xml_document = session.scalar(
            select(FiscalDocument).where(
                FiscalDocument.issuance_id == issuance_id,
                FiscalDocument.document_type == "nfse_xml",
            )
        )
        pdf_document = session.scalar(
            select(FiscalDocument).where(
                FiscalDocument.issuance_id == issuance_id,
                FiscalDocument.document_type == "danfse_pdf",
            )
        )
        assert xml_document is not None and pdf_document is not None
        xml_document.content_bytes = None
        session.delete(pdf_document)
        session.commit()

    endpoint = f"/api/v1/fiscal/issuances/{issuance_id}/documents/reconcile"
    recovered = client.post(
        endpoint,
        headers=command_headers(admin_headers, "recover-documents-13-first"),
    )
    assert recovered.status_code == 200, recovered.text
    assert recovered.json()["status"] == "completed"
    assert recovered.json()["dps_number"] == 13
    assert recovered.json()["nfse_number"] == "13"
    assert recovered.json()["access_key"] == original["access_key"]
    assert fake_gateway.issue_calls == 1
    assert fake_gateway.document_fetch_calls == 1

    documents = {
        document["document_type"]: document for document in recovered.json()["documents"]
    }
    assert documents["nfse_xml"]["status"] == "available"
    assert documents["danfse_pdf"]["status"] == "available"
    with session_factory() as session:
        persisted = list(
            session.scalars(
                select(FiscalDocument).where(FiscalDocument.issuance_id == issuance_id)
            )
        )
        assert len(persisted) == 2
        assert all(fiscal_document.content_bytes for fiscal_document in persisted)
        issuance = session.get(FiscalIssuance, issuance_id)
        assert issuance is not None
        assert (issuance.status, issuance.dps_number, issuance.nfse_number) == (
            "completed",
            13,
            "13",
        )
        assert issuance.access_key == original["access_key"]

    replay = client.post(
        endpoint,
        headers=command_headers(admin_headers, "recover-documents-13-second"),
    )
    assert replay.status_code == 200
    assert replay.json()["status"] == "completed"
    assert fake_gateway.issue_calls == 1
    assert fake_gateway.document_fetch_calls == 1

    foreign_headers = other_organization_headers(session_factory)
    forbidden_recovery = client.post(
        endpoint,
        headers=command_headers(foreign_headers, "foreign-document-recovery"),
    )
    assert forbidden_recovery.status_code == 404
    forbidden_download = client.get(
        documents["nfse_xml"]["download_path"], headers=foreign_headers
    )
    assert forbidden_download.status_code == 404


def test_document_recovery_rejects_existing_hash_divergence_without_mutation(
    client: TestClient,
    admin_headers: dict[str, str],
    fake_gateway: FakeGateway,
    session_factory: sessionmaker[Session],
) -> None:
    configure_nfse_13_issuer(session_factory)
    item = create_contract_item(client, admin_headers, "DOCUMENT-DIVERGENCE")
    issued = issue(client, admin_headers, item["id"], "issue-document-divergence").json()
    issuance_id = uuid.UUID(issued["id"])
    with session_factory() as session:
        xml_document = session.scalar(
            select(FiscalDocument).where(
                FiscalDocument.issuance_id == issuance_id,
                FiscalDocument.document_type == "nfse_xml",
            )
        )
        pdf_document = session.scalar(
            select(FiscalDocument).where(
                FiscalDocument.issuance_id == issuance_id,
                FiscalDocument.document_type == "danfse_pdf",
            )
        )
        assert xml_document is not None and pdf_document is not None
        xml_document.content_bytes = None
        xml_document.content_sha256 = "0" * 64
        session.delete(pdf_document)
        session.commit()

    response = client.post(
        f"/api/v1/fiscal/issuances/{issuance_id}/documents/reconcile",
        headers=command_headers(admin_headers, "recover-divergent-document"),
    )
    assert response.status_code == 409
    assert "diverge" in response.json()["detail"]
    assert fake_gateway.issue_calls == 1
    assert fake_gateway.document_fetch_calls == 1
    with session_factory() as session:
        issuance = session.get(FiscalIssuance, issuance_id)
        xml_document = session.scalar(
            select(FiscalDocument).where(
                FiscalDocument.issuance_id == issuance_id,
                FiscalDocument.document_type == "nfse_xml",
            )
        )
        pdf_document = session.scalar(
            select(FiscalDocument).where(
                FiscalDocument.issuance_id == issuance_id,
                FiscalDocument.document_type == "danfse_pdf",
            )
        )
        assert issuance is not None and xml_document is not None
        assert issuance.status == "completed"
        assert issuance.dps_number == 13
        assert issuance.nfse_number == "13"
        assert issuance.access_key == issued["access_key"]
        assert xml_document.content_bytes is None
        assert pdf_document is None


@pytest.mark.parametrize(
    ("existing", "divergent"),
    (
        (
            b"42091022239813375000106000000000001326090584825643",
            b"42091022239813375000106000000000001326090584825644",
        ),
        (b"<nNFSe>13</nNFSe>", b"<nNFSe>14</nNFSe>"),
        (b"<nDPS>13</nDPS>", b"<nDPS>14</nDPS>"),
        (
            b"<prest><CNPJ>39813375000106</CNPJ>",
            b"<prest><CNPJ>11111111000111</CNPJ>",
        ),
    ),
)
def test_document_recovery_rejects_authorized_xml_identity_divergence(
    existing: bytes,
    divergent: bytes,
    client: TestClient,
    admin_headers: dict[str, str],
    fake_gateway: FakeGateway,
    session_factory: sessionmaker[Session],
) -> None:
    configure_nfse_13_issuer(session_factory)
    item = create_contract_item(client, admin_headers, "DOCUMENT-IDENTITY")
    issued = issue(client, admin_headers, item["id"], "issue-document-identity").json()
    issuance_id = uuid.UUID(issued["id"])
    fake_gateway.document_xml_override = AUTHORIZED_NFSE_XML.replace(existing, divergent, 1)
    assert fake_gateway.document_xml_override != AUTHORIZED_NFSE_XML
    with session_factory() as session:
        documents = list(
            session.scalars(
                select(FiscalDocument).where(FiscalDocument.issuance_id == issuance_id)
            )
        )
        for document in documents:
            session.delete(document)
        session.commit()

    response = client.post(
        f"/api/v1/fiscal/issuances/{issuance_id}/documents/reconcile",
        headers=command_headers(admin_headers, "recover-identity-divergence"),
    )
    assert response.status_code == 409
    assert "não corresponde" in response.json()["detail"]
    assert fake_gateway.issue_calls == 1
    with session_factory() as session:
        issuance = session.get(FiscalIssuance, issuance_id)
        assert issuance is not None
        assert issuance.status == "completed"
        assert issuance.dps_number == 13
        assert issuance.nfse_number == "13"
        assert issuance.access_key == issued["access_key"]
        assert not list(
            session.scalars(
                select(FiscalDocument).where(FiscalDocument.issuance_id == issuance_id)
            )
        )


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
            "address_line": "Avenida Sintética",
            "address_number": "200",
            "address_complement": "Conjunto 31",
            "district": "Centro",
            "city": "São Paulo",
            "state_code": "SP",
            "municipality_code": "3550308",
            "postal_code": "01001000",
            "business_unit_ids": [str(UNIT_ID)],
            "contacts": [
                {
                    "kind": "email",
                    "label": "geral",
                    "value": f"geral-{suffix}@example.test",
                    "is_primary": False,
                },
                {
                    "kind": "email",
                    "label": "fiscal",
                    "value": f"fiscal-{suffix}@example.test",
                    "is_primary": True,
                },
                {
                    "kind": "phone",
                    "label": "fiscal",
                    "value": "+55 (47) 99999-1234",
                    "is_primary": True,
                },
            ],
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
    recurring_xml = etree.fromstring(fake_gateway.issued_xmls[-1])
    namespace = {"n": "http://www.sped.fazenda.gov.br/nfse"}
    assert recurring_xml.findtext(".//n:prest/n:email", namespaces=namespace) == (
        "financeiro@engenhariamr.com.br"
    )
    assert recurring_xml.findtext(".//n:prest/n:fone", namespaces=namespace) == "47999990001"
    assert recurring_xml.findtext(".//n:toma/n:end/n:xLgr", namespaces=namespace) == (
        "Avenida Sintética"
    )
    assert recurring_xml.findtext(".//n:toma/n:end/n:nro", namespaces=namespace) == "200"
    assert recurring_xml.findtext(".//n:toma/n:end/n:xCpl", namespaces=namespace) == (
        "Conjunto 31"
    )
    assert recurring_xml.findtext(".//n:toma/n:email", namespaces=namespace) == (
        "fiscal-services@example.test"
    )
    assert recurring_xml.findtext(".//n:toma/n:fone", namespaces=namespace) == "5547999991234"

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
    one_time_item = client.get(
        f"/api/v1/billing/items/{one_time.json()['billing_item_id']}", headers=admin_headers
    ).json()
    assert one_time_item["origin_label"] == "Serviço avulso"
    assert one_time_item["reference_type"] == "single"
    assert one_time_item["reference_label"] == "Única"
    installment = client.post(
        "/api/v1/billing/one-time",
        headers=command_headers(admin_headers, "one-time-installment-fiscal"),
        json={
            "business_unit_id": str(UNIT_ID),
            "customer_company_id": customer["id"],
            "product_service_id": str(MR_PRODUCT_ID),
            "service_name": "Laudo parcelado",
            "description": "Segunda parcela sintética",
            "reference": "OS-AVULSA-PARCELA-002",
            "service_date": date.today().isoformat(),
            "amount": "225.00",
            "issuer_establishment_id": str(ESTABLISHMENT_ID),
            "installment_number": 2,
            "installment_total": 3,
        },
    )
    assert installment.status_code == 201, installment.text
    installment_item = client.get(
        f"/api/v1/billing/items/{installment.json()['billing_item_id']}",
        headers=admin_headers,
    ).json()
    assert installment_item["reference_type"] == "installment"
    assert installment_item["reference_position"] == 2
    assert installment_item["reference_total"] == 3
    assert installment_item["reference_label"] == "Parcela 2/3"
    emitted = issue(
        client, admin_headers, one_time.json()["billing_item_id"], "issue-one-time-fiscal"
    )
    assert emitted.json()["status"] == "completed"
    assert fake_gateway.issue_calls == 2


def test_batch_issues_ready_items_and_reuses_completed_without_retransmission(
    client: TestClient,
    admin_headers: dict[str, str],
    fake_gateway: FakeGateway,
) -> None:
    items = create_contract_items(client, admin_headers, ("BATCH-A", "BATCH-B"))
    payload = {"billing_item_ids": [item["id"] for item in items]}
    first = client.post(
        "/api/v1/billing/items/issue-batch",
        headers=command_headers(admin_headers, "batch-two-ready"),
        json=payload,
    )
    assert first.status_code == 200, first.text
    assert [item["outcome"] for item in first.json()["results"]] == [
        "completed",
        "completed",
    ]
    assert fake_gateway.issue_calls == 2

    replay = client.post(
        "/api/v1/billing/items/issue-batch",
        headers=command_headers(admin_headers, "batch-two-ready"),
        json=payload,
    )
    assert replay.status_code == 200
    assert replay.json() == first.json()
    assert fake_gateway.issue_calls == 2

    reused = client.post(
        "/api/v1/billing/items/issue-batch",
        headers=command_headers(admin_headers, "batch-two-completed"),
        json=payload,
    )
    assert reused.status_code == 200, reused.text
    assert [item["outcome"] for item in reused.json()["results"]] == [
        "reused_completed",
        "reused_completed",
    ]
    assert fake_gateway.issue_calls == 2


def test_batch_continues_after_individual_fiscal_failure(
    client: TestClient,
    admin_headers: dict[str, str],
    fake_gateway: FakeGateway,
) -> None:
    items = create_contract_items(client, admin_headers, ("BATCH-FAIL", "BATCH-NEXT"))
    fake_gateway.issue_statuses = ["rejected", "completed"]
    response = client.post(
        "/api/v1/billing/items/issue-batch",
        headers=command_headers(admin_headers, "batch-continue-after-failure"),
        json={"billing_item_ids": [item["id"] for item in items]},
    )
    assert response.status_code == 200, response.text
    assert [item["outcome"] for item in response.json()["results"]] == [
        "failed",
        "completed",
    ]
    assert response.json()["results"][0]["error_code"] == "E_FISCAL_SYNTHETIC"
    assert fake_gateway.issue_calls == 2


def test_batch_preflight_rejects_duplicates_mixed_fields_and_incompatible_status(
    client: TestClient,
    admin_headers: dict[str, str],
    fake_gateway: FakeGateway,
    session_factory: sessionmaker[Session],
) -> None:
    items = create_contract_items(client, admin_headers, ("PREFLIGHT-A", "PREFLIGHT-B"))
    first_id, second_id = (uuid.UUID(item["id"]) for item in items)

    duplicate = client.post(
        "/api/v1/billing/items/issue-batch",
        headers=command_headers(admin_headers, "batch-duplicate"),
        json={"billing_item_ids": [str(first_id), str(first_id)]},
    )
    assert duplicate.status_code == 422

    with session_factory() as session:
        second = session.get(BillingItem, second_id)
        assert second is not None
        original_competence = second.competence_month
        second.competence_month = date(2026, 10, 1)
        session.commit()
    mixed_competence = client.post(
        "/api/v1/billing/items/issue-batch",
        headers=command_headers(admin_headers, "batch-mixed-competence"),
        json={"billing_item_ids": [str(first_id), str(second_id)]},
    )
    assert mixed_competence.status_code == 422

    with session_factory() as session:
        second = session.get(BillingItem, second_id)
        assert second is not None
        second.competence_month = original_competence
        second.issuer_establishment_id = SECOND_ESTABLISHMENT_ID
        session.commit()
    mixed_issuer = client.post(
        "/api/v1/billing/items/issue-batch",
        headers=command_headers(admin_headers, "batch-mixed-issuer"),
        json={"billing_item_ids": [str(first_id), str(second_id)]},
    )
    assert mixed_issuer.status_code == 422

    with session_factory() as session:
        second = session.get(BillingItem, second_id)
        assert second is not None
        second.issuer_establishment_id = ESTABLISHMENT_ID
        second.status = "blocked"
        session.commit()
    incompatible = client.post(
        "/api/v1/billing/items/issue-batch",
        headers=command_headers(admin_headers, "batch-incompatible-status"),
        json={"billing_item_ids": [str(first_id), str(second_id)]},
    )
    assert incompatible.status_code == 409
    assert fake_gateway.issue_calls == 0


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
    client: TestClient,
    admin_headers: dict[str, str],
    fake_gateway: FakeGateway,
    session_factory: sessionmaker[Session],
) -> None:
    customer = client.post(
        "/api/v1/crm/companies",
        headers=command_headers(admin_headers, "customer-incomplete-fiscal"),
        json={
            "legal_name": "Cliente Incompleto Fiscal Ltda.",
            "tax_id": "28000000000019",
            "address_line": "Rua Parcial",
            "city": "São Paulo",
            "state_code": "SP",
            "municipality_code": "3550308",
            "postal_code": "01001000",
            "business_unit_ids": [str(UNIT_ID)],
        },
    ).json()
    with session_factory() as session:
        config = session.scalar(
            select(FiscalEstablishmentConfig).where(
                FiscalEstablishmentConfig.establishment_id == ESTABLISHMENT_ID
            )
        )
        assert config is not None
        initial_number = config.next_dps_number
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
    assert "número, bairro" in blocked_issue.json()["detail"]
    with session_factory() as session:
        config = session.scalar(
            select(FiscalEstablishmentConfig).where(
                FiscalEstablishmentConfig.establishment_id == ESTABLISHMENT_ID
            )
        )
        assert config is not None and config.next_dps_number == initial_number
    assert fake_gateway.issue_calls == 0
