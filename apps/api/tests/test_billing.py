from __future__ import annotations

import hashlib
import uuid
from datetime import date, timedelta

from conftest import ESTABLISHMENT_ID, MR_PRODUCT_ID, SECOND_ESTABLISHMENT_ID, UNIT_ID
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from stk_os.models import AuditEvent, BillingItem, BillingRun, OperationalException, OutboxEvent


def command_headers(headers: dict[str, str], key: str) -> dict[str, str]:
    return {**headers, "Idempotency-Key": key}


def month_start(value: date | None = None) -> date:
    target = value or date.today()
    return target.replace(day=1)


def next_month(value: date) -> date:
    return (value.replace(day=28) + timedelta(days=4)).replace(day=1)


def create_billable_contract(
    client: TestClient,
    headers: dict[str, str],
    *,
    suffix: str,
    start_on: date,
    amount: str = "12000.00",
    pricing_model: str = "annual",
) -> tuple[dict[str, object], dict[str, object]]:
    tax_suffix = int(hashlib.sha256(suffix.encode()).hexdigest()[:8], 16) % 1_000_000
    customer_response = client.post(
        "/api/v1/crm/companies",
        headers=command_headers(headers, f"billing-company-{suffix}"),
        json={
            "legal_name": f"Cliente Faturamento {suffix} Ltda. — sintético",
            "trade_name": f"Faturamento {suffix}",
            "tax_id": f"19000000{tax_suffix:06d}",
            "address_line": "Rua Sintética",
            "address_number": "100",
            "address_complement": "Sala 2",
            "district": "Centro",
            "city": "São Paulo",
            "state_code": "SP",
            "municipality_code": "3550308",
            "postal_code": "01001000",
            "business_unit_ids": [str(UNIT_ID)],
            "contacts": [
                {
                    "kind": "email",
                    "label": "financeiro",
                    "value": f"billing-{suffix}@example.test",
                    "is_primary": True,
                }
            ],
        },
    )
    assert customer_response.status_code == 201, customer_response.text
    customer = customer_response.json()
    contract_response = client.post(
        "/api/v1/contracts",
        headers=command_headers(headers, f"billing-contract-{suffix}"),
        json={
            "business_unit_id": str(UNIT_ID),
            "customer_company_id": customer["id"],
            "internal_number": f"BILL-{suffix}",
            "signed_on": start_on.isoformat(),
            "start_date": start_on.isoformat(),
            "contract_type": "recurring_service",
        },
    )
    assert contract_response.status_code == 201, contract_response.text
    contract = contract_response.json()
    version_response = client.post(
        f"/api/v1/contracts/{contract['id']}/versions",
        headers=command_headers(headers, f"billing-version-{suffix}"),
        json={
            "effective_from": start_on.isoformat(),
            "issuer_establishment_id": str(ESTABLISHMENT_ID),
            "currency": "BRL",
            "billing_frequency": "monthly",
            "pricing_model": pricing_model,
            "amount": amount,
            "billing_installments": 12 if pricing_model == "annual" else None,
            "billing_day": 1,
            "payment_terms_days": 15,
            "invoice_description": "Serviço recorrente sintético.",
            "change_type": "initial",
            "change_reason": "Configuração inicial sintética",
            "source": "api",
            "services": [
                {
                    "product_service_id": str(MR_PRODUCT_ID),
                    "contractual_description": "Consultoria recorrente sintética",
                    "quantity": "1.000",
                    "unit_amount": amount,
                    "is_active": True,
                }
            ],
            "financial_contacts": [
                {
                    "contact_method_id": customer["contacts"][0]["id"],
                    "recipient_role": "primary",
                    "purpose": "billing",
                    "preferred_channel": "email",
                }
            ],
        },
    )
    assert version_response.status_code == 201, version_response.text
    return contract, customer


