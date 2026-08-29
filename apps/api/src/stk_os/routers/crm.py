from __future__ import annotations

import re
import uuid
from datetime import UTC, datetime
from decimal import Decimal
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from stk_os.commands import begin_command, complete_command, record_change
from stk_os.crm_schemas import (
    ActivityCreate,
    ActivityResponse,
    CatalogItem,
    Company360Response,
    CompanyCreate,
    CompanySummary,
    CompanyUpdate,
    ContactMethodInput,
    ContactMethodResponse,
    CrmImportCreate,
    CrmImportResponse,
    ImportRowResult,
    KanbanColumn,
    KanbanResponse,
    OpportunityCreate,
    OpportunityResponse,
    OpportunityStageMove,
    OpportunityStatusUpdate,
    Person360Response,
    PersonCompanyLinkCreate,
    PersonCompanyLinkResponse,
    PersonCreate,
    PersonSummary,
    PersonUpdate,
    PipelineItem,
    PipelineStageItem,
    ReferenceDataResponse,
    SearchResult,
    TaskCreate,
    TaskResponse,
)
from stk_os.database import SessionDep
from stk_os.dependencies import require_permission
from stk_os.models import (
    Activity,
    BusinessUnit,
    Company,
    CompanyBusinessUnit,
    ContactMethod,
    CrmImportJob,
    CrmImportRow,
    LeadSource,
    LossReason,
    Opportunity,
    OpportunityContact,
    OpportunityProduct,
    OpportunityStageHistory,
    Person,
    PersonBusinessUnit,
    PersonCompanyRelationship,
    Pipeline,
    PipelineStage,
    ProductService,
    Task,
)
from stk_os.schemas import ActorContext
from stk_os.security import canonical_hash

router = APIRouter(prefix="/crm", tags=["crm"])
IdempotencyHeader = Annotated[str, Header(alias="Idempotency-Key", min_length=8, max_length=255)]


def digits(value: str | None) -> str | None:
    if value is None:
        return None
    return re.sub(r"\D", "", value)


def normalize_tax_id(value: str | None, *, length: int) -> str | None:
    normalized = digits(value)
    if normalized is not None and len(normalized) != length:
        raise HTTPException(status_code=422, detail=f"Documento deve possuir {length} dígitos")
    return normalized


def normalize_state(value: str | None) -> str | None:
    return value.strip().upper() if value else None


def normalize_contact(item: ContactMethodInput) -> str:
    if item.kind == "email":
        normalized = item.value.strip().lower()
        if "@" not in normalized:
            raise HTTPException(status_code=422, detail="E-mail inválido")
        return normalized
    normalized = digits(item.value) or ""
    if len(normalized) < 8:
        raise HTTPException(status_code=422, detail="Telefone inválido")
    return normalized


