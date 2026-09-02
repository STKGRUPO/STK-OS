from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from stk_os.commands import begin_command, complete_command, record_change
from stk_os.contract_schemas import (
    ContractConfiguration,
    ContractCreate,
    ContractDetail,
    ContractEventResponse,
    ContractReferenceData,
    ContractReferenceItem,
    ContractSummary,
    ContractVersionCreate,
    ContractVersionResponse,
    OperationalEventCreate,
    VersionContactResponse,
    VersionServiceResponse,
)
from stk_os.database import SessionDep
from stk_os.dependencies import require_permission
from stk_os.models import (
    Actor,
    ActorRole,
    BusinessUnit,
    Company,
    CompanyBusinessUnit,
    ContactMethod,
    Contract,
    ContractOperationalEvent,
    ContractVersion,
    ContractVersionContact,
    ContractVersionService,
    FiscalEstablishment,
    LegalEntity,
    Permission,
    Person,
    PersonCompanyRelationship,
    ProductService,
    RolePermission,
)
from stk_os.schemas import ActorContext
from stk_os.security import canonical_hash

router = APIRouter(prefix="/contracts", tags=["contracts"])
IdempotencyHeader = Annotated[str, Header(alias="Idempotency-Key", min_length=8, max_length=255)]


def unit_scope(session: Session, actor: ActorContext, permission: str) -> set[uuid.UUID] | None:
    rows = session.scalars(
        select(ActorRole.business_unit_id)
        .join(RolePermission, RolePermission.role_id == ActorRole.role_id)
        .join(Permission, Permission.id == RolePermission.permission_id)
        .where(ActorRole.actor_id == actor.id, Permission.code == permission)
    ).all()
    if not rows:
        raise HTTPException(status_code=403, detail="Capacidade insuficiente")
    if any(item is None for item in rows):
        return None
    return {item for item in rows if item is not None}


def ensure_unit_access(
    session: Session, actor: ActorContext, permission: str, business_unit_id: uuid.UUID
) -> None:
    scope = unit_scope(session, actor, permission)
    if scope is not None and business_unit_id not in scope:
        raise HTTPException(status_code=404, detail="Contrato não encontrado")


def get_contract(
    session: Session,
    actor: ActorContext,
    contract_id: uuid.UUID,
    permission: str,
) -> Contract:
    contract = session.scalar(
        select(Contract).where(
            Contract.id == contract_id, Contract.organization_id == actor.organization_id
        )
    )
    if contract is None:
        raise HTTPException(status_code=404, detail="Contrato não encontrado")
    ensure_unit_access(session, actor, permission, contract.business_unit_id)
    return contract


def issuer_for(
    session: Session, organization_id: uuid.UUID, establishment_id: uuid.UUID
) -> FiscalEstablishment:
    issuer = session.scalar(
        select(FiscalEstablishment)
        .join(LegalEntity, LegalEntity.id == FiscalEstablishment.legal_entity_id)
        .where(
            FiscalEstablishment.id == establishment_id,
            FiscalEstablishment.status == "active",
            LegalEntity.organization_id == organization_id,
        )
    )
    if issuer is None:
        raise HTTPException(status_code=422, detail="Estabelecimento fiscal emissor inválido")
    return issuer


def versions_for(session: Session, contract_id: uuid.UUID) -> list[ContractVersion]:
    return list(
        session.scalars(
            select(ContractVersion)
            .where(ContractVersion.contract_id == contract_id)
            .order_by(ContractVersion.effective_from, ContractVersion.version_number)
        ).all()
    )


def version_at(session: Session, contract: Contract, on_date: date) -> ContractVersion | None:
    if on_date < contract.start_date:
        return None
    return session.scalar(
        select(ContractVersion)
        .where(
            ContractVersion.contract_id == contract.id,
            ContractVersion.effective_from <= on_date,
        )
        .order_by(ContractVersion.effective_from.desc(), ContractVersion.version_number.desc())
        .limit(1)
    )


def operational_state(session: Session, contract_id: uuid.UUID, on_date: date) -> str:
    event = session.scalar(
        select(ContractOperationalEvent)
        .where(
            ContractOperationalEvent.contract_id == contract_id,
            ContractOperationalEvent.effective_on <= on_date,
            ContractOperationalEvent.event_type.in_(("suspended", "resumed", "terminated")),
        )
        .order_by(
            ContractOperationalEvent.effective_on.desc(),
            ContractOperationalEvent.created_at.desc(),
        )
        .limit(1)
    )
    if event is None or event.event_type == "resumed":
        return "active"
    return "suspended" if event.event_type == "suspended" else "terminated"