def generate(
    client: TestClient,
    headers: dict[str, str],
    *,
    key: str,
    competence: date,
) -> object:
    return client.post(
        "/api/v1/billing/runs",
        headers=command_headers(headers, key),
        json={
            "business_unit_id": str(UNIT_ID),
            "competence_month": competence.strftime("%Y-%m"),
            "run_type": "manual",
        },
    )


def test_generate_competence_is_deterministic_idempotent_and_audited(
    client: TestClient,
    admin_headers: dict[str, str],
    session_factory: sessionmaker[Session],
) -> None:
    competence = month_start()
    contract, _ = create_billable_contract(
        client, admin_headers, suffix="READY", start_on=competence
    )
    first = generate(client, admin_headers, key="billing-ready-same-key", competence=competence)
    replay = generate(client, admin_headers, key="billing-ready-same-key", competence=competence)
    business_replay = generate(
        client, admin_headers, key="billing-ready-new-key", competence=competence
    )
    assert first.status_code == replay.status_code == business_replay.status_code == 201
    assert first.json() == replay.json() == business_replay.json()
    assert first.json()["operational_timezone"] == "America/Sao_Paulo"
    assert first.json()["metrics"] == {
        "considered": 1,
        "created": 1,
        "reused": 0,
        "not_eligible": 0,
        "ready": 1,
        "blocked": 0,
    }

    items = client.get(
        f"/api/v1/billing/items?competence_month={competence:%Y-%m}",
        headers=admin_headers,
    )
    assert items.status_code == 200
    assert len(items.json()) == 1
    item = items.json()[0]
    assert item["contract_id"] == contract["id"]
    assert item["gross_amount"] == "1000.00"
    assert item["status"] == "ready"
    assert item["issuer_establishment_id"] == str(ESTABLISHMENT_ID)

    detail = client.get(f"/api/v1/billing/items/{item['id']}", headers=admin_headers)
    assert detail.status_code == 200
    payload = detail.json()
    assert payload["snapshot"]["contract_version"]["contract_amount"] == "12000.00"
    assert payload["snapshot"]["gross_amount"] == "1000"
    assert payload["snapshot_sha256"]
    assert {event["name"] for event in payload["history"]} == {
        "billing.item.created",
        "billing.item.ready.v1",
    }

    summary = client.get(
        f"/api/v1/billing/summary?competence_month={competence:%Y-%m}",
        headers=admin_headers,
    )
    assert summary.status_code == 200
    assert summary.json()["predicted_gross_amount"] == "1000.00"

    with session_factory() as session:
        assert len(session.scalars(select(BillingRun)).all()) == 1
        assert len(session.scalars(select(BillingItem)).all()) == 1
        assert session.scalar(select(AuditEvent).where(AuditEvent.resource_type == "billing_item"))
        ready_event = session.scalar(
            select(OutboxEvent).where(OutboxEvent.event_type == "billing.item.ready.v1")
        )
        assert ready_event is not None
        assert "snapshot" not in ready_event.payload


def test_same_idempotency_key_with_divergent_payload_is_rejected(
    client: TestClient, admin_headers: dict[str, str]
) -> None:
    competence = month_start()
    first = generate(client, admin_headers, key="billing-divergent-key", competence=competence)
    assert first.status_code == 201
    divergent = client.post(
        "/api/v1/billing/runs",
        headers=command_headers(admin_headers, "billing-divergent-key"),
        json={
            "business_unit_id": str(UNIT_ID),
            "competence_month": competence.strftime("%Y-%m"),
            "run_type": "scheduled",
        },
    )
    assert divergent.status_code == 409


