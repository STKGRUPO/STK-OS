from __future__ import annotations

import re
import unicodedata
import uuid
from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, Form, Header, HTTPException, Request, Response
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from stk_os.commands import record_change
from stk_os.database import SessionDep
from stk_os.dependencies import require_permission
from stk_os import schemas
from stk_os.models import (
    AuditEvent,
    BusinessUnit,
    FiscalEstablishment,
    FiscalEstablishmentConfig,
    IdempotencyKey,
    LegalEntity,
    Organization,
    OutboxEvent,
    ProductService,
)
from stk_os.schemas import (
    ActorContext,
    BusinessUnitResponse,
    BusinessUnitUpdate,
    FiscalConfigListResponse,
    FiscalConfigResponse,
    FiscalConfigUpsert,
    FiscalEstablishmentCreate,
    FiscalEstablishmentResponse,
    FiscalEstablishmentUpdate,
    LegalEntityCreate,
    LegalEntityResponse,
    LegalEntityUpdate,
    OrganizationResponse,
    ProductServiceListResponse,
    ProductServiceResponse,
    ProductServiceUpsert,
)
from stk_os.security import canonical_hash

router = APIRouter(prefix="/organization", tags=["organization"])


def code_base(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9]+", "-", normalized.lower()).strip("-")[:90] or "cadastro"


def available_entity_code(session: SessionDep, organization_id: uuid.UUID, preferred: str) -> str:
    base = code_base(preferred)
    candidate = base
    suffix = 2
    while session.scalar(
        select(LegalEntity.id).where(
            LegalEntity.organization_id == organization_id, LegalEntity.code == candidate
        )
    ):
        candidate = f"{base[: 90 - len(str(suffix))]}-{suffix}"
        suffix += 1
    return candidate


def available_establishment_code(
    session: SessionDep, legal_entity_id: uuid.UUID, preferred: str
) -> str:
    base = code_base(preferred)
    candidate = base
    suffix = 2
    while session.scalar(
        select(FiscalEstablishment.id).where(
            FiscalEstablishment.legal_entity_id == legal_entity_id,
            FiscalEstablishment.code == candidate,
        )
    ):
        candidate = f"{base[: 90 - len(str(suffix))]}-{suffix}"
        suffix += 1
    return candidate


def flush_or_conflict(session: SessionDep, detail: str) -> None:
    try:
        session.flush()
    except IntegrityError as error:
        session.rollback()
        raise HTTPException(status_code=409, detail=detail) from error


def establishment_response(
    session: SessionDep, establishment: FiscalEstablishment
) -> FiscalEstablishmentResponse:
    units = session.scalars(
        select(BusinessUnit)
        .where(BusinessUnit.primary_establishment_id == establishment.id)
        .order_by(BusinessUnit.name)
    ).all()
    return FiscalEstablishmentResponse(
        id=establishment.id,
        code=establishment.code,
        name=establishment.name,
        kind=establishment.kind,
        tax_id=establishment.tax_id,
        status=establishment.status,
        legal_entity_id=establishment.legal_entity_id,
        business_units=[BusinessUnitResponse.model_validate(unit) for unit in units],
    )


def legal_entity_response(session: SessionDep, entity: LegalEntity) -> LegalEntityResponse:
    establishments = session.scalars(
        select(FiscalEstablishment)
        .where(FiscalEstablishment.legal_entity_id == entity.id)
        .order_by(FiscalEstablishment.code)
    ).all()
    return LegalEntityResponse(
        id=entity.id,
        code=entity.code,
        registered_name=entity.registered_name,
        trade_name=entity.trade_name,
        tax_id=entity.tax_id,
        status=entity.status,
        establishments=[establishment_response(session, item) for item in establishments],
    )


def scoped_legal_entity(
    session: SessionDep, entity_id: uuid.UUID, organization_id: uuid.UUID
) -> LegalEntity:
    entity = session.scalar(
        select(LegalEntity).where(
            LegalEntity.id == entity_id, LegalEntity.organization_id == organization_id
        )
    )
    if entity is None:
        raise HTTPException(status_code=404, detail="Empresa do Grupo não encontrada")
    return entity