def service_responses(session: Session, version_id: uuid.UUID) -> list[VersionServiceResponse]:
    services = session.scalars(
        select(ContractVersionService)
        .where(ContractVersionService.contract_version_id == version_id)
        .order_by(ContractVersionService.created_at, ContractVersionService.id)
    ).all()
    result = []
    for item in services:
        product = (
            session.get(ProductService, item.product_service_id)
            if item.product_service_id
            else None
        )
        result.append(
            VersionServiceResponse(
                id=item.id,
                product_service_id=item.product_service_id,
                product_name=product.name if product else None,
                contractual_description=item.contractual_description,
                quantity=Decimal(item.quantity),
                unit_amount=Decimal(item.unit_amount) if item.unit_amount is not None else None,
                is_active=item.is_active,
            )
        )
    return result


def contact_identity(session: Session, contact: ContactMethod) -> str:
    if contact.company_id:
        company = session.get(Company, contact.company_id)
        return (company.trade_name or company.legal_name) if company else "Empresa"
    person = session.get(Person, contact.person_id) if contact.person_id else None
    return person.full_name if person else "Pessoa"


def contact_responses(session: Session, version_id: uuid.UUID) -> list[VersionContactResponse]:
    contacts = session.scalars(
        select(ContractVersionContact)
        .where(ContractVersionContact.contract_version_id == version_id)
        .order_by(ContractVersionContact.recipient_role.desc(), ContractVersionContact.created_at)
    ).all()
    result = []
    for item in contacts:
        method = session.get(ContactMethod, item.contact_method_id)
        if method is None:
            continue
        result.append(
            VersionContactResponse(
                id=item.id,
                contact_method_id=method.id,
                contact_name=contact_identity(session, method),
                contact_value=method.value,
                recipient_role=item.recipient_role,
                purpose=item.purpose,
                preferred_channel=item.preferred_channel,
            )
        )
    return result


def version_response(
    session: Session,
    version: ContractVersion,
    timeline: list[ContractVersion] | None = None,
) -> ContractVersionResponse:
    ordered = timeline or versions_for(session, version.contract_id)
    position = next(index for index, item in enumerate(ordered) if item.id == version.id)
    effective_until = (
        ordered[position + 1].effective_from - timedelta(days=1)
        if position + 1 < len(ordered)
        else None
    )
    today = date.today()
    if version.effective_from > today:
        temporal_status = "scheduled"
    elif effective_until is not None and effective_until < today:
        temporal_status = "historical"
    else:
        temporal_status = "current"
    issuer = session.get(FiscalEstablishment, version.issuer_establishment_id)
    return ContractVersionResponse(
        id=version.id,
        contract_id=version.contract_id,
        version_number=version.version_number,
        effective_from=version.effective_from,
        effective_until=effective_until,
        temporal_status=temporal_status,
        issuer_establishment_id=version.issuer_establishment_id,
        issuer_name=issuer.name if issuer else "Estabelecimento indisponível",
        currency=version.currency,
        billing_frequency=version.billing_frequency,
        pricing_model=version.pricing_model,
        amount=Decimal(version.amount),
        billing_installments=version.billing_installments,
        billing_anchor_competence=version.billing_anchor_competence,
        billing_anchor_position=version.billing_anchor_position,
        billing_cycle_total=version.billing_cycle_total,
        billing_day=version.billing_day,
        payment_terms_days=version.payment_terms_days,
        invoice_description=version.invoice_description,
        adjustment_reference=version.adjustment_reference,
        adjustment_frequency=version.adjustment_frequency,
        adjustment_base_date=version.adjustment_base_date,
        adjustment_applied_percentage=(
            Decimal(version.adjustment_applied_percentage)
            if version.adjustment_applied_percentage is not None
            else None
        ),
        adjustment_source=version.adjustment_source,
        change_type=version.change_type,
        change_reason=version.change_reason,
        source=version.source,
        configuration_sha256=version.configuration_sha256,
        services=service_responses(session, version.id),
        financial_contacts=contact_responses(session, version.id),
        created_at=version.created_at,
    )


