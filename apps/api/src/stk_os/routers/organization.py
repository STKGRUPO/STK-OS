from __future__ import annotations

import re
import logging
import unicodedata
import uuid
from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, Header, HTTPException, Request, Response, UploadFile
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError

from stk_os.commands import record_change
from stk_os.database import SessionDep
from stk_os.dependencies import ActorDep, current_actor, require_permission
from stk_os.fiscal import certificate_vault
from stk_os.fiscal.sequence import highest_reserved_number
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
logger = logging.getLogger(__name__)


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
        logger.warning("integrity_error detail=%s error=%s", detail, error)
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
        email=establishment.email,
        phone=establishment.phone,
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
        tax_regime=entity.tax_regime,
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
                email=establishment.email,
                phone=establishment.phone,
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
                tax_regime=entity.tax_regime,
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
        tax_regime=command.tax_regime,
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
    entity.tax_regime = command.tax_regime
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
        email=command.email,
        phone=command.phone,
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
    if "email" in command.model_fields_set:
        establishment.email = command.email
    if "phone" in command.model_fields_set:
        establishment.phone = command.phone
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
    is_new_config = config is None
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
        "municipality_code",
        "series",
        "service_code",
        "nbs_code",
        "fiscal_rules",
        "status",
    ):
        setattr(config, field, getattr(command, field))
    # O certificado A1 é resolvido pelo CNPJ em fiscal_certificates: a tela não envia
    # essas referências e salvar a configuracao nao pode apaga-las.
    if command.next_dps_number is not None:
        historic = highest_reserved_number(session, config)
        if historic > 0 or is_new_config is False:
            raise HTTPException(
                status_code=409,
                detail=(
                    "A sequência da DPS é controlada pelo motor fiscal e não pode ser "
                    "alterada aqui. Use o procedimento administrativo de sequência."
                ),
            )
        config.next_dps_number = int(command.next_dps_number)
    if not config.certificate_secret_ref:
        config.certificate_secret_ref = "db://fiscal_certificates"
    if not config.certificate_key_id:
        config.certificate_key_id = str(establishment.id)
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

_CERT_COLUMNS = """
    id, establishment_id, environment, alias, certificate_key_id,
    holder_name AS subject_name, tax_id, thumbprint,
    not_before AS not_valid_before, not_after AS not_valid_after,
    secret_ref AS certificate_secret_ref,
    (status = 'active') AS is_active, created_at
"""


@router.get(
    "/fiscal-establishments/{establishment_id}/certificates",
    response_model=schemas.EstablishmentCertificateListOut,
)
def list_establishment_certificates(
    establishment_id: uuid.UUID,
    session: SessionDep,
    actor: Annotated[ActorContext, Depends(require_permission("organization:read"))],
) -> schemas.EstablishmentCertificateListOut:
    establishment = scoped_establishment(session, establishment_id, actor.organization_id)
    rows = (
        session.execute(
            text(
                f"""
                SELECT {_CERT_COLUMNS}
                  FROM fiscal_certificates
                 WHERE establishment_id = :eid AND organization_id = :org
                 ORDER BY created_at DESC
                """
            ),
            {"eid": establishment.id, "org": actor.organization_id},
        )
        .mappings()
        .all()
    )
    return schemas.EstablishmentCertificateListOut(
        certificates=[schemas.EstablishmentCertificateOut(**dict(row)) for row in rows]
    )


