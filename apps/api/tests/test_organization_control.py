from __future__ import annotations

from conftest import LAB_UNIT_ID, UNIT_ID
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from stk_os.models import AuditEvent, IdempotencyKey, OutboxEvent


def test_hierarchy_is_explicit(client: TestClient, admin_headers: dict[str, str]) -> None:
    response = client.get("/api/v1/organization", headers=admin_headers)
    assert response.status_code == 200
    payload = response.json()
    assert payload["legal_entities"][0]["establishments"][0]["business_units"][0]["code"] == "mr"
    assert payload["legal_entities"][0]["tax_id"] == "12345678000190"
    assert payload["legal_entities"][0]["establishments"][0]["tax_id"] == "12345678000190"


def test_legal_entity_and_fiscal_establishment_crud(
    client: TestClient, admin_headers: dict[str, str]
) -> None:
    created_entity = client.post(
        "/api/v1/organization/legal-entities",
        headers=admin_headers,
        json={
            "registered_name": "Nova Pessoa Jurídica Ltda.",
            "trade_name": "Nova Empresa",
            "tax_id": "11.222.333/0001-81",
            "email": "contato@nova-empresa.example.test",
            "phone": "+55 47 3333-1111",
            "status": "active",
        },
    )
    assert created_entity.status_code == 201, created_entity.text
    entity = created_entity.json()
    assert entity["tax_id"] == "11222333000181"
    assert entity["email"] == "contato@nova-empresa.example.test"
    assert entity["phone"] == "+55 47 3333-1111"
    assert entity["establishments"] == []

    updated_entity = client.patch(
        f"/api/v1/organization/legal-entities/{entity['id']}",
        headers=admin_headers,
        json={
            "registered_name": "Nova Pessoa Jurídica S.A.",
            "trade_name": "Nova Empresa Editada",
            "tax_id": "11.222.333/0001-81",
            "status": "inactive",
        },
    )
    assert updated_entity.status_code == 200, updated_entity.text
    assert updated_entity.json()["registered_name"] == "Nova Pessoa Jurídica S.A."
    assert updated_entity.json()["status"] == "inactive"
    assert updated_entity.json()["email"] == "contato@nova-empresa.example.test"
    assert updated_entity.json()["phone"] == "+55 47 3333-1111"

    edited_contacts = client.patch(
        f"/api/v1/organization/legal-entities/{entity['id']}",
        headers=admin_headers,
        json={
            "registered_name": "Nova Pessoa Jurídica S.A.",
            "trade_name": "Nova Empresa Editada",
            "tax_id": "11.222.333/0001-81",
            "email": "geral@nova-empresa.example.test",
            "phone": "+55 47 3333-2222",
            "status": "inactive",
        },
    )
    assert edited_contacts.status_code == 200, edited_contacts.text
    assert edited_contacts.json()["email"] == "geral@nova-empresa.example.test"
    assert edited_contacts.json()["phone"] == "+55 47 3333-2222"

    created_establishment = client.post(
        f"/api/v1/organization/legal-entities/{entity['id']}/fiscal-establishments",
        headers=admin_headers,
        json={
            "name": "Matriz Nova Empresa",
            "tax_id": "22.333.444/0001-63",
            "email": "fiscal@nova-empresa.example.test",
            "phone": "+55 47 3333-4444",
            "kind": "headquarters",
            "status": "active",
            "business_unit_ids": [str(LAB_UNIT_ID)],
        },
    )
    assert created_establishment.status_code == 201, created_establishment.text
    establishment = created_establishment.json()
    assert establishment["tax_id"] == "22333444000163"
    assert establishment["email"] == "fiscal@nova-empresa.example.test"
    assert establishment["phone"] == "+55 47 3333-4444"
    assert [unit["id"] for unit in establishment["business_units"]] == [str(LAB_UNIT_ID)]

    updated_establishment = client.patch(
        f"/api/v1/organization/fiscal-establishments/{establishment['id']}",
        headers=admin_headers,
        json={
            "name": "Matriz Nova Empresa Editada",
            "tax_id": "22.333.444/0001-63",
            "email": "financeiro@nova-empresa.example.test",
            "phone": "+55 47 3333-5555",
            "kind": "headquarters",
            "status": "inactive",
            "business_unit_ids": [str(LAB_UNIT_ID)],
        },
    )
    assert updated_establishment.status_code == 200, updated_establishment.text
    assert updated_establishment.json()["name"] == "Matriz Nova Empresa Editada"
    assert updated_establishment.json()["status"] == "inactive"
    assert updated_establishment.json()["email"] == "financeiro@nova-empresa.example.test"
    assert updated_establishment.json()["phone"] == "+55 47 3333-5555"

    hierarchy = client.get("/api/v1/organization", headers=admin_headers).json()
    stored = next(item for item in hierarchy["legal_entities"] if item["id"] == entity["id"])
    assert stored["email"] == "geral@nova-empresa.example.test"
    assert stored["phone"] == "+55 47 3333-2222"
    assert stored["email"] != stored["establishments"][0]["email"]
    assert stored["establishments"][0]["business_units"][0]["id"] == str(LAB_UNIT_ID)