def scoped_establishment(
    session: SessionDep, establishment_id: uuid.UUID, organization_id: uuid.UUID
) -> FiscalEstablishment:
    establishment = session.scalar(
        select(FiscalEstablishment)
        .join(LegalEntity, LegalEntity.id == FiscalEstablishment.legal_entity_id)
        .where(
            FiscalEstablishment.id == establishment_id,
            LegalEntity.organization_id == organization_id,
        )
    )
    if establishment is None:
        raise HTTPException(status_code=404, detail="Estabelecimento fiscal não encontrado")
    return establishment


def link_business_units(
    session: SessionDep,
    *,
    establishment: FiscalEstablishment,
    organization_id: uuid.UUID,
    business_unit_ids: list[uuid.UUID],
    allow_existing_removal: bool,
) -> None:
    unique_ids = list(dict.fromkeys(business_unit_ids))
    if not allow_existing_removal:
        current_ids = set(
            session.scalars(
                select(BusinessUnit.id).where(
                    BusinessUnit.primary_establishment_id == establishment.id
                )
            ).all()
        )
        if not current_ids.issubset(unique_ids):
            raise HTTPException(
                status_code=422,
                detail=(
                    "Uma unidade não pode ficar sem estabelecimento fiscal. "
                    "Vincule-a primeiro ao estabelecimento de destino."
                ),
            )
    if not unique_ids:
        return
    units = session.scalars(
        select(BusinessUnit).where(
            BusinessUnit.organization_id == organization_id,
            BusinessUnit.id.in_(unique_ids),
        )
    ).all()
    if len(units) != len(unique_ids):
        raise HTTPException(status_code=422, detail="Unidade de negócio inválida")
    for unit in units:
        unit.primary_establishment_id = establishment.id


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
                tax_id=establishment.tax_id,
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
                tax_id=entity.tax_id,
                status=entity.status,
                establishments=establishments_by_entity.get(entity.id, []),
            )
            for entity in entities
        ],
    )


@router.post("/legal-entities", response_model=LegalEntityResponse, status_code=201)
def create_legal_entity(
    command: LegalEntityCreate,
    request: Request,
    session: SessionDep,
    actor: Annotated[ActorContext, Depends(require_permission("organization:write"))],
) -> LegalEntityResponse:
    entity = LegalEntity(
        organization_id=actor.organization_id,
        code=available_entity_code(
            session,
            actor.organization_id,
            command.code or command.trade_name or command.registered_name,
        ),
        registered_name=command.registered_name,
        trade_name=command.trade_name,
        tax_id=command.tax_id,
        status=command.status,
    )
    session.add(entity)
    flush_or_conflict(session, "CNPJ ou código já cadastrado")
    response = legal_entity_response(session, entity)
    record_change(
        session,
        actor=actor,
        correlation_id=request.state.correlation_id,
        action="organization.legal_entity.created",
        resource_type="legal_entity",
        resource_id=entity.id,
        before_state=None,
        after_state=response.model_dump(mode="json"),
        event_type="organization.legal_entity.created.v1",
        event_payload={"legal_entity_id": str(entity.id)},
    )
    try:
        session.commit()
    except IntegrityError as error:
        session.rollback()
        raise HTTPException(status_code=409, detail="CNPJ ou código já cadastrado") from error
    return response


@router.patch("/legal-entities/{entity_id}", response_model=LegalEntityResponse)
def update_legal_entity(
    entity_id: uuid.UUID,
    command: LegalEntityUpdate,
    request: Request,
    session: SessionDep,
    actor: Annotated[ActorContext, Depends(require_permission("organization:write"))],
) -> LegalEntityResponse:
    entity = scoped_legal_entity(session, entity_id, actor.organization_id)
    before = legal_entity_response(session, entity).model_dump(mode="json")
    entity.registered_name = command.registered_name
    entity.trade_name = command.trade_name
    entity.tax_id = command.tax_id
    entity.status = command.status
    flush_or_conflict(session, "CNPJ já cadastrado")
    response = legal_entity_response(session, entity)
    record_change(
        session,
        actor=actor,
        correlation_id=request.state.correlation_id,
        action="organization.legal_entity.updated",
        resource_type="legal_entity",
        resource_id=entity.id,
        before_state=before,
        after_state=response.model_dump(mode="json"),
        event_type="organization.legal_entity.updated.v1",
        event_payload={"legal_entity_id": str(entity.id)},
    )
    try:
        session.commit()
    except IntegrityError as error:
        session.rollback()
        raise HTTPException(status_code=409, detail="CNPJ já cadastrado") from error
    return response