def summary(session: Session, contract: Contract, on_date: date | None = None) -> ContractSummary:
    target = on_date or date.today()
    unit = session.get(BusinessUnit, contract.business_unit_id)
    company = session.get(Company, contract.customer_company_id)
    current = version_at(session, contract, target)
    issuer = session.get(FiscalEstablishment, current.issuer_establishment_id) if current else None
    scheduled = len(
        session.scalars(
            select(ContractVersion.id).where(
                ContractVersion.contract_id == contract.id,
                ContractVersion.effective_from > date.today(),
            )
        ).all()
    )
    return ContractSummary(
        id=contract.id,
        business_unit_id=contract.business_unit_id,
        business_unit_name=unit.name if unit else "Unidade indisponível",
        customer_company_id=contract.customer_company_id,
        customer_name=(company.trade_name or company.legal_name)
        if company
        else "Cliente indisponível",
        internal_number=contract.internal_number,
        administrative_status=contract.administrative_status,
        signed_on=contract.signed_on,
        start_date=contract.start_date,
        contract_type=contract.contract_type,
        owner_actor_id=contract.owner_actor_id,
        current_operational_state=operational_state(session, contract.id, target),
        current_version_number=current.version_number if current else None,
        current_issuer_establishment_id=current.issuer_establishment_id if current else None,
        current_issuer_name=issuer.name if issuer else None,
        current_amount=Decimal(current.amount) if current else None,
        current_currency=current.currency if current else None,
        scheduled_versions=scheduled,
        created_at=contract.created_at,
        updated_at=contract.updated_at,
    )


def event_response(item: ContractOperationalEvent) -> ContractEventResponse:
    return ContractEventResponse(
        id=item.id,
        event_type=item.event_type,
        effective_on=item.effective_on,
        reason=item.reason,
        source=item.source,
        related_version_id=item.related_version_id,
        actor_id=item.actor_id,
        correlation_id=item.correlation_id,
        created_at=item.created_at,
    )


def detail(session: Session, contract: Contract) -> ContractDetail:
    base = summary(session, contract)
    timeline = versions_for(session, contract.id)
    events = session.scalars(
        select(ContractOperationalEvent)
        .where(ContractOperationalEvent.contract_id == contract.id)
        .order_by(ContractOperationalEvent.effective_on, ContractOperationalEvent.created_at)
    ).all()
    return ContractDetail(
        **base.model_dump(),
        controlled_notes=contract.controlled_notes,
        versions=[version_response(session, item, timeline) for item in timeline],
        operational_events=[event_response(item) for item in events],
    )


def validate_version_snapshot(
    session: Session, contract: Contract, command: ContractVersionCreate
) -> tuple[FiscalEstablishment, list[ContractVersion]]:
    issuer = issuer_for(session, contract.organization_id, command.issuer_establishment_id)
    timeline = versions_for(session, contract.id)
    if not timeline:
        if command.change_type != "initial" or command.effective_from != contract.start_date:
            raise HTTPException(
                status_code=422,
                detail="A primeira versão deve ser inicial e começar na data do contrato",
            )
    else:
        if command.change_type == "initial":
            raise HTTPException(
                status_code=422, detail="Somente a primeira versão pode ser inicial"
            )
        if command.effective_from <= timeline[-1].effective_from:
            raise HTTPException(status_code=409, detail="Vigência sobreposta ou fora de ordem")
        if command.effective_from < date.today():
            raise HTTPException(
                status_code=409,
                detail=(
                    "Correção retroativa exige operação histórica autorizada, "
                    "ainda fora desta etapa"
                ),
            )
        previous = timeline[-1]
        if command.change_type == "value_change" and command.amount == Decimal(previous.amount):
            raise HTTPException(status_code=422, detail="Alteração de valor deve modificar o valor")
        if (
            command.change_type == "issuer_change"
            and command.issuer_establishment_id == previous.issuer_establishment_id
        ):
            raise HTTPException(
                status_code=422, detail="Alteração de emissor deve modificar o emissor"
            )
    catalog_ids = [item.product_service_id for item in command.services if item.product_service_id]
    if len(catalog_ids) != len(set(catalog_ids)):
        raise HTTPException(status_code=422, detail="Serviço de catálogo duplicado na versão")
    if catalog_ids:
        valid_products = set(
            session.scalars(
                select(ProductService.id).where(
                    ProductService.id.in_(catalog_ids),
                    ProductService.organization_id == contract.organization_id,
                    ProductService.business_unit_id == contract.business_unit_id,
                    ProductService.status == "active",
                )
            ).all()
        )
        if valid_products != set(catalog_ids):
            raise HTTPException(status_code=422, detail="Serviço fora da unidade do contrato")
    contact_ids = [item.contact_method_id for item in command.financial_contacts]
    if len(contact_ids) != len(set(contact_ids)):
        raise HTTPException(status_code=422, detail="Contato financeiro duplicado na versão")
    for contact_input in command.financial_contacts:
        contact = session.scalar(
            select(ContactMethod).where(
                ContactMethod.id == contact_input.contact_method_id,
                ContactMethod.organization_id == contract.organization_id,
                ContactMethod.status == "active",
            )
        )
        if contact is None or contact.kind != contact_input.preferred_channel:
            raise HTTPException(status_code=422, detail="Canal financeiro canônico inválido")
        belongs = contact.company_id == contract.customer_company_id
        if contact.person_id and not belongs:
            belongs = (
                session.scalar(
                    select(PersonCompanyRelationship.id).where(
                        PersonCompanyRelationship.person_id == contact.person_id,
                        PersonCompanyRelationship.company_id == contract.customer_company_id,
                        PersonCompanyRelationship.status == "active",
                    )
                )
                is not None
            )
        if not belongs:
            raise HTTPException(
                status_code=422, detail="Contato financeiro não pertence ao cliente"
            )
    return issuer, timeline