def test_organization_writes_validate_scope_and_unique_cnpj(
    client: TestClient,
    admin_headers: dict[str, str],
    service_headers: dict[str, str],
) -> None:
    duplicate = client.post(
        "/api/v1/organization/legal-entities",
        headers=admin_headers,
        json={
            "registered_name": "Duplicada",
            "tax_id": "12.345.678/0001-90",
            "status": "active",
        },
    )
    forbidden = client.post(
        "/api/v1/organization/legal-entities",
        headers=service_headers,
        json={"registered_name": "Sem permissão", "status": "active"},
    )
    invalid = client.post(
        "/api/v1/organization/legal-entities",
        headers=admin_headers,
        json={"registered_name": "CNPJ inválido", "tax_id": "123", "status": "active"},
    )
    assert duplicate.status_code == 409
    assert forbidden.status_code == 403
    assert invalid.status_code == 422


def test_authenticated_action_is_atomic_and_idempotent(
    client: TestClient,
    admin_headers: dict[str, str],
    session_factory: sessionmaker[Session],
) -> None:
    headers = {**admin_headers, "Idempotency-Key": "rename-mr-once"}
    first = client.patch(
        f"/api/v1/organization/business-units/{UNIT_ID}",
        headers=headers,
        json={"name": "MR — Fundação validada"},
    )
    replay = client.patch(
        f"/api/v1/organization/business-units/{UNIT_ID}",
        headers=headers,
        json={"name": "MR — Fundação validada"},
    )
    assert first.status_code == 200
    assert replay.status_code == 200
    assert replay.json() == first.json()
    assert first.headers["X-Correlation-ID"]
    with session_factory() as session:
        assert session.scalar(select(func.count()).select_from(AuditEvent)) == 1
        assert session.scalar(select(func.count()).select_from(OutboxEvent)) == 1
        assert session.scalar(select(func.count()).select_from(IdempotencyKey)) == 1


def test_idempotency_key_cannot_change_intent(
    client: TestClient, admin_headers: dict[str, str]
) -> None:
    headers = {**admin_headers, "Idempotency-Key": "same-key-different-body"}
    first = client.patch(
        f"/api/v1/organization/business-units/{UNIT_ID}",
        headers=headers,
        json={"name": "Primeiro nome"},
    )
    second = client.patch(
        f"/api/v1/organization/business-units/{UNIT_ID}",
        headers=headers,
        json={"name": "Segundo nome"},
    )
    assert first.status_code == 200
    assert second.status_code == 409


def test_service_account_cannot_change_organization(
    client: TestClient, service_headers: dict[str, str]
) -> None:
    response = client.patch(
        f"/api/v1/organization/business-units/{UNIT_ID}",
        headers={**service_headers, "Idempotency-Key": "service-not-authorized"},
        json={"name": "Não autorizado"},
    )
    assert response.status_code == 403