@router.post(
    "/fiscal-establishments/{establishment_id}/certificates",
    response_model=schemas.EstablishmentCertificateOut,
    status_code=201,
)
def create_establishment_certificate(
    establishment_id: uuid.UUID,
    session: SessionDep,
    actor: Annotated[ActorContext, Depends(require_permission("organization:write"))],
    file: Annotated[UploadFile, File()],
    password: Annotated[str, Form()],
    environment: Annotated[str, Form()] = "homologation",
    alias: Annotated[str | None, Form()] = None,
) -> schemas.EstablishmentCertificateOut:
    establishment = scoped_establishment(session, establishment_id, actor.organization_id)
    if environment not in {"homologation", "production"}:
        raise HTTPException(status_code=422, detail="Ambiente inválido")

    content = file.file.read()
    if not content:
        raise HTTPException(status_code=422, detail="Arquivo vazio")
    if len(content) > 512_000:
        raise HTTPException(status_code=413, detail="Arquivo maior que 500 KB")

    try:
        info = certificate_vault.inspect_pfx(content, password)
    except certificate_vault.CertificateError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    if info["expired"]:
        raise HTTPException(status_code=422, detail="Certificado expirado")

    key_id = certificate_vault.new_key_id(establishment.id, environment)
    material_ct, material_nonce = certificate_vault.encrypt(content)
    password_ct, password_nonce = certificate_vault.encrypt(password.encode())

    row = (
        session.execute(
            text(
                f"""
                INSERT INTO fiscal_certificates (
                    organization_id, establishment_id, environment, alias,
                    certificate_key_id, holder_name, thumbprint,
                    not_before, not_after, secret_ref, status,
                    material_ciphertext, material_nonce,
                    password_ciphertext, password_nonce
                ) VALUES (
                    :org, :est, :env, :alias,
                    :kid, :subject, :thumb,
                    :nvb, :nva, :ref, 'active',
                    :mct, :mn, :pct, :pn
                )
                ON CONFLICT (establishment_id, environment) DO UPDATE SET
                    alias = EXCLUDED.alias,
                    certificate_key_id = EXCLUDED.certificate_key_id,
                    holder_name = EXCLUDED.holder_name,
                    thumbprint = EXCLUDED.thumbprint,
                    not_before = EXCLUDED.not_before,
                    not_after = EXCLUDED.not_after,
                    secret_ref = EXCLUDED.secret_ref,
                    status = 'active',
                    material_ciphertext = EXCLUDED.material_ciphertext,
                    material_nonce = EXCLUDED.material_nonce,
                    password_ciphertext = EXCLUDED.password_ciphertext,
                    password_nonce = EXCLUDED.password_nonce,
                    updated_at = now()
                RETURNING {_CERT_COLUMNS}
                """
            ),
            {
                "org": actor.organization_id,
                "est": establishment.id,
                "env": environment,
                "alias": alias or file.filename or "Certificado A1",
                "kid": key_id,
                "subject": info["subject_name"],
                "thumb": info["thumbprint_sha256"],
                "nvb": info["not_valid_before"],
                "nva": info["not_valid_after"],
                "ref": f"db://fiscal_certificates/{key_id}",
                "mct": material_ct,
                "mn": material_nonce,
                "pct": password_ct,
                "pn": password_nonce,
            },
        )
        .mappings()
        .one()
    )

    session.execute(
        text(
            """
            UPDATE fiscal_establishment_configs
               SET certificate_secret_ref = :ref,
                   certificate_key_id = :kid,
                   updated_at = now()
             WHERE establishment_id = :est AND environment = :env
            """
        ),
        {
            "ref": row["certificate_secret_ref"],
            "kid": key_id,
            "est": establishment.id,
            "env": environment,
        },
    )
    session.commit()
    return schemas.EstablishmentCertificateOut(**dict(row))


@router.delete(
    "/fiscal-establishments/{establishment_id}/certificates/{certificate_id}",
    status_code=204,
)
def delete_establishment_certificate(
    establishment_id: uuid.UUID,
    certificate_id: uuid.UUID,
    session: SessionDep,
    actor: Annotated[ActorContext, Depends(require_permission("organization:write"))],
) -> Response:
    establishment = scoped_establishment(session, establishment_id, actor.organization_id)
    session.execute(
        text(
            """
            DELETE FROM fiscal_certificates
             WHERE id = :cid AND establishment_id = :eid AND organization_id = :org
            """
        ),
        {"cid": certificate_id, "eid": establishment.id, "org": actor.organization_id},
    )
    session.commit()
    return Response(status_code=204)


_CATALOG_SELECT = text(
    """
    SELECT id, service_code, nbs_code, description,
           default_iss_percent, status
      FROM service_code_catalog
     ORDER BY service_code
    """
)


def _catalog_item(row) -> dict:
    return {
        "id": str(row.id),
        "service_code": row.service_code,
        "nbs_code": row.nbs_code,
        "description": row.description,
        "default_iss_percent": (
            None if row.default_iss_percent is None else str(row.default_iss_percent)
        ),
        "status": row.status,
    }


@router.get("/service-codes")
def list_service_codes(
    session: SessionDep,
    actor: Annotated[ActorContext, Depends(require_permission("organization:read"))],
) -> dict:
    rows = session.execute(_CATALOG_SELECT).all()
    return {"items": [_catalog_item(row) for row in rows]}


@router.post("/service-codes", status_code=201)
def create_service_code(
    payload: dict,
    session: SessionDep,
    actor: Annotated[ActorContext, Depends(require_permission("organization:write"))],
) -> dict:
    code = (payload.get("service_code") or "").strip()
    if not code:
        raise HTTPException(status_code=422, detail="service_code é obrigatório")
    row = session.execute(
        text(
            """
            INSERT INTO service_code_catalog
                   (service_code, nbs_code, description, default_iss_percent, status)
            VALUES (:code, :nbs, :description, :iss, :status)
            ON CONFLICT (service_code) DO UPDATE
                SET nbs_code = EXCLUDED.nbs_code,
                    description = EXCLUDED.description,
                    default_iss_percent = EXCLUDED.default_iss_percent,
                    status = EXCLUDED.status,
                    updated_at = now()
            RETURNING id, service_code, nbs_code, description,
                      default_iss_percent, status
            """
        ),
        {
            "code": code,
            "nbs": payload.get("nbs_code"),
            "description": payload.get("description"),
            "iss": payload.get("default_iss_percent"),
            "status": payload.get("status") or "active",
        },
    ).one()
    session.commit()
    return _catalog_item(row)