def add_version(
    session: Session,
    *,
    actor: ActorContext,
    contract: Contract,
    command: ContractVersionCreate,
) -> ContractVersion:
    _, timeline = validate_version_snapshot(session, contract, command)
    number = len(timeline) + 1
    payload = command.model_dump(mode="json")
    configuration_sha256 = canonical_hash(
        {"contract_id": str(contract.id), "version_number": number, "configuration": payload}
    )
    version = ContractVersion(
        organization_id=contract.organization_id,
        contract_id=contract.id,
        version_number=number,
        effective_from=command.effective_from,
        issuer_establishment_id=command.issuer_establishment_id,
        currency=command.currency,
        billing_frequency=command.billing_frequency,
        pricing_model=command.pricing_model,
        amount=command.amount,
        billing_installments=command.billing_installments,
        billing_anchor_competence=command.billing_anchor_competence,
        billing_anchor_position=command.billing_anchor_position,
        billing_cycle_total=command.billing_cycle_total,
        billing_day=command.billing_day,
        payment_terms_days=command.payment_terms_days,
        invoice_description=command.invoice_description,
        adjustment_reference=command.adjustment_reference,
        adjustment_frequency=command.adjustment_frequency,
        adjustment_base_date=command.adjustment_base_date,
        adjustment_applied_percentage=command.adjustment_applied_percentage,
        adjustment_source=command.adjustment_source,
        change_type=command.change_type,
        change_reason=command.change_reason,
        source=command.source,
        configuration_sha256=configuration_sha256,
        created_by_actor_id=actor.id,
    )
    session.add(version)
    session.flush()
    for item in command.services:
        session.add(
            ContractVersionService(
                contract_version_id=version.id,
                product_service_id=item.product_service_id,
                contractual_description=item.contractual_description.strip(),
                quantity=item.quantity,
                unit_amount=item.unit_amount,
                is_active=item.is_active,
            )
        )
    for item in command.financial_contacts:
        session.add(
            ContractVersionContact(
                contract_version_id=version.id,
                contact_method_id=item.contact_method_id,
                recipient_role=item.recipient_role,
                purpose=item.purpose,
                preferred_channel=item.preferred_channel,
            )
        )
    if contract.administrative_status == "draft":
        contract.administrative_status = "active"
        contract.updated_at = datetime.now(UTC)
    session.flush()
    return version


