from __future__ import annotations

import uuid
from datetime import date, timedelta

from conftest import (
    ESTABLISHMENT_ID,
    LAB_UNIT_ID,
    MR_PRODUCT_ID,
    ORGANIZATION_ID,
    SECOND_ESTABLISHMENT_ID,
    UNIT_ID,
)
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from stk_os.models import (
    Actor,
    ActorRole,
    AuditEvent,
    ContractVersion,
    ContractVersionService,
    Permission,
    Role,
    RolePermission,
    User,
)
from stk_os.security import hash_secret


def command_headers(headers: dict[str, str], key: str) -> dict[str, str]:
    return {**headers, "Idempotency-Key": key}


def create_customer(client: TestClient, headers: dict[str, str], suffix: str) -> dict[str, object]:
    response = client.post(
        "/api/v1/crm/companies",
        headers=command_headers(headers, f"company-{suffix}"),
        json={
            "legal_name": f"Cliente Contratual {suffix} Ltda. — sintético",
            "trade_name": f"Cliente {suffix}",
            "business_unit_ids": [str(UNIT_ID)],
            "contacts": [
                {
                    "kind": "email",
                    "label": "financeiro",
                    "value": f"financeiro-{suffix}@example.test",
                    "is_primary": True,
                }
            ],
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def create_contract(
    client: TestClient,
    headers: dict[str, str],
    *,
    suffix: str,
    start_date: date | None = None,
) -> tuple[dict[str, object], dict[str, object]]:
    customer = create_customer(client, headers, suffix)
    response = client.post(
        "/api/v1/contracts",
        headers=command_headers(headers, f"contract-{suffix}"),
        json={
            "business_unit_id": str(UNIT_ID),
            "customer_company_id": customer["id"],
            "internal_number": f"CT-{suffix}",
            "signed_on": (start_date or date.today()).isoformat(),
            "start_date": (start_date or date.today()).isoformat(),
            "contract_type": "recurring_service",
            "controlled_notes": "Observação sintética controlada.",
        },
    )
    assert response.status_code == 201, response.text
    return response.json(), customer


def version_payload(
    contact_id: str,
    *,
    effective_from: date,
    change_type: str = "initial",
    amount: str = "12000.00",
    issuer_id: uuid.UUID = ESTABLISHMENT_ID,
    services: list[dict[str, object]] | None = None,
) -> dict[str, object]:
    return {
        "effective_from": effective_from.isoformat(),
        "issuer_establishment_id": str(issuer_id),
        "currency": "BRL",
        "billing_frequency": "monthly",
        "pricing_model": "annual",
        "amount": amount,
        "billing_installments": 12,
        "billing_day": 1,
        "payment_terms_days": 15,
        "invoice_description": "Serviços técnicos sintéticos conforme contrato.",
        "adjustment_reference": "Índice contratual configurável",
        "adjustment_frequency": "annual",
        "adjustment_base_date": effective_from.isoformat(),
        "adjustment_source": "not_applied",
        "change_type": change_type,
        "change_reason": f"Motivo sintético para {change_type}",
        "source": "api",
        "services": services
        or [
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
                "contact_method_id": contact_id,
                "recipient_role": "primary",
                "purpose": "billing",
                "preferred_channel": "email",
            }
        ],
    }


def publish_version(
    client: TestClient,
    headers: dict[str, str],
    contract_id: str,
    contact_id: str,
    *,
    key: str,
    effective_from: date,
    path: str = "versions",
    **changes: object,
) -> dict[str, object]:
    response = client.post(
        f"/api/v1/contracts/{contract_id}/{path}",
        headers=command_headers(headers, key),
        json=version_payload(contact_id, effective_from=effective_from, **changes),
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_contract_and_first_version_are_idempotent_decimal_and_audited(
    client: TestClient,
    admin_headers: dict[str, str],
    session_factory: sessionmaker[Session],
) -> None:
    contract, customer = create_contract(client, admin_headers, suffix="A")
    assert contract["administrative_status"] == "draft"
    assert contract["current_version_number"] is None
    contact_id = customer["contacts"][0]["id"]

    payload = version_payload(contact_id, effective_from=date.today())
    headers = command_headers(admin_headers, "version-A-initial")
    first = client.post(
        f"/api/v1/contracts/{contract['id']}/versions", headers=headers, json=payload
    )
    replay = client.post(
        f"/api/v1/contracts/{contract['id']}/versions", headers=headers, json=payload
    )
    assert first.status_code == replay.status_code == 201
    assert first.json() == replay.json()
    assert first.json()["amount"] == "12000.00"
    assert first.json()["configuration_sha256"]
    assert first.json()["temporal_status"] == "current"

    detail = client.get(f"/api/v1/contracts/{contract['id']}", headers=admin_headers)
    assert detail.status_code == 200
    assert detail.json()["administrative_status"] == "active"
    assert detail.json()["versions"][0]["services"][0]["product_name"]
    assert detail.json()["versions"][0]["financial_contacts"][0]["contact_value"].endswith(
        "@example.test"
    )

    with session_factory() as session:
        actions = set(
            session.scalars(
                select(AuditEvent.action).where(
                    AuditEvent.resource_id.in_([uuid.UUID(contract["id"])])
                )
            ).all()
        )
        version_audits = session.scalars(
            select(AuditEvent).where(AuditEvent.action == "contract.version_published")
        ).all()
    assert "contract.created" in actions
    assert len(version_audits) == 1
    assert version_audits[0].after_state["amount"] == "12000.00"


def test_future_versions_preserve_history_and_reconstruct_any_date(
    client: TestClient, admin_headers: dict[str, str]
) -> None:
    today = date.today()
    contract, customer = create_contract(client, admin_headers, suffix="B")
    contact_id = customer["contacts"][0]["id"]
    publish_version(
        client,
        admin_headers,
        contract["id"],
        contact_id,
        key="version-B-1",
        effective_from=today,
    )
    value_version = publish_version(
        client,
        admin_headers,
        contract["id"],
        contact_id,
        key="version-B-2",
        effective_from=today + timedelta(days=1),
        path="schedule",
        change_type="value_change",
        amount="13200.00",
    )
    added_services = [
        {
            "product_service_id": str(MR_PRODUCT_ID),
            "contractual_description": "Consultoria recorrente sintética",
            "quantity": "1.000",
            "unit_amount": "13200.00",
            "is_active": True,
        },
        {
            "product_service_id": None,
            "contractual_description": "Projeto adicional sintético",
            "quantity": "2.000",
            "unit_amount": "500.00",
            "is_active": True,
        },
    ]
    publish_version(
        client,
        admin_headers,
        contract["id"],
        contact_id,
        key="version-B-3",
        effective_from=today + timedelta(days=2),
        path="schedule",
        change_type="service_change",
        amount="13200.00",
        services=added_services,
    )
    excluded_services = [
        {**added_services[0], "is_active": False},
        added_services[1],
    ]
    publish_version(
        client,
        admin_headers,
        contract["id"],
        contact_id,
        key="version-B-4",
        effective_from=today + timedelta(days=3),
        path="schedule",
        change_type="service_change",
        amount="13200.00",
        services=excluded_services,
    )
    issuer_version = publish_version(
        client,
        admin_headers,
        contract["id"],
        contact_id,
        key="version-B-5",
        effective_from=today + timedelta(days=4),
        path="schedule",
        change_type="issuer_change",
        amount="13200.00",
        issuer_id=SECOND_ESTABLISHMENT_ID,
        services=excluded_services,
    )
    assert value_version["amount"] == "13200.00"
    assert issuer_version["issuer_establishment_id"] == str(SECOND_ESTABLISHMENT_ID)

    original = client.get(
        f"/api/v1/contracts/{contract['id']}/configuration?date={today.isoformat()}",
        headers=admin_headers,
    )
    changed = client.get(
        f"/api/v1/contracts/{contract['id']}/configuration?date="
        f"{(today + timedelta(days=4)).isoformat()}",
        headers=admin_headers,
    )
    assert original.status_code == changed.status_code == 200
    assert original.json()["version"]["version_number"] == 1
    assert original.json()["version"]["amount"] == "12000.00"
    assert changed.json()["version"]["version_number"] == 5
    catalog_service = next(
        item
        for item in changed.json()["version"]["services"]
        if item["product_service_id"] == str(MR_PRODUCT_ID)
    )
    assert catalog_service["is_active"] is False

    history = client.get(
        f"/api/v1/contracts/{contract['id']}/history", headers=admin_headers
    ).json()
    assert [item["version_number"] for item in history["versions"]] == [1, 2, 3, 4, 5]
    assert history["versions"][0]["effective_until"] == today.isoformat()
    assert (
        history["versions"][0]["configuration_sha256"]
        != history["versions"][1]["configuration_sha256"]
    )


def test_overlap_and_historical_overwrite_are_rejected(
    client: TestClient, admin_headers: dict[str, str]
) -> None:
    today = date.today()
    contract, customer = create_contract(client, admin_headers, suffix="C")
    contact_id = customer["contacts"][0]["id"]
    publish_version(
        client,
        admin_headers,
        contract["id"],
        contact_id,
        key="version-C-1",
        effective_from=today,
    )
    publish_version(
        client,
        admin_headers,
        contract["id"],
        contact_id,
        key="version-C-2",
        effective_from=today + timedelta(days=2),
        change_type="value_change",
        amount="14000.00",
    )
    overlap = client.post(
        f"/api/v1/contracts/{contract['id']}/versions",
        headers=command_headers(admin_headers, "version-C-overlap"),
        json=version_payload(
            contact_id,
            effective_from=today + timedelta(days=2),
            change_type="conditions_change",
        ),
    )
    overwrite = client.patch(
        f"/api/v1/contracts/{contract['id']}/versions/unknown",
        headers=command_headers(admin_headers, "version-C-overwrite"),
        json={"amount": "1.00"},
    )
    assert overlap.status_code == 409
    assert overwrite.status_code in {404, 405}


def test_suspend_resume_terminate_and_renewal_are_explicit(
    client: TestClient, admin_headers: dict[str, str]
) -> None:
    today = date.today()
    contract, customer = create_contract(client, admin_headers, suffix="D")
    contact_id = customer["contacts"][0]["id"]
    publish_version(
        client,
        admin_headers,
        contract["id"],
        contact_id,
        key="version-D-1",
        effective_from=today,
    )
    renewal = client.post(
        f"/api/v1/contracts/{contract['id']}/renew",
        headers=command_headers(admin_headers, "renew-contract-D"),
        json=version_payload(
            contact_id,
            effective_from=today + timedelta(days=1),
            change_type="renewal",
            amount="12500.00",
        ),
    )
    assert renewal.status_code == 201, renewal.text
    assert renewal.json()["operational_events"][0]["event_type"] == "renewed"

    for index, (path, event_type) in enumerate(
        (("suspend", "suspended"), ("resume", "resumed"), ("terminate", "terminated")),
        start=2,
    ):
        response = client.post(
            f"/api/v1/contracts/{contract['id']}/{path}",
            headers=command_headers(admin_headers, f"{path}-D"),
            json={
                "effective_on": (today + timedelta(days=index)).isoformat(),
                "reason": f"Motivo sintético de {path}",
                "source": "api",
            },
        )
        assert response.status_code == 201, response.text
        assert response.json()["event_type"] == event_type

    suspended = client.get(
        f"/api/v1/contracts/{contract['id']}/configuration?date="
        f"{(today + timedelta(days=2)).isoformat()}",
        headers=admin_headers,
    )
    resumed = client.get(
        f"/api/v1/contracts/{contract['id']}/configuration?date="
        f"{(today + timedelta(days=3)).isoformat()}",
        headers=admin_headers,
    )
    terminated = client.get(
        f"/api/v1/contracts/{contract['id']}/configuration?date="
        f"{(today + timedelta(days=4)).isoformat()}",
        headers=admin_headers,
    )
    assert suspended.json()["operational_state"] == "suspended"
    assert resumed.json()["operational_state"] == "active"
    assert terminated.json()["operational_state"] == "terminated"


def test_authorization_and_unit_scope_isolate_contracts(
    client: TestClient,
    admin_headers: dict[str, str],
    service_headers: dict[str, str],
    session_factory: sessionmaker[Session],
) -> None:
    contract, _ = create_contract(client, admin_headers, suffix="E")
    denied = client.post(
        "/api/v1/contracts",
        headers=command_headers(service_headers, "service-create-contract"),
        json={
            "business_unit_id": str(UNIT_ID),
            "customer_company_id": contract["customer_company_id"],
            "internal_number": "CT-DENIED",
            "start_date": date.today().isoformat(),
            "contract_type": "other",
        },
    )
    assert denied.status_code == 403
    assert client.get("/api/v1/contracts", headers=service_headers).status_code == 200

    restricted_actor_id = uuid.uuid4()
    with session_factory() as session, session.begin():
        permission = session.scalar(select(Permission).where(Permission.code == "contracts:read"))
        role = Role(
            organization_id=ORGANIZATION_ID,
            code="lab-contract-reader",
            name="Leitor de contratos Lab",
        )
        actor = Actor(
            id=restricted_actor_id,
            organization_id=ORGANIZATION_ID,
            kind="user",
            display_name="Leitor Lab sintético",
        )
        session.add_all([role, actor])
        session.flush()
        session.add_all(
            [
                User(
                    actor_id=actor.id,
                    email="lab-reader@example.test",
                    password_hash=hash_secret("synthetic-reader-password"),
                ),
                ActorRole(actor_id=actor.id, role_id=role.id, business_unit_id=LAB_UNIT_ID),
                RolePermission(role_id=role.id, permission_id=permission.id),
            ]
        )
    login = client.post(
        "/api/v1/auth/token",
        json={"email": "lab-reader@example.test", "password": "synthetic-reader-password"},
    )
    restricted = {"Authorization": f"Bearer {login.json()['access_token']}"}
    assert client.get("/api/v1/contracts", headers=restricted).json() == []
    assert client.get(f"/api/v1/contracts/{contract['id']}", headers=restricted).status_code == 404


def test_direct_mutation_of_published_version_does_not_exist(
    client: TestClient,
    admin_headers: dict[str, str],
    session_factory: sessionmaker[Session],
) -> None:
    contract, customer = create_contract(client, admin_headers, suffix="F")
    version = publish_version(
        client,
        admin_headers,
        contract["id"],
        customer["contacts"][0]["id"],
        key="version-F-1",
        effective_from=date.today(),
    )
    with session_factory() as session:
        stored = session.get(ContractVersion, uuid.UUID(version["id"]))
        service_count = len(
            session.scalars(
                select(ContractVersionService).where(
                    ContractVersionService.contract_version_id == stored.id
                )
            ).all()
        )
    assert stored.configuration_sha256 == version["configuration_sha256"]
    assert service_count == 1
    response = client.patch(
        f"/api/v1/contracts/{contract['id']}/versions/{version['id']}",
        headers=command_headers(admin_headers, "forbidden-version-edit"),
        json={"amount": "0.01"},
    )
    assert response.status_code in {404, 405}
