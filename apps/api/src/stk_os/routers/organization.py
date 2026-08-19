from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from sqlalchemy import select

from stk_os.database import SessionDep
from stk_os.dependencies import require_permission
from stk_os.models import (
    AuditEvent,
    BusinessUnit,
    FiscalEstablishment,
    IdempotencyKey,
    LegalEntity,
    Organization,
    OutboxEvent,
)
from stk_os.schemas import (
    ActorContext,
    BusinessUnitResponse,
    BusinessUnitUpdate,
    FiscalEstablishmentResponse,
    LegalEntityResponse,
    OrganizationResponse,
)
from stk_os.security import canonical_hash

router = APIRouter(prefix="/organization", tags=["organization"])


@router.get("", response_model=OrganizationResponse)
def get_organization(
    session: SessionDep,
    actor: Annotated[ActorContext, Depends(require_permission("organization:read"))],
) -> OrganizationResponse:
    organization = session.get(Organization, actor.organization_id)
    if organization is None:
        raise HTTPException(status_code=404, detail="Grupo não encontrado")
    entities = session.scalars(
        select(LegalEntity)
        .where(LegalEntity.organization_id == actor.organization_id)
        .order_by(LegalEntity.code)
    ).all()
    establishments = session.scalars(
        select(FiscalEstablishment)
        .join(LegalEntity, FiscalEstablishment.legal_entity_id == LegalEntity.id)
        .where(LegalEntity.organization_id == actor.organization_id)
        .order_by(FiscalEstablishment.code)
    ).all()
    units = session.scalars(
        select(BusinessUnit)
        .where(BusinessUnit.organization_id == actor.organization_id)
        .order_by(BusinessUnit.code)
    ).all()
    units_by_establishment: dict[uuid.UUID, list[BusinessUnitResponse]] = {}
    for unit in units:
        units_by_establishment.setdefault(unit.primary_establishment_id, []).append(
            BusinessUnitResponse.model_validate(unit)
        )
    establishments_by_entity: dict[uuid.UUID, list[FiscalEstablishmentResponse]] = {}
    for establishment in establishments:
        establishments_by_entity.setdefault(establishment.legal_entity_id, []).append(
            FiscalEstablishmentResponse(
                id=establishment.id,
                code=establishment.code,
                name=establishment.name,
                kind=establishment.kind,
                status=establishment.status,
                legal_entity_id=establishment.legal_entity_id,
                business_units=units_by_establishment.get(establishment.id, []),
            )
        )
    return OrganizationResponse(
        id=organization.id,
        code=organization.code,
        name=organization.name,
        status=organization.status,
        legal_entities=[
            LegalEntityResponse(
                id=entity.id,
                code=entity.code,
                registered_name=entity.registered_name,
                trade_name=entity.trade_name,
                status=entity.status,
                establishments=establishments_by_entity.get(entity.id, []),
            )
            for entity in entities
        ],
    )


@router.patch("/business-units/{unit_id}", response_model=BusinessUnitResponse)
def update_business_unit(
    unit_id: uuid.UUID,
    command: BusinessUnitUpdate,
    request: Request,
    session: SessionDep,
    actor: Annotated[ActorContext, Depends(require_permission("organization:write"))],
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=8, max_length=255)],
) -> BusinessUnitResponse:
    command_name = "organization.business_unit.update"
    request_hash = canonical_hash({"unit_id": str(unit_id), **command.model_dump()})
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
        if existing.status == "completed" and existing.response_body:
            return BusinessUnitResponse.model_validate(existing.response_body)
        raise HTTPException(
            status_code=409, detail="Comando com esta chave ainda está em processamento"
        )

    now = datetime.now(UTC)
    record = IdempotencyKey(
        actor_id=actor.id,
        command_name=command_name,
        idempotency_key=idempotency_key,
        request_hash=request_hash,
        correlation_id=request.state.correlation_id,
        expires_at=now + timedelta(hours=24),
    )
    session.add(record)

    unit = session.scalar(
        select(BusinessUnit).where(
            BusinessUnit.id == unit_id,
            BusinessUnit.organization_id == actor.organization_id,
        )
    )
    if unit is None:
        raise HTTPException(status_code=404, detail="Unidade de negócio não encontrada")
    before = {"name": unit.name, "status": unit.status}
    unit.name = command.name
    after = {"name": unit.name, "status": unit.status}
    session.add(
        AuditEvent(
            organization_id=actor.organization_id,
            actor_id=actor.id,
            correlation_id=request.state.correlation_id,
            action="business_unit.updated",
            resource_type="business_unit",
            resource_id=unit.id,
            before_state=before,
            after_state=after,
            event_metadata={"source": "api"},
        )
    )
    session.add(
        OutboxEvent(
            organization_id=actor.organization_id,
            aggregate_type="business_unit",
            aggregate_id=unit.id,
            event_type="organization.business_unit.updated.v1",
            payload={"business_unit_id": str(unit.id), "changed_fields": ["name"]},
            correlation_id=request.state.correlation_id,
        )
    )
    response = BusinessUnitResponse.model_validate(unit)
    record.status = "completed"
    record.response_status = 200
    record.response_body = response.model_dump(mode="json")
    record.completed_at = now
    session.commit()
    return response
