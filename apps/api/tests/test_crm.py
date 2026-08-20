from __future__ import annotations

from datetime import UTC, datetime, timedelta

from conftest import (
    LAB_UNIT_ID,
    MR_LOSS_REASON_ID,
    MR_PIPELINE_ID,
    MR_PRODUCT_ID,
    MR_STAGE_LEAD_ID,
    MR_STAGE_PROPOSAL_ID,
    SOURCE_ID,
    STELLI_UNIT_ID,
    UNIT_ID,
)
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from stk_os.models import (
    AuditEvent,
    CrmImportRow,
    OpportunityStageHistory,
    OutboxEvent,
    Person,
    PersonBusinessUnit,
)


def command_headers(headers: dict[str, str], key: str) -> dict[str, str]:
    return {**headers, "Idempotency-Key": key}


def create_person(
    client: TestClient, headers: dict[str, str], *, key: str = "create-person-001"
) -> dict[str, object]:
    response = client.post(
        "/api/v1/crm/people",
        headers=command_headers(headers, key),
        json={
            "full_name": "Pessoa CRM sintética",
            "tax_id": "111.222.333-44",
            "city": "Cidade teste",
            "state_code": "sp",
            "business_unit_ids": [str(UNIT_ID), str(LAB_UNIT_ID), str(STELLI_UNIT_ID)],
            "lead_source_id": str(SOURCE_ID),
            "contacts": [
                {
                    "kind": "email",
                    "value": "crm.person2@example.test",
                    "is_primary": True,
                }
            ],
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def create_company(client: TestClient, headers: dict[str, str]) -> dict[str, object]:
    response = client.post(
        "/api/v1/crm/companies",
        headers=command_headers(headers, "create-company-001"),
        json={
            "legal_name": "Empresa CRM sintética Ltda.",
            "trade_name": "Empresa sintética",
            "tax_id": "11.222.333/0001-44",
            "business_unit_ids": [str(UNIT_ID), str(STELLI_UNIT_ID)],
            "lead_source_id": str(SOURCE_ID),
            "contacts": [{"kind": "phone", "value": "+55 11 99999-0000"}],
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def create_opportunity(
    client: TestClient,
    headers: dict[str, str],
    *,
    person_id: str,
    company_id: str,
) -> dict[str, object]:
    response = client.post(
        "/api/v1/crm/opportunities",
        headers=command_headers(headers, "create-opportunity-001"),
        json={
            "business_unit_id": str(UNIT_ID),
            "pipeline_id": str(MR_PIPELINE_ID),
            "stage_id": str(MR_STAGE_LEAD_ID),
            "person_ids": [person_id],
            "company_id": company_id,
            "title": "Oportunidade sintética",
            "value": "1250.50",
            "lead_source_id": str(SOURCE_ID),
            "product_service_ids": [str(MR_PRODUCT_ID)],
            "next_action_title": "Realizar contato de teste",
            "next_action_due_at": (datetime.now(UTC) + timedelta(days=2)).isoformat(),
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_reference_data_contains_three_units_and_corrected_pipelines(
    client: TestClient, admin_headers: dict[str, str]
) -> None:
    response = client.get("/api/v1/crm/reference-data", headers=admin_headers)
    assert response.status_code == 200
    payload = response.json()
    assert {item["code"] for item in payload["business_units"]} == {"mr", "stk-lab", "stelli"}
    assert all(
        stage["code"] not in {"won", "lost"}
        for pipeline in payload["pipelines"]
        for stage in pipeline["stages"]
    )


def test_canonical_person_and_company_are_multiunit_and_idempotent(
    client: TestClient,
    admin_headers: dict[str, str],
    session_factory: sessionmaker[Session],
) -> None:
    person = create_person(client, admin_headers)
    replay = create_person(client, admin_headers)
    assert replay == person
    assert set(person["business_unit_ids"]) == {str(UNIT_ID), str(LAB_UNIT_ID), str(STELLI_UNIT_ID)}
    company = create_company(client, admin_headers)
    assert set(company["business_unit_ids"]) == {str(UNIT_ID), str(STELLI_UNIT_ID)}
    link = client.post(
        "/api/v1/crm/relationships/person-company",
        headers=command_headers(admin_headers, "link-person-company-001"),
        json={
            "person_id": person["id"],
            "company_id": company["id"],
            "role": "responsável técnico",
            "is_primary": True,
        },
    )
    assert link.status_code == 201
    with session_factory() as session:
        assert session.scalar(select(func.count()).select_from(Person)) == 1
        assert session.scalar(select(func.count()).select_from(PersonBusinessUnit)) == 3


def test_opportunity_kanban_stage_history_next_action_and_360(
    client: TestClient,
    admin_headers: dict[str, str],
    session_factory: sessionmaker[Session],
) -> None:
    person = create_person(client, admin_headers)
    company = create_company(client, admin_headers)
    opportunity = create_opportunity(
        client,
        admin_headers,
        person_id=str(person["id"]),
        company_id=str(company["id"]),
    )
    assert opportunity["next_action"]["title"] == "Realizar contato de teste"
    assert opportunity["product_names"] == ["Serviço mr sintético"]
    kanban = client.get(f"/api/v1/crm/kanban/{MR_PIPELINE_ID}", headers=admin_headers)
    assert kanban.status_code == 200
    assert kanban.json()["columns"][0]["opportunities"][0]["id"] == opportunity["id"]

    moved = client.patch(
        f"/api/v1/crm/opportunities/{opportunity['id']}/stage",
        headers=command_headers(admin_headers, "move-opportunity-001"),
        json={"stage_id": str(MR_STAGE_PROPOSAL_ID), "source": "ui", "note": "Arraste"},
    )
    replay = client.patch(
        f"/api/v1/crm/opportunities/{opportunity['id']}/stage",
        headers=command_headers(admin_headers, "move-opportunity-001"),
        json={"stage_id": str(MR_STAGE_PROPOSAL_ID), "source": "ui", "note": "Arraste"},
    )
    assert moved.status_code == 200
    assert replay.json() == moved.json()

    activity = client.post(
        "/api/v1/crm/activities",
        headers=command_headers(admin_headers, "activity-001"),
        json={
            "business_unit_id": str(UNIT_ID),
            "opportunity_id": opportunity["id"],
            "person_id": person["id"],
            "company_id": company["id"],
            "activity_type": "meeting",
            "occurred_at": datetime.now(UTC).isoformat(),
            "summary": "Reunião comercial sintética",
            "origin": "test",
        },
    )
    assert activity.status_code == 201
    view = client.get(f"/api/v1/crm/people/{person['id']}/360", headers=admin_headers)
    assert view.status_code == 200
    assert view.json()["opportunities"][0]["id"] == opportunity["id"]
    assert view.json()["activities"][0]["summary"] == "Reunião comercial sintética"
    search = client.get("/api/v1/crm/search?q=crm.person", headers=admin_headers)
    assert search.status_code == 200
    assert search.json()[0]["resource_type"] == "person"
    email_with_digit = client.get("/api/v1/crm/search?q=crm.person2", headers=admin_headers)
    assert email_with_digit.status_code == 200
    assert email_with_digit.json()[0]["resource_type"] == "person"
    with session_factory() as session:
        assert session.scalar(select(func.count()).select_from(OpportunityStageHistory)) == 2
        assert session.scalar(select(func.count()).select_from(AuditEvent)) >= 5
        assert session.scalar(select(func.count()).select_from(OutboxEvent)) >= 5


def test_lost_requires_reason_and_terminal_opportunity_cannot_move(
    client: TestClient, admin_headers: dict[str, str]
) -> None:
    person = create_person(client, admin_headers)
    company = create_company(client, admin_headers)
    opportunity = create_opportunity(
        client,
        admin_headers,
        person_id=str(person["id"]),
        company_id=str(company["id"]),
    )
    missing_reason = client.patch(
        f"/api/v1/crm/opportunities/{opportunity['id']}/status",
        headers=command_headers(admin_headers, "lose-without-reason"),
        json={"status": "lost"},
    )
    assert missing_reason.status_code == 422
    lost = client.patch(
        f"/api/v1/crm/opportunities/{opportunity['id']}/status",
        headers=command_headers(admin_headers, "lose-with-reason"),
        json={"status": "lost", "loss_reason_id": str(MR_LOSS_REASON_ID)},
    )
    assert lost.status_code == 200
    assert lost.json()["status"] == "lost"
    blocked = client.patch(
        f"/api/v1/crm/opportunities/{opportunity['id']}/stage",
        headers=command_headers(admin_headers, "move-closed-opportunity"),
        json={"stage_id": str(MR_STAGE_PROPOSAL_ID)},
    )
    assert blocked.status_code == 409


def test_small_import_is_repeatable_auditable_and_does_not_store_payload(
    client: TestClient,
    admin_headers: dict[str, str],
    service_headers: dict[str, str],
    session_factory: sessionmaker[Session],
) -> None:
    payload = {
        "source_label": "planilha sintética de teste",
        "rows": [
            {
                "entity_type": "person",
                "person": {
                    "full_name": "Importada sintética",
                    "tax_id": "55566677788",
                    "email": "import@example.test",
                    "business_unit_ids": [str(UNIT_ID), str(LAB_UNIT_ID)],
                },
            },
            {
                "entity_type": "person",
                "person": {
                    "full_name": "Mesmo documento sintético",
                    "tax_id": "55566677788",
                    "business_unit_ids": [str(STELLI_UNIT_ID)],
                },
            },
            {
                "entity_type": "company",
                "company": {
                    "legal_name": "Contato ambíguo sintético",
                    "email": "import@example.test",
                    "business_unit_ids": [str(UNIT_ID)],
                },
            },
        ],
    }
    denied = client.post(
        "/api/v1/crm/imports",
        headers=command_headers(service_headers, "service-import-denied"),
        json=payload,
    )
    assert denied.status_code == 403
    imported = client.post(
        "/api/v1/crm/imports",
        headers=command_headers(admin_headers, "small-import-001"),
        json=payload,
    )
    replay = client.post(
        "/api/v1/crm/imports",
        headers=command_headers(admin_headers, "small-import-001"),
        json=payload,
    )
    assert imported.status_code == 201, imported.text
    assert replay.json() == imported.json()
    assert imported.json()["created_rows"] == 1
    assert imported.json()["matched_rows"] == 1
    assert imported.json()["failed_rows"] == 1
    assert imported.json()["rows"][2]["error_code"] == "manual_review_contact_match"
    with session_factory() as session:
        rows = session.scalars(select(CrmImportRow).order_by(CrmImportRow.row_number)).all()
        assert len(rows) == 3
        assert all(len(row.input_sha256) == 64 for row in rows)
        assert not hasattr(rows[0], "payload")