def test_annual_residue_becomes_traceable_block_without_rounding(
    client: TestClient,
    admin_headers: dict[str, str],
    session_factory: sessionmaker[Session],
) -> None:
    competence = month_start()
    create_billable_contract(
        client,
        admin_headers,
        suffix="RESIDUE",
        start_on=competence,
        amount="100.00",
    )
    response = generate(client, admin_headers, key="billing-residue", competence=competence)
    assert response.status_code == 201
    assert response.json()["status"] == "completed_with_exceptions"
    items = client.get("/api/v1/billing/items?status=blocked", headers=admin_headers).json()
    assert len(items) == 1
    assert items[0]["gross_amount"] is None
    assert items[0]["blocking_code"] == "GATE_A_ANNUAL_ROUNDING_PENDING"
    exceptions = client.get("/api/v1/billing/exceptions", headers=admin_headers)
    assert exceptions.status_code == 200
    assert exceptions.json()[0]["billing_item_id"] == items[0]["id"]
    with session_factory() as session:
        assert session.scalar(
            select(OperationalException).where(
                OperationalException.exception_type == "billing.item.blocked"
            )
        )


def test_partial_start_is_not_eligible_and_mid_month_event_is_blocked(
    client: TestClient, admin_headers: dict[str, str]
) -> None:
    competence = month_start()
    partial_contract, _ = create_billable_contract(
        client,
        admin_headers,
        suffix="PARTIAL",
        start_on=competence + timedelta(days=1),
        pricing_model="monthly",
        amount="500.00",
    )
    active_contract, _ = create_billable_contract(
        client,
        admin_headers,
        suffix="SUSPEND",
        start_on=competence,
        pricing_model="monthly",
        amount="700.00",
    )
    suspension = client.post(
        f"/api/v1/contracts/{active_contract['id']}/suspend",
        headers=command_headers(admin_headers, "billing-suspend-mid-month"),
        json={
            "effective_on": (date.today() + timedelta(days=1)).isoformat(),
            "reason": "Suspensão sintética dentro da competência",
            "source": "api",
        },
    )
    assert suspension.status_code == 201, suspension.text
    response = generate(client, admin_headers, key="billing-partial-event", competence=competence)
    assert response.status_code == 201
    contracts = {entry["contract_id"]: entry for entry in response.json()["contracts"]}
    assert contracts[partial_contract["id"]]["outcome"] == "not_eligible"
    assert contracts[partial_contract["id"]]["reason_code"] == "CONTRACT_NOT_STARTED_FOR_FULL_MONTH"
    items = client.get("/api/v1/billing/items", headers=admin_headers).json()
    assert len(items) == 1
    assert items[0]["contract_id"] == active_contract["id"]
    assert items[0]["blocking_code"] == "GATE_A_EVENT_DURING_COMPETENCE"


def test_future_contract_change_does_not_mutate_existing_obligation(
    client: TestClient, admin_headers: dict[str, str]
) -> None:
    competence = month_start()
    contract, customer = create_billable_contract(
        client, admin_headers, suffix="IMMUTABLE", start_on=competence
    )
    run = generate(client, admin_headers, key="billing-immutable", competence=competence)
    assert run.status_code == 201
    before = client.get("/api/v1/billing/items", headers=admin_headers).json()[0]
    future = next_month(date.today())
    version = client.post(
        f"/api/v1/contracts/{contract['id']}/versions",
        headers=command_headers(admin_headers, "billing-future-version"),
        json={
            "effective_from": future.isoformat(),
            "issuer_establishment_id": str(SECOND_ESTABLISHMENT_ID),
            "currency": "BRL",
            "billing_frequency": "monthly",
            "pricing_model": "monthly",
            "amount": "2500.00",
            "billing_day": 1,
            "payment_terms_days": 15,
            "change_type": "value_change",
            "change_reason": "Mudança futura sintética",
            "source": "api",
            "services": [
                {
                    "product_service_id": str(MR_PRODUCT_ID),
                    "contractual_description": "Consultoria futura sintética",
                    "quantity": "1.000",
                    "unit_amount": "2500.00",
                    "is_active": True,
                }
            ],
            "financial_contacts": [
                {
                    "contact_method_id": customer["contacts"][0]["id"],
                    "recipient_role": "primary",
                    "purpose": "billing",
                    "preferred_channel": "email",
                }
            ],
        },
    )
    assert version.status_code == 201, version.text
    after = client.get(f"/api/v1/billing/items/{before['id']}", headers=admin_headers).json()
    assert after["gross_amount"] == "1000.00"
    assert after["snapshot_sha256"] == before["snapshot_sha256"]
    assert after["contract_version_number"] == 1
    future_run = generate(client, admin_headers, key="billing-future-competence", competence=future)
    assert future_run.status_code == 201
    future_items = client.get(
        f"/api/v1/billing/items?competence_month={future:%Y-%m}", headers=admin_headers
    ).json()
    assert len(future_items) == 1
    assert future_items[0]["contract_version_number"] == 2
    assert future_items[0]["issuer_establishment_id"] == str(SECOND_ESTABLISHMENT_ID)
    assert future_items[0]["gross_amount"] == "2500.00"