@router.get("/reference-data", response_model=ContractReferenceData)
def reference_data(
    session: SessionDep,
    actor: Annotated[ActorContext, Depends(require_permission("contracts:read"))],
) -> ContractReferenceData:
    scope = unit_scope(session, actor, "contracts:read")
    unit_statement = select(BusinessUnit).where(
        BusinessUnit.organization_id == actor.organization_id, BusinessUnit.status == "active"
    )
    if scope is not None:
        unit_statement = unit_statement.where(BusinessUnit.id.in_(scope))
    units = session.scalars(unit_statement.order_by(BusinessUnit.name)).all()
    unit_ids = [item.id for item in units]
    companies = session.scalars(
        select(Company)
        .join(CompanyBusinessUnit, CompanyBusinessUnit.company_id == Company.id)
        .where(
            Company.organization_id == actor.organization_id,
            CompanyBusinessUnit.business_unit_id.in_(unit_ids),
            CompanyBusinessUnit.status == "active",
        )
        .distinct()
        .order_by(Company.legal_name)
    ).all()
    establishments = session.scalars(
        select(FiscalEstablishment)
        .join(LegalEntity, LegalEntity.id == FiscalEstablishment.legal_entity_id)
        .where(
            LegalEntity.organization_id == actor.organization_id,
            FiscalEstablishment.status == "active",
        )
        .order_by(FiscalEstablishment.name)
    ).all()
    products = session.scalars(
        select(ProductService).where(
            ProductService.organization_id == actor.organization_id,
            ProductService.business_unit_id.in_(unit_ids),
            ProductService.status == "active",
        )
    ).all()
    contacts = session.scalars(
        select(ContactMethod).where(
            ContactMethod.organization_id == actor.organization_id,
            ContactMethod.status == "active",
        )
    ).all()
    return ContractReferenceData(
        business_units=[
            ContractReferenceItem(
                id=item.id,
                name=item.name,
                primary_establishment_id=item.primary_establishment_id,
            )
            for item in units
        ],
        companies=[
            ContractReferenceItem(id=item.id, name=item.trade_name or item.legal_name)
            for item in companies
        ],
        fiscal_establishments=[
            ContractReferenceItem(id=item.id, name=item.name) for item in establishments
        ],
        products_services=[
            ContractReferenceItem(
                id=item.id, name=item.name, business_unit_id=item.business_unit_id
            )
            for item in products
        ],
        contact_methods=[
            ContractReferenceItem(
                id=item.id,
                name=contact_identity(session, item),
                company_id=item.company_id,
                person_id=item.person_id,
                kind=item.kind,
                value=item.value,
            )
            for item in contacts
        ],
    )


@router.post("", response_model=ContractSummary, status_code=201)
def create_contract(
    command: ContractCreate,
    request: Request,
    session: SessionDep,
    actor: Annotated[ActorContext, Depends(require_permission("contracts:create"))],
    idempotency_key: IdempotencyHeader,
) -> ContractSummary:
    record, replay = begin_command(
        session,
        actor=actor,
        command_name="contracts.create",
        idempotency_key=idempotency_key,
        payload=command.model_dump(mode="json"),
        correlation_id=request.state.correlation_id,
    )
    if replay is not None:
        return ContractSummary.model_validate(replay)
    ensure_unit_access(session, actor, "contracts:create", command.business_unit_id)
    unit = session.scalar(
        select(BusinessUnit).where(
            BusinessUnit.id == command.business_unit_id,
            BusinessUnit.organization_id == actor.organization_id,
            BusinessUnit.status == "active",
        )
    )
    customer = session.scalar(
        select(Company)
        .join(CompanyBusinessUnit, CompanyBusinessUnit.company_id == Company.id)
        .where(
            Company.id == command.customer_company_id,
            Company.organization_id == actor.organization_id,
            CompanyBusinessUnit.business_unit_id == command.business_unit_id,
            CompanyBusinessUnit.status == "active",
        )
    )
    if unit is None or customer is None:
        raise HTTPException(status_code=422, detail="Unidade ou cliente inválido para o contrato")
    owner_actor_id = command.owner_actor_id or actor.id
    if (
        session.scalar(
            select(Actor.id).where(
                Actor.id == owner_actor_id,
                Actor.organization_id == actor.organization_id,
                Actor.status == "active",
            )
        )
        is None
    ):
        raise HTTPException(status_code=422, detail="Responsável inválido para o contrato")
    if session.scalar(
        select(Contract.id).where(
            Contract.organization_id == actor.organization_id,
            Contract.internal_number == command.internal_number.strip(),
        )
    ):
        raise HTTPException(status_code=409, detail="Número interno de contrato já utilizado")
    contract = Contract(
        organization_id=actor.organization_id,
        business_unit_id=command.business_unit_id,
        customer_company_id=command.customer_company_id,
        internal_number=command.internal_number.strip(),
        signed_on=command.signed_on,
        start_date=command.start_date,
        contract_type=command.contract_type,
        owner_actor_id=owner_actor_id,
        controlled_notes=command.controlled_notes,
        created_by_actor_id=actor.id,
    )
    session.add(contract)
    session.flush()
    response = summary(session, contract)
    record_change(
        session,
        actor=actor,
        correlation_id=request.state.correlation_id,
        action="contract.created",
        resource_type="contract",
        resource_id=contract.id,
        before_state=None,
        after_state={
            "internal_number": contract.internal_number,
            "business_unit_id": str(contract.business_unit_id),
            "customer_company_id": str(contract.customer_company_id),
            "administrative_status": contract.administrative_status,
        },
        event_type="contracts.contract.created.v1",
        event_payload={"contract_id": str(contract.id)},
    )
    assert record is not None
    complete_command(record, response.model_dump(mode="json"), response_status=201)
    session.commit()
    return response