@router.patch("/service-codes/{code_id}")
def update_service_code(
    code_id: uuid.UUID,
    payload: dict,
    session: SessionDep,
    actor: Annotated[ActorContext, Depends(require_permission("organization:write"))],
) -> dict:
    row = session.execute(
        text(
            """
            UPDATE service_code_catalog
               SET service_code = COALESCE(:code, service_code),
                   nbs_code = :nbs,
                   description = :description,
                   default_iss_percent = :iss,
                   status = COALESCE(:status, status),
                   updated_at = now()
             WHERE id = :id
            RETURNING id, service_code, nbs_code, description,
                      default_iss_percent, status
            """
        ),
        {
            "id": code_id,
            "code": payload.get("service_code"),
            "nbs": payload.get("nbs_code"),
            "description": payload.get("description"),
            "iss": payload.get("default_iss_percent"),
            "status": payload.get("status"),
        },
    ).first()
    if row is None:
        raise HTTPException(status_code=404, detail="Código de serviço não encontrado")
    session.commit()
    return _catalog_item(row)


@router.get("/service-codes/{code_id}/rate")
def get_service_code_rate(
    code_id: uuid.UUID,
    municipality_code: str,
    session: SessionDep,
    actor: Annotated[ActorContext, Depends(require_permission("organization:read"))],
) -> dict:
    digits = "".join(ch for ch in municipality_code if ch.isdigit())
    row = session.execute(
        text(
            """
            SELECT iss_percent, iss_retained_by_taker, source,
                   legal_basis, confirmed_by, confirmed_at
              FROM service_code_municipal_rates
             WHERE service_code_id = :id AND municipality_code = :municipality
            """
        ),
        {"id": code_id, "municipality": digits},
    ).first()
    if row is None:
        return {
            "service_code_id": str(code_id),
            "municipality_code": digits,
            "iss_percent": None,
            "iss_retained_by_taker": None,
            "confirmed": False,
        }
    return {
        "service_code_id": str(code_id),
        "municipality_code": digits,
        "iss_percent": None if row.iss_percent is None else str(row.iss_percent),
        "iss_retained_by_taker": row.iss_retained_by_taker,
        "source": row.source,
        "legal_basis": row.legal_basis,
        "confirmed_by": row.confirmed_by,
        "confirmed_at": row.confirmed_at.isoformat() if row.confirmed_at else None,
        "confirmed": row.confirmed_at is not None,
    }


@router.post("/service-codes/{code_id}/rates", status_code=201)
def upsert_service_code_rate(
    code_id: uuid.UUID,
    payload: dict,
    session: SessionDep,
    actor: Annotated[ActorContext, Depends(require_permission("organization:write"))],
) -> dict:
    digits = "".join(ch for ch in (payload.get("municipality_code") or "") if ch.isdigit())
    if len(digits) != 7:
        raise HTTPException(status_code=422, detail="municipality_code deve ter 7 dígitos (IBGE)")
    row = session.execute(
        text(
            """
            INSERT INTO service_code_municipal_rates
                   (service_code_id, municipality_code, iss_percent,
                    iss_retained_by_taker, source, legal_basis,
                    confirmed_by, confirmed_at)
            VALUES (:id, :municipality, :iss, :retained, 'manual',
                    :legal_basis, :actor, now())
            ON CONFLICT (service_code_id, municipality_code) DO UPDATE
                SET iss_percent = EXCLUDED.iss_percent,
                    iss_retained_by_taker = EXCLUDED.iss_retained_by_taker,
                    legal_basis = EXCLUDED.legal_basis,
                    confirmed_by = EXCLUDED.confirmed_by,
                    confirmed_at = now(),
                    updated_at = now()
            RETURNING iss_percent, iss_retained_by_taker, source,
                      legal_basis, confirmed_by, confirmed_at
            """
        ),
        {
            "id": code_id,
            "municipality": digits,
            "iss": payload.get("iss_percent"),
            "retained": bool(payload.get("iss_retained_by_taker")),
            "legal_basis": payload.get("legal_basis"),
            "actor": actor.display_name,
        },
    ).one()
    session.commit()
    return {
        "service_code_id": str(code_id),
        "municipality_code": digits,
        "iss_percent": None if row.iss_percent is None else str(row.iss_percent),
        "iss_retained_by_taker": row.iss_retained_by_taker,
        "source": row.source,
        "legal_basis": row.legal_basis,
        "confirmed_by": row.confirmed_by,
        "confirmed_at": row.confirmed_at.isoformat() if row.confirmed_at else None,
        "confirmed": True,
    }
