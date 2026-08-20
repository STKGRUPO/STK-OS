from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from stk_os.models import AuditEvent, IdempotencyKey, OutboxEvent
from stk_os.schemas import ActorContext
from stk_os.security import canonical_hash


def begin_command(
    session: Session,
    *,
    actor: ActorContext,
    command_name: str,
    idempotency_key: str,
    payload: dict[str, Any],
    correlation_id: uuid.UUID,
) -> tuple[IdempotencyKey | None, dict[str, Any] | None]:
    request_hash = canonical_hash(payload)
    existing = session.scalar(
        select(IdempotencyKey).where(
            IdempotencyKey.actor_id == actor.id,
            IdempotencyKey.command_name == command_name,
            IdempotencyKey.idempotency_key == idempotency_key,
        )
    )
    if existing:
        if existing.request_hash != request_hash:
            raise HTTPException(status_code=409, detail="Chave reutilizada com intenção diferente")
        if existing.status == "completed" and existing.response_body is not None:
            return None, existing.response_body
        raise HTTPException(
            status_code=409, detail="Comando com esta chave ainda está em processamento"
        )
    now = datetime.now(UTC)
    record = IdempotencyKey(
        actor_id=actor.id,
        command_name=command_name,
        idempotency_key=idempotency_key,
        request_hash=request_hash,
        correlation_id=correlation_id,
        expires_at=now + timedelta(hours=24),
    )
    session.add(record)
    return record, None


def complete_command(
    record: IdempotencyKey, response_body: dict[str, Any], *, response_status: int
) -> None:
    record.status = "completed"
    record.response_status = response_status
    record.response_body = response_body
    record.completed_at = datetime.now(UTC)


def record_change(
    session: Session,
    *,
    actor: ActorContext,
    correlation_id: uuid.UUID,
    action: str,
    resource_type: str,
    resource_id: uuid.UUID,
    before_state: dict[str, Any] | None,
    after_state: dict[str, Any] | None,
    event_type: str,
    event_payload: dict[str, Any],
) -> None:
    session.add(
        AuditEvent(
            organization_id=actor.organization_id,
            actor_id=actor.id,
            correlation_id=correlation_id,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            before_state=before_state,
            after_state=after_state,
            event_metadata={"source": "api"},
        )
    )
    session.add(
        OutboxEvent(
            organization_id=actor.organization_id,
            aggregate_type=resource_type,
            aggregate_id=resource_id,
            event_type=event_type,
            payload=event_payload,
            correlation_id=correlation_id,
        )
    )