@router.get("", response_model=list[ContractSummary])
def list_contracts(
    session: SessionDep,
    actor: Annotated[ActorContext, Depends(require_permission("contracts:read"))],
    business_unit_id: uuid.UUID | None = None,
    customer_company_id: uuid.UUID | None = None,
    administrative_status: str | None = None,
    issuer_establishment_id: uuid.UUID | None = None,
    valid_on: date | None = None,
) -> list[ContractSummary]:
    scope = unit_scope(session, actor, "contracts:read")
    statement = select(Contract).where(Contract.organization_id == actor.organization_id)
    if scope is not None:
        statement = statement.where(Contract.business_unit_id.in_(scope))
    if business_unit_id:
        if scope is not None and business_unit_id not in scope:
            return []
        statement = statement.where(Contract.business_unit_id == business_unit_id)
    if customer_company_id:
        statement = statement.where(Contract.customer_company_id == customer_company_id)
    if administrative_status:
        statement = statement.where(Contract.administrative_status == administrative_status)
    contracts = session.scalars(statement.order_by(Contract.internal_number).limit(500)).all()
    target = valid_on or date.today()
    result = []
    for contract in contracts:
        version = version_at(session, contract, target)
        if valid_on and version is None:
            continue
        if issuer_establishment_id and (
            version is None or version.issuer_establishment_id != issuer_establishment_id
        ):
            continue
        result.append(summary(session, contract))
    return result


@router.get("/{contract_id}", response_model=ContractDetail)
def read_contract(
    contract_id: uuid.UUID,
    session: SessionDep,
    actor: Annotated[ActorContext, Depends(require_permission("contracts:read"))],
) -> ContractDetail:
    return detail(session, get_contract(session, actor, contract_id, "contracts:read"))


@router.get("/{contract_id}/history", response_model=ContractDetail)
def contract_history(
    contract_id: uuid.UUID,
    session: SessionDep,
    actor: Annotated[ActorContext, Depends(require_permission("contracts:read"))],
) -> ContractDetail:
    return detail(session, get_contract(session, actor, contract_id, "contracts:read"))


@router.get("/{contract_id}/configuration", response_model=ContractConfiguration)
def configuration_on_date(
    contract_id: uuid.UUID,
    session: SessionDep,
    actor: Annotated[ActorContext, Depends(require_permission("contracts:read"))],
    on_date: Annotated[date, Query(alias="date")],
) -> ContractConfiguration:
    contract = get_contract(session, actor, contract_id, "contracts:read")
    selected = version_at(session, contract, on_date)
    if selected is None:
        raise HTTPException(status_code=404, detail="Não há configuração contratual nesta data")
    return ContractConfiguration(
        contract=summary(session, contract, on_date),
        on_date=on_date,
        operational_state=operational_state(session, contract.id, on_date),
        version=version_response(session, selected),
    )


def version_command(
    contract_id: uuid.UUID,
    command: ContractVersionCreate,
    request: Request,
    session: Session,
    actor: ActorContext,
    idempotency_key: str,
    *,
    command_name: str,
    require_future: bool,
) -> ContractVersionResponse:
    payload = {"contract_id": str(contract_id), **command.model_dump(mode="json")}
    record, replay = begin_command(
        session,
        actor=actor,
        command_name=command_name,
        idempotency_key=idempotency_key,
        payload=payload,
        correlation_id=request.state.correlation_id,
    )
    if replay is not None:
        return ContractVersionResponse.model_validate(replay)
    contract = get_contract(session, actor, contract_id, "contracts:version")
    if require_future and command.effective_from <= date.today():
        raise HTTPException(status_code=422, detail="Versão programada deve iniciar no futuro")
    version = add_version(session, actor=actor, contract=contract, command=command)
    response = version_response(session, version)
    record_change(
        session,
        actor=actor,
        correlation_id=request.state.correlation_id,
        action="contract.version_published",
        resource_type="contract_version",
        resource_id=version.id,
        before_state=None,
        after_state={
            "contract_id": str(contract.id),
            "version_number": version.version_number,
            "effective_from": version.effective_from.isoformat(),
            "issuer_establishment_id": str(version.issuer_establishment_id),
            "amount": str(version.amount),
            "change_type": version.change_type,
            "configuration_sha256": version.configuration_sha256,
        },
        event_type="contracts.version.published.v1",
        event_payload={"contract_id": str(contract.id), "contract_version_id": str(version.id)},
    )
    assert record is not None
    complete_command(record, response.model_dump(mode="json"), response_status=201)
    session.commit()
    return response