def aware(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


def get_owned(session: Session, model: type[Any], item_id: uuid.UUID, organization_id: uuid.UUID):
    item = session.scalar(
        select(model).where(model.id == item_id, model.organization_id == organization_id)
    )
    if item is None:
        raise HTTPException(status_code=404, detail="Registro não encontrado")
    return item


def ensure_units(
    session: Session, organization_id: uuid.UUID, unit_ids: list[uuid.UUID]
) -> list[BusinessUnit]:
    unique_ids = list(dict.fromkeys(unit_ids))
    units = session.scalars(
        select(BusinessUnit).where(
            BusinessUnit.organization_id == organization_id,
            BusinessUnit.id.in_(unique_ids),
            BusinessUnit.status == "active",
        )
    ).all()
    if len(units) != len(unique_ids):
        raise HTTPException(status_code=422, detail="Unidade de negócio inválida")
    return list(units)


def ensure_source(
    session: Session, organization_id: uuid.UUID, source_id: uuid.UUID | None
) -> LeadSource | None:
    if source_id is None:
        return None
    source = session.scalar(
        select(LeadSource).where(
            LeadSource.id == source_id,
            LeadSource.organization_id == organization_id,
            LeadSource.status == "active",
        )
    )
    if source is None:
        raise HTTPException(status_code=422, detail="Origem inválida")
    return source


def contact_response(item: ContactMethod) -> ContactMethodResponse:
    return ContactMethodResponse(
        id=item.id,
        kind=item.kind,
        label=item.label,
        value=item.value,
        normalized_value=item.normalized_value,
        is_primary=item.is_primary,
        status=item.status,
    )


def contacts_for(
    session: Session, *, person_id: uuid.UUID | None = None, company_id: uuid.UUID | None = None
) -> list[ContactMethodResponse]:
    statement = select(ContactMethod).where(ContactMethod.status == "active")
    if person_id is not None:
        statement = statement.where(ContactMethod.person_id == person_id)
    else:
        statement = statement.where(ContactMethod.company_id == company_id)
    return [contact_response(item) for item in session.scalars(statement).all()]


def person_summary(session: Session, person: Person) -> PersonSummary:
    unit_ids = list(
        session.scalars(
            select(PersonBusinessUnit.business_unit_id).where(
                PersonBusinessUnit.person_id == person.id,
                PersonBusinessUnit.status == "active",
            )
        ).all()
    )
    return PersonSummary(
        id=person.id,
        full_name=person.full_name,
        tax_id=person.tax_id,
        city=person.city,
        state_code=person.state_code,
        status=person.status,
        business_unit_ids=unit_ids,
        contacts=contacts_for(session, person_id=person.id),
        created_at=person.created_at,
        updated_at=person.updated_at,
    )


def company_summary(session: Session, company: Company) -> CompanySummary:
    unit_rows = session.execute(
        select(BusinessUnit.id, BusinessUnit.code, BusinessUnit.name)
        .join(CompanyBusinessUnit, CompanyBusinessUnit.business_unit_id == BusinessUnit.id)
        .where(
            CompanyBusinessUnit.company_id == company.id,
            CompanyBusinessUnit.status == "active",
        )
        .order_by(BusinessUnit.name)
    ).all()
    units = [CatalogItem(id=row.id, code=row.code, name=row.name) for row in unit_rows]
    return CompanySummary(
        id=company.id,
        legal_name=company.legal_name,
        trade_name=company.trade_name,
        tax_id=company.tax_id,
        address_line=company.address_line,
        city=company.city,
        state_code=company.state_code,
        municipality_code=company.municipality_code,
        postal_code=company.postal_code,
        site=company.site,
        status=company.status,
        business_unit_ids=[item.id for item in units],
        business_units=units,
        contacts=contacts_for(session, company_id=company.id),
        created_at=company.created_at,
        updated_at=company.updated_at,
    )


def task_response(item: Task) -> TaskResponse:
    return TaskResponse(
        id=item.id,
        business_unit_id=item.business_unit_id,
        opportunity_id=item.opportunity_id,
        person_id=item.person_id,
        company_id=item.company_id,
        title=item.title,
        due_at=item.due_at,
        priority=item.priority,
        status=item.status,
        completed_at=item.completed_at,
    )


def activity_response(item: Activity) -> ActivityResponse:
    return ActivityResponse(
        id=item.id,
        business_unit_id=item.business_unit_id,
        opportunity_id=item.opportunity_id,
        person_id=item.person_id,
        company_id=item.company_id,
        activity_type=item.activity_type,
        occurred_at=item.occurred_at,
        summary=item.summary,
        origin=item.origin,
        performed_by=item.performed_by,
        status=item.status,
    )


def opportunity_response(session: Session, opportunity: Opportunity) -> OpportunityResponse:
    person_ids = list(
        session.scalars(
            select(OpportunityContact.person_id).where(
                OpportunityContact.opportunity_id == opportunity.id
            )
        ).all()
    )
    product_rows = session.execute(
        select(ProductService.id, ProductService.name)
        .join(OpportunityProduct, OpportunityProduct.product_service_id == ProductService.id)
        .where(OpportunityProduct.opportunity_id == opportunity.id)
        .order_by(ProductService.name)
    ).all()
    company = session.get(Company, opportunity.company_id) if opportunity.company_id else None
    first_person = session.get(Person, person_ids[0]) if person_ids else None
    customer_name = (
        (company.trade_name or company.legal_name)
        if company
        else (first_person.full_name if first_person else "Sem participante")
    )
    last_interaction = session.scalar(
        select(func.max(Activity.occurred_at)).where(
            Activity.opportunity_id == opportunity.id,
            Activity.status == "active",
        )
    )
    stage_entered = (
        session.scalar(
            select(func.max(OpportunityStageHistory.changed_at)).where(
                OpportunityStageHistory.opportunity_id == opportunity.id,
                OpportunityStageHistory.to_stage_id == opportunity.stage_id,
            )
        )
        or opportunity.entered_at
    )
    next_task = session.scalar(
        select(Task)
        .where(Task.opportunity_id == opportunity.id, Task.status == "open")
        .order_by(Task.due_at, Task.created_at)
        .limit(1)
    )
    return OpportunityResponse(
        id=opportunity.id,
        business_unit_id=opportunity.business_unit_id,
        pipeline_id=opportunity.pipeline_id,
        stage_id=opportunity.stage_id,
        company_id=opportunity.company_id,
        title=opportunity.title,
        status=opportunity.status,
        value=Decimal(opportunity.value) if opportunity.value is not None else None,
        currency=opportunity.currency,
        lead_source_id=opportunity.lead_source_id,
        loss_reason_id=opportunity.loss_reason_id,
        expected_close_date=opportunity.expected_close_date,
        person_ids=person_ids,
        product_service_ids=[row.id for row in product_rows],
        customer_name=customer_name,
        product_names=[row.name for row in product_rows],
        last_interaction_at=last_interaction,
        stage_entered_at=stage_entered,
        next_action=task_response(next_task) if next_task else None,
        created_at=opportunity.created_at,
        updated_at=opportunity.updated_at,
    )


def add_contacts(
    session: Session,
    *,
    organization_id: uuid.UUID,
    contacts: list[ContactMethodInput],
    person_id: uuid.UUID | None = None,
    company_id: uuid.UUID | None = None,
) -> None:
    seen: set[tuple[str, str]] = set()
    for contact in contacts:
        normalized = normalize_contact(contact)
        key = (contact.kind, normalized)
        if key in seen:
            continue
        seen.add(key)
        session.add(
            ContactMethod(
                organization_id=organization_id,
                person_id=person_id,
                company_id=company_id,
                kind=contact.kind,
                label=contact.label,
                value=contact.value.strip(),
                normalized_value=normalized,
                is_primary=contact.is_primary,
            )
        )


def link_person_units(
    session: Session,
    *,
    actor: ActorContext,
    person_id: uuid.UUID,
    unit_ids: list[uuid.UUID],
    source_id: uuid.UUID | None,
) -> None:
    ensure_units(session, actor.organization_id, unit_ids)
    ensure_source(session, actor.organization_id, source_id)
    existing = set(
        session.scalars(
            select(PersonBusinessUnit.business_unit_id).where(
                PersonBusinessUnit.person_id == person_id
            )
        ).all()
    )
    for unit_id in dict.fromkeys(unit_ids):
        if unit_id not in existing:
            session.add(
                PersonBusinessUnit(
                    organization_id=actor.organization_id,
                    person_id=person_id,
                    business_unit_id=unit_id,
                    lead_source_id=source_id,
                    owner_actor_id=actor.id,
                )
            )


def link_company_units(
    session: Session,
    *,
    actor: ActorContext,
    company_id: uuid.UUID,
    unit_ids: list[uuid.UUID],
    source_id: uuid.UUID | None,
) -> None:
    ensure_units(session, actor.organization_id, unit_ids)
    ensure_source(session, actor.organization_id, source_id)
    existing = set(
        session.scalars(
            select(CompanyBusinessUnit.business_unit_id).where(
                CompanyBusinessUnit.company_id == company_id
            )
        ).all()
    )
    for unit_id in dict.fromkeys(unit_ids):
        if unit_id not in existing:
            session.add(
                CompanyBusinessUnit(
                    organization_id=actor.organization_id,
                    company_id=company_id,
                    business_unit_id=unit_id,
                    lead_source_id=source_id,
                    owner_actor_id=actor.id,
                )
            )


@router.get("/reference-data", response_model=ReferenceDataResponse)
def reference_data(
    session: SessionDep,
    actor: Annotated[ActorContext, Depends(require_permission("crm:read"))],
) -> ReferenceDataResponse:
    units = session.scalars(
        select(BusinessUnit)
        .where(
            BusinessUnit.organization_id == actor.organization_id, BusinessUnit.status == "active"
        )
        .order_by(BusinessUnit.name)
    ).all()
    sources = session.scalars(
        select(LeadSource)
        .where(LeadSource.organization_id == actor.organization_id, LeadSource.status == "active")
        .order_by(LeadSource.name)
    ).all()
    products = session.scalars(
        select(ProductService)
        .where(
            ProductService.organization_id == actor.organization_id,
            ProductService.status == "active",
        )
        .order_by(ProductService.name)
    ).all()
    reasons = session.scalars(
        select(LossReason)
        .where(LossReason.organization_id == actor.organization_id, LossReason.status == "active")
        .order_by(LossReason.name)
    ).all()
    pipelines = session.scalars(
        select(Pipeline)
        .where(Pipeline.organization_id == actor.organization_id, Pipeline.status == "active")
        .order_by(Pipeline.business_unit_id, Pipeline.name)
    ).all()
    pipeline_items = []
    for pipeline in pipelines:
        stages = session.scalars(
            select(PipelineStage)
            .where(PipelineStage.pipeline_id == pipeline.id, PipelineStage.status == "active")
            .order_by(PipelineStage.position)
        ).all()
        pipeline_items.append(
            PipelineItem(
                id=pipeline.id,
                business_unit_id=pipeline.business_unit_id,
                code=pipeline.code,
                name=pipeline.name,
                kind=pipeline.kind,
                stages=[
                    PipelineStageItem(
                        id=stage.id,
                        code=stage.code,
                        name=stage.name,
                        position=stage.position,
                        sla_days=stage.sla_days,
                    )
                    for stage in stages
                ],
            )
        )
    return ReferenceDataResponse(
        business_units=[CatalogItem(id=item.id, code=item.code, name=item.name) for item in units],
        lead_sources=[CatalogItem(id=item.id, code=item.code, name=item.name) for item in sources],
        products_services=[
            CatalogItem(
                id=item.id,
                code=item.code,
                name=item.name,
                business_unit_id=item.business_unit_id,
                category=item.category,
            )
            for item in products
        ],
        loss_reasons=[
            CatalogItem(
                id=item.id,
                code=item.code,
                name=item.name,
                business_unit_id=item.business_unit_id,
            )
            for item in reasons
        ],
        pipelines=pipeline_items,
    )


@router.get("/people", response_model=list[PersonSummary])
def list_people(
    session: SessionDep,
    actor: Annotated[ActorContext, Depends(require_permission("crm:read"))],
    business_unit_id: uuid.UUID | None = None,
    query: Annotated[str | None, Query(alias="q", max_length=100)] = None,
) -> list[PersonSummary]:
    statement = select(Person).where(Person.organization_id == actor.organization_id)
    if business_unit_id:
        statement = statement.join(PersonBusinessUnit).where(
            PersonBusinessUnit.business_unit_id == business_unit_id,
            PersonBusinessUnit.status == "active",
        )
    if query:
        pattern = f"%{query.strip().lower()}%"
        statement = statement.where(func.lower(Person.full_name).like(pattern))
    people = session.scalars(statement.distinct().order_by(Person.full_name).limit(100)).all()
    return [person_summary(session, item) for item in people]


@router.post("/people", response_model=PersonSummary, status_code=201)
def create_person(
    command: PersonCreate,
    request: Request,
    session: SessionDep,
    actor: Annotated[ActorContext, Depends(require_permission("crm:write"))],
    idempotency_key: IdempotencyHeader,
) -> PersonSummary:
    record, replay = begin_command(
        session,
        actor=actor,
        command_name="crm.person.create",
        idempotency_key=idempotency_key,
        payload=command.model_dump(mode="json"),
        correlation_id=request.state.correlation_id,
    )
    if replay is not None:
        return PersonSummary.model_validate(replay)
    tax_id = normalize_tax_id(command.tax_id, length=11)
    if tax_id and session.scalar(
        select(Person.id).where(
            Person.organization_id == actor.organization_id, Person.tax_id == tax_id
        )
    ):
        raise HTTPException(status_code=409, detail="Pessoa com este CPF já cadastrada")
    person = Person(
        organization_id=actor.organization_id,
        full_name=command.full_name.strip(),
        tax_id=tax_id,
        city=command.city,
        state_code=normalize_state(command.state_code),
        notes=command.notes,
        created_by_actor_id=actor.id,
    )
    session.add(person)
    session.flush()
    add_contacts(
        session,
        organization_id=actor.organization_id,
        contacts=command.contacts,
        person_id=person.id,
    )
    link_person_units(
        session,
        actor=actor,
        person_id=person.id,
        unit_ids=command.business_unit_ids,
        source_id=command.lead_source_id,
    )
    session.flush()
    response = person_summary(session, person)
    record_change(
        session,
        actor=actor,
        correlation_id=request.state.correlation_id,
        action="person.created",
        resource_type="person",
        resource_id=person.id,
        before_state=None,
        after_state={"full_name": person.full_name, "status": person.status},
        event_type="crm.person.created.v1",
        event_payload={"person_id": str(person.id)},
    )
    assert record is not None
    complete_command(record, response.model_dump(mode="json"), response_status=201)
    session.commit()
    return response


@router.patch("/people/{person_id}", response_model=PersonSummary)
def update_person(
    person_id: uuid.UUID,
    command: PersonUpdate,
    request: Request,
    session: SessionDep,
    actor: Annotated[ActorContext, Depends(require_permission("crm:write"))],
    idempotency_key: IdempotencyHeader,
) -> PersonSummary:
    record, replay = begin_command(
        session,
        actor=actor,
        command_name="crm.person.update",
        idempotency_key=idempotency_key,
        payload={
            "person_id": str(person_id),
            **command.model_dump(mode="json", exclude_unset=True),
        },
        correlation_id=request.state.correlation_id,
    )
    if replay is not None:
        return PersonSummary.model_validate(replay)
    person = get_owned(session, Person, person_id, actor.organization_id)
    before = {"full_name": person.full_name, "status": person.status}
    for field, value in command.model_dump(exclude_unset=True).items():
        if field == "state_code":
            value = normalize_state(value)
        if field == "tax_id":
            value = normalize_tax_id(value, length=11)
        if field == "full_name" and value:
            value = value.strip()
        setattr(person, field, value)
    person.updated_at = datetime.now(UTC)
    session.flush()
    response = person_summary(session, person)
    record_change(
        session,
        actor=actor,
        correlation_id=request.state.correlation_id,
        action="person.updated",
        resource_type="person",
        resource_id=person.id,
        before_state=before,
        after_state={"full_name": person.full_name, "status": person.status},
        event_type="crm.person.updated.v1",
        event_payload={"person_id": str(person.id)},
    )
    assert record is not None
    complete_command(record, response.model_dump(mode="json"), response_status=200)
    session.commit()
    return response


@router.get("/companies", response_model=list[CompanySummary])
def list_companies(
    session: SessionDep,
    actor: Annotated[ActorContext, Depends(require_permission("crm:read"))],
    business_unit_id: uuid.UUID | None = None,
    query: Annotated[str | None, Query(alias="q", max_length=100)] = None,
) -> list[CompanySummary]:
    statement = select(Company).where(Company.organization_id == actor.organization_id)
    if business_unit_id:
        statement = statement.join(CompanyBusinessUnit).where(
            CompanyBusinessUnit.business_unit_id == business_unit_id,
            CompanyBusinessUnit.status == "active",
        )
    if query:
        pattern = f"%{query.strip().lower()}%"
        statement = statement.where(
            or_(
                func.lower(Company.legal_name).like(pattern),
                func.lower(func.coalesce(Company.trade_name, "")).like(pattern),
            )
        )
    companies = session.scalars(statement.distinct().order_by(Company.legal_name).limit(100)).all()
    return [company_summary(session, item) for item in companies]


@router.post("/companies", response_model=CompanySummary, status_code=201)
def create_company(
    command: CompanyCreate,
    request: Request,
    session: SessionDep,
    actor: Annotated[ActorContext, Depends(require_permission("crm:write"))],
    idempotency_key: IdempotencyHeader,
) -> CompanySummary:
    record, replay = begin_command(
        session,
        actor=actor,
        command_name="crm.company.create",
        idempotency_key=idempotency_key,
        payload=command.model_dump(mode="json"),
        correlation_id=request.state.correlation_id,
    )
    if replay is not None:
        return CompanySummary.model_validate(replay)
    tax_id = normalize_tax_id(command.tax_id, length=14)
    if tax_id and session.scalar(
        select(Company.id).where(
            Company.organization_id == actor.organization_id, Company.tax_id == tax_id
        )
    ):
        raise HTTPException(status_code=409, detail="Empresa com este CNPJ já cadastrada")
    company = Company(
        organization_id=actor.organization_id,
        legal_name=command.legal_name.strip(),
        trade_name=command.trade_name,
        tax_id=tax_id,
        address_line=command.address_line,
        city=command.city,
        state_code=normalize_state(command.state_code),
        municipality_code=command.municipality_code,
        postal_code=command.postal_code,
        site=command.site,
        notes=command.notes,
        created_by_actor_id=actor.id,
    )
    session.add(company)
    session.flush()
    add_contacts(
        session,
        organization_id=actor.organization_id,
        contacts=command.contacts,
        company_id=company.id,
    )
    link_company_units(
        session,
        actor=actor,
        company_id=company.id,
        unit_ids=command.business_unit_ids,
        source_id=command.lead_source_id,
    )
    session.flush()
    response = company_summary(session, company)
    record_change(
        session,
        actor=actor,
        correlation_id=request.state.correlation_id,
        action="company.created",
        resource_type="company",
        resource_id=company.id,
        before_state=None,
        after_state={"legal_name": company.legal_name, "status": company.status},
        event_type="crm.company.created.v1",
        event_payload={"company_id": str(company.id)},
    )
    assert record is not None
    complete_command(record, response.model_dump(mode="json"), response_status=201)
    session.commit()
    return response


@router.patch("/companies/{company_id}", response_model=CompanySummary)
def update_company(
    company_id: uuid.UUID,
    command: CompanyUpdate,
    request: Request,
    session: SessionDep,
    actor: Annotated[ActorContext, Depends(require_permission("crm:write"))],
    idempotency_key: IdempotencyHeader,
) -> CompanySummary:
    record, replay = begin_command(
        session,
        actor=actor,
        command_name="crm.company.update",
        idempotency_key=idempotency_key,
        payload={
            "company_id": str(company_id),
            **command.model_dump(mode="json", exclude_unset=True),
        },
        correlation_id=request.state.correlation_id,
    )
    if replay is not None:
        return CompanySummary.model_validate(replay)
    company = get_owned(session, Company, company_id, actor.organization_id)
    before = {"legal_name": company.legal_name, "status": company.status}
    for field, value in command.model_dump(exclude_unset=True).items():
        if field == "state_code":
            value = normalize_state(value)
        if field == "tax_id":
            value = normalize_tax_id(value, length=14)
        if field == "legal_name" and value:
            value = value.strip()
        setattr(company, field, value)
    company.updated_at = datetime.now(UTC)
    session.flush()
    response = company_summary(session, company)
    record_change(
        session,
        actor=actor,
        correlation_id=request.state.correlation_id,
        action="company.updated",
        resource_type="company",
        resource_id=company.id,
        before_state=before,
        after_state={"legal_name": company.legal_name, "status": company.status},
        event_type="crm.company.updated.v1",
        event_payload={"company_id": str(company.id)},
    )
    assert record is not None
    complete_command(record, response.model_dump(mode="json"), response_status=200)
    session.commit()
    return response


@router.post(
    "/relationships/person-company", response_model=PersonCompanyLinkResponse, status_code=201
)
def link_person_company(
    command: PersonCompanyLinkCreate,
    request: Request,
    session: SessionDep,
    actor: Annotated[ActorContext, Depends(require_permission("crm:write"))],
    idempotency_key: IdempotencyHeader,
) -> PersonCompanyLinkResponse:
    record, replay = begin_command(
        session,
        actor=actor,
        command_name="crm.person_company.link",
        idempotency_key=idempotency_key,
        payload=command.model_dump(mode="json"),
        correlation_id=request.state.correlation_id,
    )
    if replay is not None:
        return PersonCompanyLinkResponse.model_validate(replay)
    get_owned(session, Person, command.person_id, actor.organization_id)
    get_owned(session, Company, command.company_id, actor.organization_id)
    existing = session.scalar(
        select(PersonCompanyRelationship).where(
            PersonCompanyRelationship.person_id == command.person_id,
            PersonCompanyRelationship.company_id == command.company_id,
            func.lower(PersonCompanyRelationship.role) == command.role.strip().lower(),
        )
    )
    if existing:
        raise HTTPException(status_code=409, detail="Vínculo já cadastrado")
    item = PersonCompanyRelationship(
        organization_id=actor.organization_id,
        person_id=command.person_id,
        company_id=command.company_id,
        role=command.role.strip(),
        is_primary=command.is_primary,
    )
    session.add(item)
    session.flush()
    response = PersonCompanyLinkResponse(
        id=item.id,
        person_id=item.person_id,
        company_id=item.company_id,
        role=item.role,
        is_primary=item.is_primary,
        status=item.status,
    )
    record_change(
        session,
        actor=actor,
        correlation_id=request.state.correlation_id,
        action="person_company_relationship.created",
        resource_type="person_company_relationship",
        resource_id=item.id,
        before_state=None,
        after_state={"role": item.role, "status": item.status},
        event_type="crm.person_company_relationship.created.v1",
        event_payload={"relationship_id": str(item.id)},
    )
    assert record is not None
    complete_command(record, response.model_dump(mode="json"), response_status=201)
    session.commit()
    return response


def validated_opportunity_references(
    session: Session, actor: ActorContext, command: OpportunityCreate
) -> tuple[Pipeline, PipelineStage]:
    ensure_units(session, actor.organization_id, [command.business_unit_id])
    ensure_source(session, actor.organization_id, command.lead_source_id)
    pipeline = session.scalar(
        select(Pipeline).where(
            Pipeline.id == command.pipeline_id,
            Pipeline.organization_id == actor.organization_id,
            Pipeline.business_unit_id == command.business_unit_id,
            Pipeline.status == "active",
        )
    )
    if pipeline is None:
        raise HTTPException(status_code=422, detail="Pipeline inválido para a unidade")
    stage = session.scalar(
        select(PipelineStage).where(
            PipelineStage.id == command.stage_id,
            PipelineStage.pipeline_id == pipeline.id,
            PipelineStage.status == "active",
        )
    )
    if stage is None:
        raise HTTPException(status_code=422, detail="Etapa inválida para o pipeline")
    if command.company_id:
        get_owned(session, Company, command.company_id, actor.organization_id)
    for person_id in dict.fromkeys(command.person_ids):
        get_owned(session, Person, person_id, actor.organization_id)
    product_count = session.scalar(
        select(func.count())
        .select_from(ProductService)
        .where(
            ProductService.id.in_(list(dict.fromkeys(command.product_service_ids))),
            ProductService.organization_id == actor.organization_id,
            ProductService.business_unit_id == command.business_unit_id,
            ProductService.status == "active",
        )
    )
    if product_count != len(set(command.product_service_ids)):
        raise HTTPException(status_code=422, detail="Produto/serviço inválido para a unidade")
    return pipeline, stage


@router.post("/opportunities", response_model=OpportunityResponse, status_code=201)
def create_opportunity(
    command: OpportunityCreate,
    request: Request,
    session: SessionDep,
    actor: Annotated[ActorContext, Depends(require_permission("crm:write"))],
    idempotency_key: IdempotencyHeader,
) -> OpportunityResponse:
    record, replay = begin_command(
        session,
        actor=actor,
        command_name="crm.opportunity.create",
        idempotency_key=idempotency_key,
        payload=command.model_dump(mode="json"),
        correlation_id=request.state.correlation_id,
    )
    if replay is not None:
        return OpportunityResponse.model_validate(replay)
    validated_opportunity_references(session, actor, command)
    opportunity = Opportunity(
        organization_id=actor.organization_id,
        business_unit_id=command.business_unit_id,
        pipeline_id=command.pipeline_id,
        stage_id=command.stage_id,
        company_id=command.company_id,
        title=command.title.strip(),
        value=command.value,
        currency=command.currency.upper(),
        lead_source_id=command.lead_source_id,
        owner_actor_id=actor.id,
        expected_close_date=command.expected_close_date,
        notes=command.notes,
    )
    session.add(opportunity)
    session.flush()
    for index, person_id in enumerate(dict.fromkeys(command.person_ids)):
        session.add(
            OpportunityContact(
                opportunity_id=opportunity.id,
                person_id=person_id,
                role="contact",
                is_primary=index == 0,
            )
        )
        link_person_units(
            session,
            actor=actor,
            person_id=person_id,
            unit_ids=[command.business_unit_id],
            source_id=command.lead_source_id,
        )
    if command.company_id:
        link_company_units(
            session,
            actor=actor,
            company_id=command.company_id,
            unit_ids=[command.business_unit_id],
            source_id=command.lead_source_id,
        )
    for product_id in dict.fromkeys(command.product_service_ids):
        session.add(
            OpportunityProduct(
                opportunity_id=opportunity.id,
                product_service_id=product_id,
            )
        )
    session.add(
        OpportunityStageHistory(
            organization_id=actor.organization_id,
            opportunity_id=opportunity.id,
            from_stage_id=None,
            to_stage_id=opportunity.stage_id,
            actor_id=actor.id,
            source="api",
            note="Oportunidade criada",
        )
    )
    session.add(
        Task(
            organization_id=actor.organization_id,
            business_unit_id=command.business_unit_id,
            opportunity_id=opportunity.id,
            company_id=command.company_id,
            person_id=command.person_ids[0] if command.person_ids else None,
            title=command.next_action_title.strip(),
            due_at=aware(command.next_action_due_at),
            owner_actor_id=actor.id,
        )
    )
    session.flush()
    response = opportunity_response(session, opportunity)
    record_change(
        session,
        actor=actor,
        correlation_id=request.state.correlation_id,
        action="opportunity.created",
        resource_type="opportunity",
        resource_id=opportunity.id,
        before_state=None,
        after_state={
            "title": opportunity.title,
            "status": opportunity.status,
            "stage_id": str(opportunity.stage_id),
        },
        event_type="crm.opportunity.created.v1",
        event_payload={"opportunity_id": str(opportunity.id)},
    )
    assert record is not None
    complete_command(record, response.model_dump(mode="json"), response_status=201)
    session.commit()
    return response


@router.get("/opportunities", response_model=list[OpportunityResponse])
def list_opportunities(
    session: SessionDep,
    actor: Annotated[ActorContext, Depends(require_permission("crm:read"))],
    business_unit_id: uuid.UUID | None = None,
    pipeline_id: uuid.UUID | None = None,
    status: str | None = "open",
) -> list[OpportunityResponse]:
    statement = select(Opportunity).where(Opportunity.organization_id == actor.organization_id)
    if business_unit_id:
        statement = statement.where(Opportunity.business_unit_id == business_unit_id)
    if pipeline_id:
        statement = statement.where(Opportunity.pipeline_id == pipeline_id)
    if status:
        if status not in {"open", "won", "lost"}:
            raise HTTPException(status_code=422, detail="Status inválido")
        statement = statement.where(Opportunity.status == status)
    items = session.scalars(statement.order_by(Opportunity.updated_at.desc()).limit(200)).all()
    return [opportunity_response(session, item) for item in items]


@router.get("/kanban/{pipeline_id}", response_model=KanbanResponse)
def get_kanban(
    pipeline_id: uuid.UUID,
    session: SessionDep,
    actor: Annotated[ActorContext, Depends(require_permission("crm:read"))],
) -> KanbanResponse:
    pipeline = session.scalar(
        select(Pipeline).where(
            Pipeline.id == pipeline_id,
            Pipeline.organization_id == actor.organization_id,
            Pipeline.status == "active",
        )
    )
    if pipeline is None:
        raise HTTPException(status_code=404, detail="Pipeline não encontrado")
    stages = session.scalars(
        select(PipelineStage)
        .where(PipelineStage.pipeline_id == pipeline.id, PipelineStage.status == "active")
        .order_by(PipelineStage.position)
    ).all()
    opportunities = session.scalars(
        select(Opportunity).where(
            Opportunity.organization_id == actor.organization_id,
            Opportunity.pipeline_id == pipeline.id,
            Opportunity.status == "open",
        )
    ).all()
    by_stage: dict[uuid.UUID, list[OpportunityResponse]] = {stage.id: [] for stage in stages}
    for opportunity in opportunities:
        by_stage.setdefault(opportunity.stage_id, []).append(
            opportunity_response(session, opportunity)
        )
    pipeline_item = PipelineItem(
        id=pipeline.id,
        business_unit_id=pipeline.business_unit_id,
        code=pipeline.code,
        name=pipeline.name,
        kind=pipeline.kind,
        stages=[
            PipelineStageItem(
                id=stage.id,
                code=stage.code,
                name=stage.name,
                position=stage.position,
                sla_days=stage.sla_days,
            )
            for stage in stages
        ],
    )
    return KanbanResponse(
        pipeline=pipeline_item,
        columns=[
            KanbanColumn(stage=pipeline_item.stages[index], opportunities=by_stage[stage.id])
            for index, stage in enumerate(stages)
        ],
    )


@router.patch("/opportunities/{opportunity_id}/stage", response_model=OpportunityResponse)
def move_opportunity_stage(
    opportunity_id: uuid.UUID,
    command: OpportunityStageMove,
    request: Request,
    session: SessionDep,
    actor: Annotated[ActorContext, Depends(require_permission("crm:write"))],
    idempotency_key: IdempotencyHeader,
) -> OpportunityResponse:
    record, replay = begin_command(
        session,
        actor=actor,
        command_name="crm.opportunity.move_stage",
        idempotency_key=idempotency_key,
        payload={"opportunity_id": str(opportunity_id), **command.model_dump(mode="json")},
        correlation_id=request.state.correlation_id,
    )
    if replay is not None:
        return OpportunityResponse.model_validate(replay)
    opportunity = get_owned(session, Opportunity, opportunity_id, actor.organization_id)
    if opportunity.status != "open":
        raise HTTPException(status_code=409, detail="Somente negócio aberto pode mudar de etapa")
    stage = session.scalar(
        select(PipelineStage).where(
            PipelineStage.id == command.stage_id,
            PipelineStage.pipeline_id == opportunity.pipeline_id,
            PipelineStage.status == "active",
        )
    )
    if stage is None:
        raise HTTPException(status_code=422, detail="Etapa inválida para o pipeline")
    before_stage_id = opportunity.stage_id
    if before_stage_id != stage.id:
        opportunity.stage_id = stage.id
        opportunity.updated_at = datetime.now(UTC)
        session.add(
            OpportunityStageHistory(
                organization_id=actor.organization_id,
                opportunity_id=opportunity.id,
                from_stage_id=before_stage_id,
                to_stage_id=stage.id,
                actor_id=actor.id,
                source=command.source,
                note=command.note,
            )
        )
        record_change(
            session,
            actor=actor,
            correlation_id=request.state.correlation_id,
            action="opportunity.stage_changed",
            resource_type="opportunity",
            resource_id=opportunity.id,
            before_state={"stage_id": str(before_stage_id)},
            after_state={"stage_id": str(stage.id)},
            event_type="crm.opportunity.stage_changed.v1",
            event_payload={
                "opportunity_id": str(opportunity.id),
                "from_stage_id": str(before_stage_id),
                "to_stage_id": str(stage.id),
            },
        )
    session.flush()
    response = opportunity_response(session, opportunity)
    assert record is not None
    complete_command(record, response.model_dump(mode="json"), response_status=200)
    session.commit()
    return response


@router.patch("/opportunities/{opportunity_id}/status", response_model=OpportunityResponse)
def update_opportunity_status(
    opportunity_id: uuid.UUID,
    command: OpportunityStatusUpdate,
    request: Request,
    session: SessionDep,
    actor: Annotated[ActorContext, Depends(require_permission("crm:write"))],
    idempotency_key: IdempotencyHeader,
) -> OpportunityResponse:
    record, replay = begin_command(
        session,
        actor=actor,
        command_name="crm.opportunity.update_status",
        idempotency_key=idempotency_key,
        payload={"opportunity_id": str(opportunity_id), **command.model_dump(mode="json")},
        correlation_id=request.state.correlation_id,
    )
    if replay is not None:
        return OpportunityResponse.model_validate(replay)
    opportunity = get_owned(session, Opportunity, opportunity_id, actor.organization_id)
    if command.status == "lost":
        reason = session.scalar(
            select(LossReason).where(
                LossReason.id == command.loss_reason_id,
                LossReason.organization_id == actor.organization_id,
                LossReason.business_unit_id == opportunity.business_unit_id,
                LossReason.status == "active",
            )
        )
        if reason is None:
            raise HTTPException(status_code=422, detail="Motivo de perda inválido")
    if command.status == "open":
        has_open_task = session.scalar(
            select(Task.id).where(
                Task.opportunity_id == opportunity.id,
                Task.status == "open",
            )
        )
        if has_open_task is None:
            raise HTTPException(status_code=409, detail="Reabertura exige uma tarefa aberta")
    before = {"status": opportunity.status, "loss_reason_id": opportunity.loss_reason_id}
    opportunity.status = command.status
    opportunity.loss_reason_id = command.loss_reason_id
    opportunity.closed_at = None if command.status == "open" else datetime.now(UTC)
    opportunity.updated_at = datetime.now(UTC)
    session.flush()
    response = opportunity_response(session, opportunity)
    record_change(
        session,
        actor=actor,
        correlation_id=request.state.correlation_id,
        action="opportunity.status_changed",
        resource_type="opportunity",
        resource_id=opportunity.id,
        before_state={key: str(value) if value else value for key, value in before.items()},
        after_state={
            "status": opportunity.status,
            "loss_reason_id": str(opportunity.loss_reason_id)
            if opportunity.loss_reason_id
            else None,
        },
        event_type="crm.opportunity.status_changed.v1",
        event_payload={"opportunity_id": str(opportunity.id), "status": opportunity.status},
    )
    assert record is not None
    complete_command(record, response.model_dump(mode="json"), response_status=200)
    session.commit()
    return response


def validate_operational_reference(
    session: Session,
    actor: ActorContext,
    *,
    business_unit_id: uuid.UUID,
    opportunity_id: uuid.UUID | None,
    person_id: uuid.UUID | None,
    company_id: uuid.UUID | None,
) -> None:
    ensure_units(session, actor.organization_id, [business_unit_id])
    if opportunity_id:
        opportunity = get_owned(session, Opportunity, opportunity_id, actor.organization_id)
        if opportunity.business_unit_id != business_unit_id:
            raise HTTPException(status_code=422, detail="Oportunidade pertence a outra unidade")
    if person_id:
        get_owned(session, Person, person_id, actor.organization_id)
    if company_id:
        get_owned(session, Company, company_id, actor.organization_id)


@router.post("/activities", response_model=ActivityResponse, status_code=201)
def create_activity(
    command: ActivityCreate,
    request: Request,
    session: SessionDep,
    actor: Annotated[ActorContext, Depends(require_permission("crm:write"))],
    idempotency_key: IdempotencyHeader,
) -> ActivityResponse:
    record, replay = begin_command(
        session,
        actor=actor,
        command_name="crm.activity.create",
        idempotency_key=idempotency_key,
        payload=command.model_dump(mode="json"),
        correlation_id=request.state.correlation_id,
    )
    if replay is not None:
        return ActivityResponse.model_validate(replay)
    validate_operational_reference(
        session,
        actor,
        business_unit_id=command.business_unit_id,
        opportunity_id=command.opportunity_id,
        person_id=command.person_id,
        company_id=command.company_id,
    )
    item = Activity(
        organization_id=actor.organization_id,
        business_unit_id=command.business_unit_id,
        opportunity_id=command.opportunity_id,
        person_id=command.person_id,
        company_id=command.company_id,
        activity_type=command.activity_type,
        occurred_at=aware(command.occurred_at),
        responsible_actor_id=actor.id,
        summary=command.summary,
        origin=command.origin,
        next_step=command.next_step,
        performed_by=command.performed_by,
        workflow_reference=command.workflow_reference,
    )
    session.add(item)
    session.flush()
    response = activity_response(item)
    record_change(
        session,
        actor=actor,
        correlation_id=request.state.correlation_id,
        action="activity.created",
        resource_type="activity",
        resource_id=item.id,
        before_state=None,
        after_state={"activity_type": item.activity_type, "status": item.status},
        event_type="crm.activity.created.v1",
        event_payload={"activity_id": str(item.id)},
    )
    assert record is not None
    complete_command(record, response.model_dump(mode="json"), response_status=201)
    session.commit()
    return response


@router.get("/tasks", response_model=list[TaskResponse])
def list_tasks(
    session: SessionDep,
    actor: Annotated[ActorContext, Depends(require_permission("crm:read"))],
    business_unit_id: uuid.UUID | None = None,
    status: Annotated[str | None, Query(pattern=r"^(open|completed|cancelled)$")] = None,
) -> list[TaskResponse]:
    statement = select(Task).where(Task.organization_id == actor.organization_id)
    if business_unit_id:
        statement = statement.where(Task.business_unit_id == business_unit_id)
    if status:
        statement = statement.where(Task.status == status)
    items = session.scalars(statement.order_by(Task.due_at, Task.created_at)).all()
    return [task_response(item) for item in items]


@router.post("/tasks", response_model=TaskResponse, status_code=201)
def create_task(
    command: TaskCreate,
    request: Request,
    session: SessionDep,
    actor: Annotated[ActorContext, Depends(require_permission("crm:write"))],
    idempotency_key: IdempotencyHeader,
) -> TaskResponse:
    record, replay = begin_command(
        session,
        actor=actor,
        command_name="crm.task.create",
        idempotency_key=idempotency_key,
        payload=command.model_dump(mode="json"),
        correlation_id=request.state.correlation_id,
    )
    if replay is not None:
        return TaskResponse.model_validate(replay)
    validate_operational_reference(
        session,
        actor,
        business_unit_id=command.business_unit_id,
        opportunity_id=command.opportunity_id,
        person_id=command.person_id,
        company_id=command.company_id,
    )
    item = Task(
        organization_id=actor.organization_id,
        business_unit_id=command.business_unit_id,
        opportunity_id=command.opportunity_id,
        person_id=command.person_id,
        company_id=command.company_id,
        title=command.title.strip(),
        due_at=aware(command.due_at),
        owner_actor_id=actor.id,
        priority=command.priority,
        notes=command.notes,
    )
    session.add(item)
    session.flush()
    response = task_response(item)
    record_change(
        session,
        actor=actor,
        correlation_id=request.state.correlation_id,
        action="task.created",
        resource_type="task",
        resource_id=item.id,
        before_state=None,
        after_state={"title": item.title, "status": item.status},
        event_type="crm.task.created.v1",
        event_payload={"task_id": str(item.id)},
    )
    assert record is not None
    complete_command(record, response.model_dump(mode="json"), response_status=201)
    session.commit()
    return response


@router.patch("/tasks/{task_id}/complete", response_model=TaskResponse)
def complete_task(
    task_id: uuid.UUID,
    request: Request,
    session: SessionDep,
    actor: Annotated[ActorContext, Depends(require_permission("crm:write"))],
    idempotency_key: IdempotencyHeader,
) -> TaskResponse:
    record, replay = begin_command(
        session,
        actor=actor,
        command_name="crm.task.complete",
        idempotency_key=idempotency_key,
        payload={"task_id": str(task_id)},
        correlation_id=request.state.correlation_id,
    )
    if replay is not None:
        return TaskResponse.model_validate(replay)
    item = get_owned(session, Task, task_id, actor.organization_id)
    before = {"status": item.status}
    item.status = "completed"
    item.completed_at = datetime.now(UTC)
    item.updated_at = datetime.now(UTC)
    response = task_response(item)
    record_change(
        session,
        actor=actor,
        correlation_id=request.state.correlation_id,
        action="task.completed",
        resource_type="task",
        resource_id=item.id,
        before_state=before,
        after_state={"status": item.status},
        event_type="crm.task.completed.v1",
        event_payload={"task_id": str(item.id)},
    )
    assert record is not None
    complete_command(record, response.model_dump(mode="json"), response_status=200)
    session.commit()
    return response


@router.get("/search", response_model=list[SearchResult])
def search_crm(
    session: SessionDep,
    actor: Annotated[ActorContext, Depends(require_permission("crm:read"))],
    query: Annotated[str, Query(alias="q", min_length=2, max_length=100)],
) -> list[SearchResult]:
    term = query.strip().lower()
    pattern = f"%{term}%"
    contact_term = digits(term) if re.fullmatch(r"[\d\s()+.\-]+", term) else term
    person_ids_by_contact = select(ContactMethod.person_id).where(
        ContactMethod.organization_id == actor.organization_id,
        ContactMethod.person_id.is_not(None),
        ContactMethod.normalized_value.like(f"%{contact_term}%"),
    )
    company_ids_by_contact = select(ContactMethod.company_id).where(
        ContactMethod.organization_id == actor.organization_id,
        ContactMethod.company_id.is_not(None),
        ContactMethod.normalized_value.like(f"%{contact_term}%"),
    )
    people = session.scalars(
        select(Person)
        .where(
            Person.organization_id == actor.organization_id,
            or_(
                func.lower(Person.full_name).like(pattern),
                Person.tax_id.like(f"%{contact_term}%"),
                Person.id.in_(person_ids_by_contact),
            ),
        )
        .limit(20)
    ).all()
    companies = session.scalars(
        select(Company)
        .where(
            Company.organization_id == actor.organization_id,
            or_(
                func.lower(Company.legal_name).like(pattern),
                func.lower(func.coalesce(Company.trade_name, "")).like(pattern),
                Company.tax_id.like(f"%{contact_term}%"),
                Company.id.in_(company_ids_by_contact),
            ),
        )
        .limit(20)
    ).all()
    opportunities = session.scalars(
        select(Opportunity)
        .where(
            Opportunity.organization_id == actor.organization_id,
            func.lower(Opportunity.title).like(pattern),
        )
        .limit(20)
    ).all()
    results = [
        SearchResult(
            resource_type="person",
            id=person.id,
            title=person.full_name,
            subtitle="Pessoa",
            business_unit_ids=person_summary(session, person).business_unit_ids,
        )
        for person in people
    ]
    results.extend(
        SearchResult(
            resource_type="company",
            id=company.id,
            title=company.trade_name or company.legal_name,
            subtitle=company.legal_name,
            business_unit_ids=company_summary(session, company).business_unit_ids,
        )
        for company in companies
    )
    results.extend(
        SearchResult(
            resource_type="opportunity",
            id=item.id,
            title=item.title,
            subtitle=item.status,
            business_unit_ids=[item.business_unit_id],
        )
        for item in opportunities
    )
    return results


@router.get("/people/{person_id}/360", response_model=Person360Response)
def person_360(
    person_id: uuid.UUID,
    session: SessionDep,
    actor: Annotated[ActorContext, Depends(require_permission("crm:read"))],
) -> Person360Response:
    person = get_owned(session, Person, person_id, actor.organization_id)
    relationships = session.scalars(
        select(PersonCompanyRelationship).where(
            PersonCompanyRelationship.person_id == person.id,
            PersonCompanyRelationship.status == "active",
        )
    ).all()
    opportunity_ids = select(OpportunityContact.opportunity_id).where(
        OpportunityContact.person_id == person.id
    )
    opportunities = session.scalars(
        select(Opportunity)
        .where(
            Opportunity.organization_id == actor.organization_id,
            Opportunity.id.in_(opportunity_ids),
        )
        .order_by(Opportunity.updated_at.desc())
    ).all()
    activities = session.scalars(
        select(Activity)
        .where(
            Activity.organization_id == actor.organization_id,
            Activity.person_id == person.id,
        )
        .order_by(Activity.occurred_at.desc())
    ).all()
    tasks = session.scalars(
        select(Task)
        .where(Task.organization_id == actor.organization_id, Task.person_id == person.id)
        .order_by(Task.due_at)
    ).all()
    return Person360Response(
        person=person_summary(session, person),
        companies=[
            PersonCompanyLinkResponse(
                id=item.id,
                person_id=item.person_id,
                company_id=item.company_id,
                role=item.role,
                is_primary=item.is_primary,
                status=item.status,
            )
            for item in relationships
        ],
        opportunities=[opportunity_response(session, item) for item in opportunities],
        activities=[activity_response(item) for item in activities],
        tasks=[task_response(item) for item in tasks],
    )


@router.get("/companies/{company_id}/360", response_model=Company360Response)
def company_360(
    company_id: uuid.UUID,
    session: SessionDep,
    actor: Annotated[ActorContext, Depends(require_permission("crm:read"))],
) -> Company360Response:
    company = get_owned(session, Company, company_id, actor.organization_id)
    relationships = session.scalars(
        select(PersonCompanyRelationship).where(
            PersonCompanyRelationship.company_id == company.id,
            PersonCompanyRelationship.status == "active",
        )
    ).all()
    opportunities = session.scalars(
        select(Opportunity)
        .where(
            Opportunity.organization_id == actor.organization_id,
            Opportunity.company_id == company.id,
        )
        .order_by(Opportunity.updated_at.desc())
    ).all()
    activities = session.scalars(
        select(Activity)
        .where(
            Activity.organization_id == actor.organization_id,
            Activity.company_id == company.id,
        )
        .order_by(Activity.occurred_at.desc())
    ).all()
    tasks = session.scalars(
        select(Task)
        .where(Task.organization_id == actor.organization_id, Task.company_id == company.id)
        .order_by(Task.due_at)
    ).all()
    return Company360Response(
        company=company_summary(session, company),
        people=[
            PersonCompanyLinkResponse(
                id=item.id,
                person_id=item.person_id,
                company_id=item.company_id,
                role=item.role,
                is_primary=item.is_primary,
                status=item.status,
            )
            for item in relationships
        ],
        opportunities=[opportunity_response(session, item) for item in opportunities],
        activities=[activity_response(item) for item in activities],
        tasks=[task_response(item) for item in tasks],
    )


def exact_contact_match(
    session: Session, organization_id: uuid.UUID, values: list[str | None]
) -> bool:
    normalized = [item for item in values if item]
    if not normalized:
        return False
    return bool(
        session.scalar(
            select(ContactMethod.id).where(
                ContactMethod.organization_id == organization_id,
                ContactMethod.normalized_value.in_(normalized),
                ContactMethod.status == "active",
            )
        )
    )


@router.post("/imports", response_model=CrmImportResponse, status_code=201)
def import_crm(
    command: CrmImportCreate,
    request: Request,
    session: SessionDep,
    actor: Annotated[ActorContext, Depends(require_permission("crm:import"))],
    idempotency_key: IdempotencyHeader,
) -> CrmImportResponse:
    record, replay = begin_command(
        session,
        actor=actor,
        command_name="crm.import.create",
        idempotency_key=idempotency_key,
        payload=command.model_dump(mode="json"),
        correlation_id=request.state.correlation_id,
    )
    if replay is not None:
        return CrmImportResponse.model_validate(replay)
    job = CrmImportJob(
        organization_id=actor.organization_id,
        actor_id=actor.id,
        correlation_id=request.state.correlation_id,
        source_label=command.source_label,
        status="processing",
        total_rows=len(command.rows),
    )
    session.add(job)
    session.flush()
    row_results: list[ImportRowResult] = []
    for row_number, row in enumerate(command.rows, start=1):
        payload = row.model_dump(mode="json", exclude_none=True)
        input_hash = canonical_hash(payload)
        result = "failed"
        resource_id = None
        error_code = None
        try:
            if row.entity_type == "person":
                assert row.person is not None
                person_data = row.person
                unit_ids = person_data.business_unit_ids
                ensure_units(session, actor.organization_id, unit_ids)
                tax_id = normalize_tax_id(person_data.tax_id, length=11)
                email = person_data.email.strip().lower() if person_data.email else None
                phone = digits(person_data.phone)
                matched = (
                    session.scalar(
                        select(Person).where(
                            Person.organization_id == actor.organization_id,
                            Person.tax_id == tax_id,
                        )
                    )
                    if tax_id
                    else None
                )
                if matched:
                    resource_id = matched.id
                    link_person_units(
                        session,
                        actor=actor,
                        person_id=matched.id,
                        unit_ids=unit_ids,
                        source_id=None,
                    )
                    result = "matched"
                elif exact_contact_match(session, actor.organization_id, [email, phone]):
                    error_code = "manual_review_contact_match"
                else:
                    item = Person(
                        organization_id=actor.organization_id,
                        full_name=person_data.full_name.strip(),
                        tax_id=tax_id,
                        created_by_actor_id=actor.id,
                    )
                    session.add(item)
                    session.flush()
                    contacts = []
                    if email:
                        contacts.append(ContactMethodInput(kind="email", value=email))
                    if phone:
                        contacts.append(ContactMethodInput(kind="phone", value=phone))
                    add_contacts(
                        session,
                        organization_id=actor.organization_id,
                        contacts=contacts,
                        person_id=item.id,
                    )
                    link_person_units(
                        session,
                        actor=actor,
                        person_id=item.id,
                        unit_ids=unit_ids,
                        source_id=None,
                    )
                    resource_id = item.id
                    result = "created"
            else:
                assert row.company is not None
                company_data = row.company
                unit_ids = company_data.business_unit_ids
                ensure_units(session, actor.organization_id, unit_ids)
                tax_id = normalize_tax_id(company_data.tax_id, length=14)
                email = company_data.email.strip().lower() if company_data.email else None
                phone = digits(company_data.phone)
                matched = (
                    session.scalar(
                        select(Company).where(
                            Company.organization_id == actor.organization_id,
                            Company.tax_id == tax_id,
                        )
                    )
                    if tax_id
                    else None
                )
                if matched:
                    resource_id = matched.id
                    link_company_units(
                        session,
                        actor=actor,
                        company_id=matched.id,
                        unit_ids=unit_ids,
                        source_id=None,
                    )
                    result = "matched"
                elif exact_contact_match(session, actor.organization_id, [email, phone]):
                    error_code = "manual_review_contact_match"
                else:
                    item = Company(
                        organization_id=actor.organization_id,
                        legal_name=company_data.legal_name.strip(),
                        trade_name=company_data.trade_name,
                        tax_id=tax_id,
                        created_by_actor_id=actor.id,
                    )
                    session.add(item)
                    session.flush()
                    contacts = []
                    if email:
                        contacts.append(ContactMethodInput(kind="email", value=email))
                    if phone:
                        contacts.append(ContactMethodInput(kind="phone", value=phone))
                    add_contacts(
                        session,
                        organization_id=actor.organization_id,
                        contacts=contacts,
                        company_id=item.id,
                    )
                    link_company_units(
                        session,
                        actor=actor,
                        company_id=item.id,
                        unit_ids=unit_ids,
                        source_id=None,
                    )
                    resource_id = item.id
                    result = "created"
        except HTTPException as error:
            error_code = f"validation_{error.status_code}"
        job.created_rows += int(result == "created")
        job.matched_rows += int(result == "matched")
        job.failed_rows += int(result == "failed")
        row_record = CrmImportRow(
            import_job_id=job.id,
            row_number=row_number,
            entity_type=row.entity_type,
            input_sha256=input_hash,
            result=result,
            resource_id=resource_id,
            error_code=error_code,
        )
        session.add(row_record)
        row_results.append(
            ImportRowResult(
                row_number=row_number,
                entity_type=row.entity_type,
                result=result,
                resource_id=resource_id,
                error_code=error_code,
            )
        )
    job.status = "completed_with_errors" if job.failed_rows else "completed"
    job.completed_at = datetime.now(UTC)
    response = CrmImportResponse(
        id=job.id,
        source_label=job.source_label,
        status=job.status,
        total_rows=job.total_rows,
        created_rows=job.created_rows,
        matched_rows=job.matched_rows,
        failed_rows=job.failed_rows,
        rows=row_results,
    )
    record_change(
        session,
        actor=actor,
        correlation_id=request.state.correlation_id,
        action="crm_import.completed",
        resource_type="crm_import_job",
        resource_id=job.id,
        before_state=None,
        after_state={
            "status": job.status,
            "total_rows": job.total_rows,
            "created_rows": job.created_rows,
            "matched_rows": job.matched_rows,
            "failed_rows": job.failed_rows,
        },
        event_type="crm.import.completed.v1",
        event_payload={"import_job_id": str(job.id), "status": job.status},
    )
    assert record is not None
    complete_command(record, response.model_dump(mode="json"), response_status=201)
    session.commit()
    return response