@router.post(
    "/legal-entities/{entity_id}/fiscal-establishments",
    response_model=FiscalEstablishmentResponse,
    status_code=201,
)
def create_fiscal_establishment(
    entity_id: uuid.UUID,
    command: FiscalEstablishmentCreate,
    request: Request,
    session: SessionDep,
    actor: Annotated[ActorContext, Depends(require_permission("organization:write"))],
) -> FiscalEstablishmentResponse:
    entity = scoped_legal_entity(session, entity_id, actor.organization_id)
    establishment = FiscalEstablishment(
        legal_entity_id=entity.id,
        code=available_establishment_code(session, entity.id, command.code or command.name),
        name=command.name,
        kind=command.kind,
        tax_id=command.tax_id,
        status=command.status,
    )
    session.add(establishment)
    flush_or_conflict(session, "CNPJ ou código já cadastrado")
    link_business_units(
        session,
        establishment=establishment,
        organization_id=actor.organization_id,
        business_unit_ids=command.business_unit_ids,
        allow_existing_removal=True,
    )
    flush_or_conflict(session, "Não foi possível vincular as unidades")
    response = establishment_response(session, establishment)
    record_change(
        session,
        actor=actor,
        correlation_id=request.state.correlation_id,
        action="organization.fiscal_establishment.created",
        resource_type="fiscal_establishment",
        resource_id=establishment.id,
        before_state=None,
        after_state=response.model_dump(mode="json"),
        event_type="organization.fiscal_establishment.created.v1",
        event_payload={
            "fiscal_establishment_id": str(establishment.id),
            "legal_entity_id": str(entity.id),
        },
    )
    try:
        session.commit()
    except IntegrityError as error:
        session.rollback()
        raise HTTPException(status_code=409, detail="CNPJ ou código já cadastrado") from error
    return response


@router.patch(
    "/fiscal-establishments/{establishment_id}",
    response_model=FiscalEstablishmentResponse,
)
def update_fiscal_establishment(
    establishment_id: uuid.UUID,
    command: FiscalEstablishmentUpdate,
    request: Request,
    session: SessionDep,
    actor: Annotated[ActorContext, Depends(require_permission("organization:write"))],
) -> FiscalEstablishmentResponse:
    establishment = scoped_establishment(session, establishment_id, actor.organization_id)
    before = establishment_response(session, establishment).model_dump(mode="json")
    establishment.name = command.name
    establishment.kind = command.kind
    establishment.tax_id = command.tax_id
    establishment.status = command.status
    link_business_units(
        session,
        establishment=establishment,
        organization_id=actor.organization_id,
        business_unit_ids=command.business_unit_ids,
        allow_existing_removal=False,
    )
    flush_or_conflict(session, "CNPJ já cadastrado")
    response = establishment_response(session, establishment)
    record_change(
        session,
        actor=actor,
        correlation_id=request.state.correlation_id,
        action="organization.fiscal_establishment.updated",
        resource_type="fiscal_establishment",
        resource_id=establishment.id,
        before_state=before,
        after_state=response.model_dump(mode="json"),
        event_type="organization.fiscal_establishment.updated.v1",
        event_payload={
            "fiscal_establishment_id": str(establishment.id),
            "legal_entity_id": str(establishment.legal_entity_id),
        },
    )
    try:
        session.commit()
    except IntegrityError as error:
        session.rollback()
        raise HTTPException(status_code=409, detail="CNPJ já cadastrado") from error
    return response


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

def fiscal_config_response(config: FiscalEstablishmentConfig) -> FiscalConfigResponse:
    return FiscalConfigResponse(
        id=config.id,
        establishment_id=config.establishment_id,
        environment=config.environment,
        provider=config.provider,
        emission_method=config.emission_method,
        endpoint=config.endpoint,
        query_base_url=config.query_base_url,
        certificate_secret_ref=config.certificate_secret_ref,
        certificate_key_id=config.certificate_key_id,
        municipality_code=config.municipality_code,
        series=config.series,
        next_dps_number=config.next_dps_number,
        service_code=config.service_code,
        nbs_code=config.nbs_code,
        fiscal_rules=config.fiscal_rules or {},
        status=config.status,
    )


