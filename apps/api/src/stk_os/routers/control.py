from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select

from stk_os.database import SessionDep
from stk_os.dependencies import require_permission
from stk_os.logging import redact
from stk_os.models import AuditEvent, InboxEvent, OperationalException
from stk_os.schemas import (
    ActorContext,
    AuditEventResponse,
    ExceptionCreate,
    ExceptionResponse,
    InboxEventCreate,
    InboxEventResponse,
)
from stk_os.security import canonical_hash

router = APIRouter(prefix="/control", tags=["control"])


@router.post("/inbox", response_model=InboxEventResponse, status_code=201)
def receive_event(
    command: InboxEventCreate,
    request: Request,
    session: SessionDep,
    actor: Annotated[ActorContext, Depends(require_permission("events:ingest"))],
) -> InboxEventResponse:
    digest = canonical_hash(command.payload)
    existing = session.scalar(
        select(InboxEvent).where(
            InboxEvent.organization_id == actor.organization_id,
            InboxEvent.source == command.source,
            InboxEvent.external_event_id == command.external_event_id,
        )
    )
    if existing:
        if existing.payload_sha256 != digest:
            raise HTTPException(status_code=409, detail="Evento duplicado com payload divergente")
        return InboxEventResponse(
            id=existing.id,
            status=existing.status,
            duplicate=True,
            correlation_id=existing.correlation_id,
        )
    event = InboxEvent(
        organization_id=actor.organization_id,
        source=command.source,
        external_event_id=command.external_event_id,
        event_type=command.event_type,
        payload=redact(command.payload),
        payload_sha256=digest,
        correlation_id=request.state.correlation_id,
    )
    session.add(event)
    session.flush()
    session.add(
        AuditEvent(
            organization_id=actor.organization_id,
            actor_id=actor.id,
            correlation_id=request.state.correlation_id,
            action="inbox_event.received",
            resource_type="inbox_event",
            resource_id=event.id,
            before_state=None,
            after_state={"source": event.source, "event_type": event.event_type},
            event_metadata={"payload_sha256": digest},
        )
    )
    session.commit()
    return InboxEventResponse(
        id=event.id,
        status=event.status,
        duplicate=False,
        correlation_id=event.correlation_id,
    )


@router.post("/exceptions", response_model=ExceptionResponse, status_code=201)
def create_exception(
    command: ExceptionCreate,
    request: Request,
    session: SessionDep,
    actor: Annotated[ActorContext, Depends(require_permission("exceptions:write"))],
) -> OperationalException:
    item = OperationalException(
        organization_id=actor.organization_id,
        actor_id=actor.id,
        correlation_id=request.state.correlation_id,
        exception_type=command.exception_type,
        severity=command.severity,
        title=command.title,
        context=redact(command.context),
    )
    session.add(item)
    session.flush()
    session.add(
        AuditEvent(
            organization_id=actor.organization_id,
            actor_id=actor.id,
            correlation_id=request.state.correlation_id,
            action="exception.created",
            resource_type="exception",
            resource_id=item.id,
            before_state=None,
            after_state={"type": item.exception_type, "severity": item.severity},
            event_metadata={},
        )
    )
    session.commit()
    return item


@router.get("/audit", response_model=list[AuditEventResponse])
def list_audit_events(
    session: SessionDep,
    actor: Annotated[ActorContext, Depends(require_permission("audit:read"))],
    limit: int = 50,
) -> list[AuditEventResponse]:
    safe_limit = max(1, min(limit, 100))
    events = session.scalars(
        select(AuditEvent)
        .where(AuditEvent.organization_id == actor.organization_id)
        .order_by(AuditEvent.occurred_at.desc())
        .limit(safe_limit)
    ).all()
    return [
        AuditEventResponse(
            id=event.id,
            actor_id=event.actor_id,
            correlation_id=event.correlation_id,
            action=event.action,
            resource_type=event.resource_type,
            resource_id=event.resource_id,
            before_state=event.before_state,
            after_state=event.after_state,
            occurred_at=event.occurred_at,
        )
        for event in events
    ]