@router.post("/{contract_id}/versions", response_model=ContractVersionResponse, status_code=201)
def create_version(
    contract_id: uuid.UUID,
    command: ContractVersionCreate,
    request: Request,
    session: SessionDep,
    actor: Annotated[ActorContext, Depends(require_permission("contracts:version"))],
    idempotency_key: IdempotencyHeader,
) -> ContractVersionResponse:
    return version_command(
        contract_id,
        command,
        request,
        session,
        actor,
        idempotency_key,
        command_name="contracts.version.create",
        require_future=False,
    )


@router.post("/{contract_id}/schedule", response_model=ContractVersionResponse, status_code=201)
def schedule_version(
    contract_id: uuid.UUID,
    command: ContractVersionCreate,
    request: Request,
    session: SessionDep,
    actor: Annotated[ActorContext, Depends(require_permission("contracts:version"))],
    idempotency_key: IdempotencyHeader,
) -> ContractVersionResponse:
    return version_command(
        contract_id,
        command,
        request,
        session,
        actor,
        idempotency_key,
        command_name="contracts.version.schedule",
        require_future=True,
    )


def add_operational_event(
    session: Session,
    *,
    actor: ActorContext,
    contract: Contract,
    event_type: str,
    command: OperationalEventCreate,
    correlation_id: uuid.UUID,
    related_version_id: uuid.UUID | None = None,
) -> ContractOperationalEvent:
    if command.effective_on < date.today() or command.effective_on < contract.start_date:
        raise HTTPException(
            status_code=409,
            detail="Evento retroativo exige operação histórica autorizada, ainda fora desta etapa",
        )
    events = list(
        session.scalars(
            select(ContractOperationalEvent)
            .where(
                ContractOperationalEvent.contract_id == contract.id,
                ContractOperationalEvent.event_type.in_(("suspended", "resumed", "terminated")),
            )
            .order_by(ContractOperationalEvent.effective_on, ContractOperationalEvent.created_at)
        ).all()
    )
    if event_type != "renewed" and events and command.effective_on <= events[-1].effective_on:
        raise HTTPException(status_code=409, detail="Evento operacional fora de ordem")
    state = operational_state(session, contract.id, command.effective_on)
    if event_type == "suspended" and state != "active":
        raise HTTPException(status_code=409, detail="Somente contrato ativo pode ser suspenso")
    if event_type == "resumed" and state != "suspended":
        raise HTTPException(status_code=409, detail="Somente contrato suspenso pode ser retomado")
    if event_type == "terminated" and state == "terminated":
        raise HTTPException(status_code=409, detail="Contrato já encerrado")
    if event_type in {"suspended", "resumed", "terminated"} and not versions_for(
        session, contract.id
    ):
        raise HTTPException(status_code=409, detail="Contrato sem versão publicada")
    if event_type == "terminated":
        latest = versions_for(session, contract.id)[-1]
        if command.effective_on < latest.effective_from:
            raise HTTPException(
                status_code=409, detail="Encerramento não pode invalidar versão futura já publicada"
            )
    event = ContractOperationalEvent(
        organization_id=contract.organization_id,
        contract_id=contract.id,
        event_type=event_type,
        effective_on=command.effective_on,
        reason=command.reason,
        source=command.source,
        related_version_id=related_version_id,
        actor_id=actor.id,
        correlation_id=correlation_id,
    )
    session.add(event)
    session.flush()
    return event


