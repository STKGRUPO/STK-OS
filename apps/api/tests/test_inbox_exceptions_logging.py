from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from stk_os.logging import redact
from stk_os.models import InboxEvent, OperationalException


def test_inbox_deduplicates_same_external_event(
    client: TestClient, service_headers: dict[str, str]
) -> None:
    payload = {
        "source": "synthetic-test",
        "external_event_id": "event-001",
        "event_type": "foundation.test.v1",
        "payload": {"reference": "safe"},
    }
    first = client.post("/api/v1/control/inbox", headers=service_headers, json=payload)
    second = client.post("/api/v1/control/inbox", headers=service_headers, json=payload)
    assert first.status_code == 201
    assert first.json()["duplicate"] is False
    assert second.json()["duplicate"] is True
    assert second.json()["id"] == first.json()["id"]


def test_inbox_rejects_same_id_with_different_payload(
    client: TestClient, service_headers: dict[str, str]
) -> None:
    base = {
        "source": "synthetic-test",
        "external_event_id": "event-002",
        "event_type": "foundation.test.v1",
    }
    assert (
        client.post(
            "/api/v1/control/inbox", headers=service_headers, json={**base, "payload": {"v": 1}}
        ).status_code
        == 201
    )
    assert (
        client.post(
            "/api/v1/control/inbox", headers=service_headers, json={**base, "payload": {"v": 2}}
        ).status_code
        == 409
    )


def test_exception_is_persisted_with_redacted_context(
    client: TestClient,
    service_headers: dict[str, str],
    session_factory: sessionmaker[Session],
) -> None:
    response = client.post(
        "/api/v1/control/exceptions",
        headers=service_headers,
        json={
            "exception_type": "synthetic.failure",
            "severity": "medium",
            "title": "Falha sintética",
            "context": {"password": "must-not-persist", "code": "E_TEST"},
        },
    )
    assert response.status_code == 201
    assert response.json()["context"]["password"] == "[REDACTED]"
    with session_factory() as session:
        item = session.scalar(select(OperationalException))
        assert item is not None
        assert item.context["password"] == "[REDACTED]"


def test_payload_is_redacted_but_hash_supports_deduplication(
    client: TestClient,
    service_headers: dict[str, str],
    session_factory: sessionmaker[Session],
) -> None:
    response = client.post(
        "/api/v1/control/inbox",
        headers=service_headers,
        json={
            "source": "synthetic-test",
            "external_event_id": "event-secret",
            "event_type": "foundation.test.v1",
            "payload": {"token": "not-a-real-token", "reference": "safe"},
        },
    )
    assert response.status_code == 201
    with session_factory() as session:
        event = session.scalar(select(InboxEvent))
        assert event is not None
        assert event.payload["token"] == "[REDACTED]"
        assert len(event.payload_sha256) == 64


def test_redaction_is_recursive() -> None:
    assert redact({"nested": [{"client_secret": "value"}]}) == {
        "nested": [{"client_secret": "[REDACTED]"}]
    }