def test_suspension_resume_and_termination_control_full_month_eligibility(
    client: TestClient, admin_headers: dict[str, str]
) -> None:
    start = month_start()
    contract, _ = create_billable_contract(
        client,
        admin_headers,
        suffix="LIFECYCLE",
        start_on=start,
        pricing_model="monthly",
        amount="900.00",
    )
    suspended_month = next_month(start)
    resumed_month = next_month(suspended_month)
    terminated_month = next_month(resumed_month)
    commands = (
        ("suspend", suspended_month, "billing-lifecycle-suspend"),
        ("resume", resumed_month, "billing-lifecycle-resume"),
        ("terminate", terminated_month, "billing-lifecycle-terminate"),
    )
    for action, effective_on, key in commands:
        response = client.post(
            f"/api/v1/contracts/{contract['id']}/{action}",
            headers=command_headers(admin_headers, key),
            json={
                "effective_on": effective_on.isoformat(),
                "reason": f"Evento sintético de {action}",
                "source": "api",
            },
        )
        assert response.status_code == 201, response.text

    suspended = generate(
        client, admin_headers, key="billing-lifecycle-suspended", competence=suspended_month
    )
    resumed = generate(
        client, admin_headers, key="billing-lifecycle-resumed", competence=resumed_month
    )
    terminated = generate(
        client, admin_headers, key="billing-lifecycle-terminated", competence=terminated_month
    )
    assert suspended.status_code == resumed.status_code == terminated.status_code == 201
    assert suspended.json()["metrics"]["not_eligible"] == 1
    assert resumed.json()["metrics"]["ready"] == 1
    assert terminated.json()["metrics"]["not_eligible"] == 1


def test_billing_review_and_reprocess_require_specific_capabilities(
    client: TestClient,
    admin_headers: dict[str, str],
    service_headers: dict[str, str],
) -> None:
    competence = month_start()
    response = generate(
        client, service_headers, key="billing-service-generate", competence=competence
    )
    assert response.status_code == 201
    run_id = response.json()["id"]
    assert client.get("/api/v1/billing/exceptions", headers=service_headers).status_code == 403
    assert (
        client.post(
            f"/api/v1/billing/runs/{run_id}/reprocess",
            headers=command_headers(service_headers, "billing-service-reprocess"),
        ).status_code
        == 403
    )
    approved = client.post(
        f"/api/v1/billing/runs/{run_id}/reprocess",
        headers=command_headers(admin_headers, "billing-admin-reprocess"),
    )
    replay = client.post(
        f"/api/v1/billing/runs/{run_id}/reprocess",
        headers=command_headers(admin_headers, "billing-admin-reprocess"),
    )
    assert approved.status_code == replay.status_code == 200
    assert approved.json() == replay.json()


def test_competence_requires_explicit_civil_month(
    client: TestClient, admin_headers: dict[str, str]
) -> None:
    response = client.post(
        "/api/v1/billing/runs",
        headers=command_headers(admin_headers, f"billing-invalid-{uuid.uuid4()}"),
        json={"business_unit_id": str(UNIT_ID), "competence_month": "2026-8"},
    )
    assert response.status_code == 422