@router.get(
    "/fiscal-establishments/{establishment_id}/fiscal-configs",
    response_model=FiscalConfigListResponse,
)
def list_fiscal_configs(
    establishment_id: uuid.UUID,
    session: SessionDep,
    actor: Annotated[ActorContext, Depends(require_permission("organization:read"))],
) -> FiscalConfigListResponse:
    establishment = scoped_establishment(session, establishment_id, actor.organization_id)
    configs = session.scalars(
        select(FiscalEstablishmentConfig)
        .where(FiscalEstablishmentConfig.establishment_id == establishment.id)
        .where(FiscalEstablishmentConfig.organization_id == actor.organization_id)
        .order_by(FiscalEstablishmentConfig.environment)
    ).all()
    return FiscalConfigListResponse(configs=[fiscal_config_response(item) for item in configs])


@router.post(
    "/fiscal-establishments/{establishment_id}/fiscal-configs",
    response_model=FiscalConfigResponse,
    status_code=200,
)
def upsert_fiscal_config(
    establishment_id: uuid.UUID,
    command: FiscalConfigUpsert,
    request: Request,
    session: SessionDep,
    actor: Annotated[ActorContext, Depends(require_permission("organization:write"))],
) -> FiscalConfigResponse:
    establishment = scoped_establishment(session, establishment_id, actor.organization_id)
    config = session.scalars(
        select(FiscalEstablishmentConfig)
        .where(FiscalEstablishmentConfig.establishment_id == establishment.id)
        .where(FiscalEstablishmentConfig.environment == command.environment)
        .where(FiscalEstablishmentConfig.organization_id == actor.organization_id)
    ).one_or_none()
    before = fiscal_config_response(config).model_dump(mode="json") if config else None
    if config is None:
        config = FiscalEstablishmentConfig(
            organization_id=actor.organization_id,
            establishment_id=establishment.id,
            environment=command.environment,
            provider="sefin_nacional",
        )
        session.add(config)
    for field in (
        "emission_method",
        "endpoint",
        "query_base_url",
        "certificate_secret_ref",
        "certificate_key_id",
        "municipality_code",
        "series",
        "next_dps_number",
        "service_code",
        "nbs_code",
        "fiscal_rules",
        "status",
    ):
        setattr(config, field, getattr(command, field))
    flush_or_conflict(session, "Configuração fiscal já existe para este ambiente")
    response = fiscal_config_response(config)
    record_change(
        session,
        actor=actor,
        correlation_id=request.state.correlation_id,
        action="organization.fiscal_config.upserted",
        resource_type="fiscal_establishment_config",
        resource_id=config.id,
        before_state=before,
        after_state=response.model_dump(mode="json"),
        event_type="organization.fiscal_config.upserted.v1",
        event_payload={
            "fiscal_establishment_id": str(establishment.id),
            "environment": config.environment,
        },
    )
    session.commit()
    return response


def product_service_response(item: ProductService) -> ProductServiceResponse:
    return ProductServiceResponse(
        id=item.id,
        name=item.name,
        code=getattr(item, "code", None),
        description=getattr(item, "description", None),
        default_amount=getattr(item, "default_amount", None),
        service_code=getattr(item, "service_code", None),
        nbs_code=getattr(item, "nbs_code", None),
        business_unit_ids=[bu_id for bu_id in (getattr(item, "business_unit_ids", None) or [])],
        status=item.status,
    )


@router.get("/product-services", response_model=ProductServiceListResponse)
def list_product_services(
    session: SessionDep,
    actor: Annotated[ActorContext, Depends(require_permission("organization:read"))],
    business_unit_id: uuid.UUID | None = None,
) -> ProductServiceListResponse:
    statement = (
        select(ProductService)
        .where(ProductService.organization_id == actor.organization_id)
        .order_by(ProductService.name)
    )
    if business_unit_id is not None:
        statement = statement.where(ProductService.business_unit_id == business_unit_id)
    items = session.scalars(statement).all()
    return ProductServiceListResponse(items=[product_service_response(i) for i in items])


