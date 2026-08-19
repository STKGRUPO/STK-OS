from __future__ import annotations

from conftest import UNIT_ID
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from stk_os.models import AuditEvent, IdempotencyKey, OutboxEvent


def test_hierarchy_is_explicit(client: TestClient, admin_headers: dict[str, str]) -> None:
    response = client.get("/api/v1/organization", headers=admin_headers)
    assert response.status_code == 200
    payload = response.json()
    assert payload["legal_entities"][0]["establishments"][0]["business_units"][0]["code"] == "mr"


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