def operational_command(
    contract_id: uuid.UUID,
    event_type: str,
    command: OperationalEventCreate,
    request: Request,
    session: Session,
    actor: ActorContext,
    idempotency_key: str,
    permission: str,
) -> ContractEventResponse:
    payload = {
        "contract_id": str(contract_id),
        "event_type": event_type,
        **command.model_dump(mode="json"),
    }
    record, replay = begin_command(
        session,
        actor=actor,
        command_name=f"contracts.{event_type}",
        idempotency_key=idempotency_key,
        payload=payload,
        correlation_id=request.state.correlation_id,
    )
    if replay is not None:
        return ContractEventResponse.model_validate(replay)
    contract = get_contract(session, actor, contract_id, permission)
    event = add_operational_event(
        session,
        actor=actor,
        contract=contract,
        event_type=event_type,
        command=command,
        correlation_id=request.state.correlation_id,
    )
    response = event_response(event)
    record_change(
        session,
        actor=actor,
        correlation_id=request.state.correlation_id,
        action=f"contract.{event_type}",
        resource_type="contract",
        resource_id=contract.id,
        before_state=None,
        after_state={
            "operational_event": event_type,
            "effective_on": event.effective_on.isoformat(),
        },
        event_type=f"contracts.contract.{event_type}.v1",
        event_payload={"contract_id": str(contract.id), "event_id": str(event.id)},
    )
    assert record is not None
    complete_command(record, response.model_dump(mode="json"), response_status=201)
    session.commit()
    return response


@router.post("/{contract_id}/suspend", response_model=ContractEventResponse, status_code=201)
def suspend_contract(
    contract_id: uuid.UUID,
    command: OperationalEventCreate,
    request: Request,
    session: SessionDep,
    actor: Annotated[ActorContext, Depends(require_permission("contracts:suspend"))],
    idempotency_key: IdempotencyHeader,
) -> ContractEventResponse:
    return operational_command(
        contract_id,
        "suspended",
        command,
        request,
        session,
        actor,
        idempotency_key,
        "contracts:suspend",
    )


@router.post("/{contract_id}/resume", response_model=ContractEventResponse, status_code=201)
def resume_contract(
    contract_id: uuid.UUID,
    command: OperationalEventCreate,
    request: Request,
    session: SessionDep,
    actor: Annotated[ActorContext, Depends(require_permission("contracts:resume"))],
    idempotency_key: IdempotencyHeader,
) -> ContractEventResponse:
    return operational_command(
        contract_id,
        "resumed",
        command,
        request,
        session,
        actor,
        idempotency_key,
        "contracts:resume",
    )


@router.post("/{contract_id}/terminate", response_model=ContractEventResponse, status_code=201)
def terminate_contract(
    contract_id: uuid.UUID,
    command: OperationalEventCreate,
    request: Request,
    session: SessionDep,
    actor: Annotated[ActorContext, Depends(require_permission("contracts:terminate"))],
    idempotency_key: IdempotencyHeader,
) -> ContractEventResponse:
    return operational_command(
        contract_id,
        "terminated",
        command,
        request,
        session,
        actor,
        idempotency_key,
        "contracts:terminate",
    )


@router.post("/{contract_id}/renew", response_model=ContractDetail, status_code=201)
def renew_contract(
    contract_id: uuid.UUID,
    command: ContractVersionCreate,
    request: Request,
    session: SessionDep,
    actor: Annotated[ActorContext, Depends(require_permission("contracts:version"))],
    idempotency_key: IdempotencyHeader,
) -> ContractDetail:
    if command.change_type != "renewal":
        raise HTTPException(status_code=422, detail="Renovação exige change_type renewal")
    payload = {"contract_id": str(contract_id), **command.model_dump(mode="json")}
    record, replay = begin_command(
        session,
        actor=actor,
        command_name="contracts.renew",
        idempotency_key=idempotency_key,
        payload=payload,
        correlation_id=request.state.correlation_id,
    )
    if replay is not None:
        return ContractDetail.model_validate(replay)
    contract = get_contract(session, actor, contract_id, "contracts:version")
    version = add_version(session, actor=actor, contract=contract, command=command)
    add_operational_event(
        session,
        actor=actor,
        contract=contract,
        event_type="renewed",
        command=OperationalEventCreate(
            effective_on=command.effective_from,
            reason=command.change_reason,
            source=command.source,
        ),
        correlation_id=request.state.correlation_id,
        related_version_id=version.id,
    )
    response = detail(session, contract)
    record_change(
        session,
        actor=actor,
        correlation_id=request.state.correlation_id,
        action="contract.renewed",
        resource_type="contract",
        resource_id=contract.id,
        before_state=None,
        after_state={
            "renewal_version_id": str(version.id),
            "effective_from": version.effective_from.isoformat(),
        },
        event_type="contracts.contract.renewed.v1",
        event_payload={"contract_id": str(contract.id), "contract_version_id": str(version.id)},
    )
    assert record is not None
    complete_command(record, response.model_dump(mode="json"), response_status=201)
    session.commit()
    return response