@router.post("/product-services", response_model=ProductServiceResponse, status_code=201)
def create_product_service(
    command: ProductServiceUpsert,
    request: Request,
    session: SessionDep,
    actor: Annotated[ActorContext, Depends(require_permission("organization:write"))],
) -> ProductServiceResponse:
    item = ProductService(
        organization_id=actor.organization_id,
        name=command.name,
        status=command.status,
    )
    for field in ("code", "description", "default_amount", "service_code", "nbs_code"):
        if hasattr(item, field):
            setattr(item, field, getattr(command, field))
    if command.business_unit_ids and hasattr(item, "business_unit_id"):
        item.business_unit_id = command.business_unit_ids[0]
    session.add(item)
    flush_or_conflict(session, "Serviço já cadastrado no catálogo")
    response = product_service_response(item)
    record_change(
        session,
        actor=actor,
        correlation_id=request.state.correlation_id,
        action="organization.product_service.created",
        resource_type="product_service",
        resource_id=item.id,
        before_state=None,
        after_state=response.model_dump(mode="json"),
        event_type="organization.product_service.created.v1",
        event_payload={"product_service_id": str(item.id)},
    )
    session.commit()
    return response

@router.get(
    "/fiscal-establishments/{establishment_id}/certificates",
    response_model=schemas.EstablishmentCertificateListOut,
)
async def list_establishment_certificates(
    establishment_id: uuid.UUID,
    actor: Actor = Depends(require_permissions("fiscal:read")),
    session: AsyncSession = Depends(get_session),
) -> schemas.EstablishmentCertificateListOut:
    rows = (
        await session.execute(
            text(
                """
                SELECT id, establishment_id, alias, certificate_secret_ref,
                       certificate_key_id, subject_name, not_valid_before,
                       not_valid_after, is_active, created_at
                  FROM fiscal_certificates
                 WHERE establishment_id = :eid AND organization_id = :org
                 ORDER BY created_at DESC
                """
            ),
            {"eid": establishment_id, "org": actor.organization_id},
        )
    ).mappings().all()
    return schemas.EstablishmentCertificateListOut(
        certificates=[schemas.EstablishmentCertificateOut(**dict(r)) for r in rows]
    )


@router.post(
    "/fiscal-establishments/{establishment_id}/certificates",
    response_model=schemas.EstablishmentCertificateOut,
    status_code=201,
)
async def create_establishment_certificate(
    establishment_id: uuid.UUID,
    alias: str = Form(...),
    certificate_secret_ref: str = Form(...),
    certificate_key_id: str = Form(...),
    actor: Actor = Depends(require_permissions("fiscal:write")),
    session: AsyncSession = Depends(get_session),
) -> schemas.EstablishmentCertificateOut:
    row = (
        await session.execute(
            text(
                """
                INSERT INTO fiscal_certificates
                    (organization_id, establishment_id, alias,
                     certificate_secret_ref, certificate_key_id, is_active)
                VALUES (:org, :eid, :alias, :ref, :kid, TRUE)
                RETURNING id, establishment_id, alias, certificate_secret_ref,
                          certificate_key_id, subject_name, not_valid_before,
                          not_valid_after, is_active, created_at
                """
            ),
            {
                "org": actor.organization_id,
                "eid": establishment_id,
                "alias": alias,
                "ref": certificate_secret_ref,
                "kid": certificate_key_id,
            },
        )
    ).mappings().one()
    await session.commit()
    return schemas.EstablishmentCertificateOut(**dict(row))


@router.delete(
    "/fiscal-establishments/{establishment_id}/certificates/{certificate_id}",
    status_code=204,
)
async def delete_establishment_certificate(
    establishment_id: uuid.UUID,
    certificate_id: uuid.UUID,
    actor: Actor = Depends(require_permissions("fiscal:write")),
    session: AsyncSession = Depends(get_session),
) -> Response:
    await session.execute(
        text(
            """
            DELETE FROM fiscal_certificates
             WHERE id = :cid AND establishment_id = :eid AND organization_id = :org
            """
        ),
        {"cid": certificate_id, "eid": establishment_id, "org": actor.organization_id},
    )
    await session.commit()
    return Response(status_code=204)
