from __future__ import annotations

import uuid
from calendar import monthrange
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from sqlalchemy import func, select

from stk_os.client_service_schemas import (
    ClientServiceCreate,
    ClientServiceOccurrenceResponse,
    ClientServiceResponse,
    ClientServiceUpdate,
    OccurrenceGenerate,
    OccurrenceUpdate,
)
from stk_os.commands import begin_command, complete_command, record_change
from stk_os.database import SessionDep
from stk_os.dependencies import require_permission
from stk_os.models import (
    Actor,
    BillingItem,
    BusinessUnit,
    ClientService,
    ClientServiceOccurrence,
    Company,
    Contract,
    ContractVersion,
    ProductService,
)
from stk_os.schemas import ActorContext
from stk_os.security import canonical_hash

router = APIRouter(prefix="/client-services", tags=["client-services"])
IdempotencyHeader = Annotated[str, Header(alias="Idempotency-Key", min_length=8, max_length=255)]


def add_months(value: date, months: int) -> date:
    index = value.year * 12 + value.month - 1 + months
    year, zero_month = divmod(index, 12)
    month = zero_month + 1
    return date(year, month, min(value.day, monthrange(year, month)[1]))


def recurrence_months(service: ClientService) -> int:
    return {"monthly": 1, "quarterly": 3, "semiannual": 6, "annual": 12}.get(
        service.recurrence or "", service.interval_months or 1
    )


def response_for(session: SessionDep, service: ClientService) -> ClientServiceResponse:
    company = session.get(Company, service.customer_company_id)
    contract = session.get(Contract, service.contract_id) if service.contract_id else None
    owner = session.get(Actor, service.owner_actor_id)
    occurrences = session.scalars(
        select(ClientServiceOccurrence)
        .where(ClientServiceOccurrence.client_service_id == service.id)
        .order_by(ClientServiceOccurrence.scheduled_for.desc())
    ).all()
    return ClientServiceResponse(
        id=service.id,
        organization_id=service.organization_id,
        business_unit_id=service.business_unit_id,
        customer_company_id=service.customer_company_id,
        customer_name=(company.trade_name or company.legal_name)
        if company
        else "Cliente indisponível",
        product_service_id=service.product_service_id,
        contract_id=service.contract_id,
        contract_number=contract.internal_number if contract else None,
        name=service.name,
        description=service.description,
        service_type=service.service_type,
        recurrence=service.recurrence,
        interval_months=service.interval_months,
        installment_total=service.installment_total,
        start_date=service.start_date,
        next_occurrence_on=service.next_occurrence_on,
        owner_actor_id=service.owner_actor_id,
        owner_name=owner.display_name if owner else "Responsável indisponível",
        amount=service.amount,
        currency=service.currency,
        operational_lead_days=service.operational_lead_days,
        reminder_lead_days=service.reminder_lead_days,
        status=service.status,
        occurrences=[
            ClientServiceOccurrenceResponse(
                id=item.id,
                scheduled_for=item.scheduled_for,
                due_on=item.due_on,
                status=item.status,
                billing_status=item.billing_status,
                billing_item_id=item.billing_item_id,
                installment_number=item.installment_number,
                created_at=item.created_at,
            )
            for item in occurrences
        ],
        created_at=service.created_at,
        updated_at=service.updated_at,
    )


def get_service(session: SessionDep, actor: ActorContext, service_id: uuid.UUID) -> ClientService:
    service = session.scalar(
        select(ClientService).where(
            ClientService.id == service_id, ClientService.organization_id == actor.organization_id
        )
    )
    if service is None:
        raise HTTPException(status_code=404, detail="Serviço do cliente não encontrado")
    return service


def validate_scope(session: SessionDep, actor: ActorContext, command: ClientServiceCreate) -> None:
    unit = session.scalar(
        select(BusinessUnit).where(
            BusinessUnit.id == command.business_unit_id,
            BusinessUnit.organization_id == actor.organization_id,
        )
    )
    company = session.scalar(
        select(Company).where(
            Company.id == command.customer_company_id,
            Company.organization_id == actor.organization_id,
        )
    )
    owner = session.scalar(
        select(Actor).where(
            Actor.id == command.owner_actor_id,
            Actor.organization_id == actor.organization_id,
            Actor.status == "active",
        )
    )
    if unit is None or company is None or owner is None:
        raise HTTPException(status_code=422, detail="Cliente, unidade ou responsável inválido")
    if (
        command.product_service_id
        and session.scalar(
            select(ProductService).where(
                ProductService.id == command.product_service_id,
                ProductService.organization_id == actor.organization_id,
                ProductService.business_unit_id == command.business_unit_id,
            )
        )
        is None
    ):
        raise HTTPException(status_code=422, detail="Catálogo de serviço inválido")
    if (
        command.contract_id
        and session.scalar(
            select(Contract).where(
                Contract.id == command.contract_id,
                Contract.organization_id == actor.organization_id,
                Contract.business_unit_id == command.business_unit_id,
                Contract.customer_company_id == command.customer_company_id,
            )
        )
        is None
    ):
        raise HTTPException(status_code=422, detail="Contrato não pertence ao cliente e unidade")


@router.get("", response_model=list[ClientServiceResponse])
def list_services(
    session: SessionDep,
    actor: Annotated[ActorContext, Depends(require_permission("services:read"))],
    customer_company_id: uuid.UUID | None = None,
    business_unit_id: uuid.UUID | None = None,
    status: Annotated[str | None, Query(pattern=r"^(active|inactive)$")] = None,
) -> list[ClientServiceResponse]:
    statement = select(ClientService).where(ClientService.organization_id == actor.organization_id)
    if customer_company_id:
        statement = statement.where(ClientService.customer_company_id == customer_company_id)
    if business_unit_id:
        statement = statement.where(ClientService.business_unit_id == business_unit_id)
    if status:
        statement = statement.where(ClientService.status == status)
    services = session.scalars(statement.order_by(ClientService.name, ClientService.id)).all()
    return [response_for(session, service) for service in services]


@router.post("", response_model=ClientServiceResponse, status_code=201)
def create_service(
    command: ClientServiceCreate,
    request: Request,
    session: SessionDep,
    actor: Annotated[ActorContext, Depends(require_permission("services:write"))],
) -> ClientServiceResponse:
    validate_scope(session, actor, command)
    service = ClientService(
        organization_id=actor.organization_id,
        **command.model_dump(),
        next_occurrence_on=None if command.installment_total else command.start_date,
        status="active",
        created_by_actor_id=actor.id,
    )
    session.add(service)
    session.flush()
    record_change(
        session,
        actor=actor,
        correlation_id=request.state.correlation_id,
        action="client_service.created",
        resource_type="client_service",
        resource_id=service.id,
        before_state=None,
        after_state={
            "service_type": service.service_type,
            "contract_id": str(service.contract_id) if service.contract_id else None,
        },
        event_type="client_service.created.v1",
        event_payload={
            "client_service_id": str(service.id),
            "customer_company_id": str(service.customer_company_id),
        },
    )
    session.commit()
    return response_for(session, service)


@router.patch("/{service_id}", response_model=ClientServiceResponse)
def update_service(
    service_id: uuid.UUID,
    command: ClientServiceUpdate,
    request: Request,
    session: SessionDep,
    actor: Annotated[ActorContext, Depends(require_permission("services:write"))],
) -> ClientServiceResponse:
    service = get_service(session, actor, service_id)
    before = {
        "status": service.status,
        "contract_id": str(service.contract_id) if service.contract_id else None,
    }
    changes = command.model_dump(exclude_unset=True)
    if (
        "owner_actor_id" in changes
        and session.scalar(
            select(Actor).where(
                Actor.id == changes["owner_actor_id"],
                Actor.organization_id == actor.organization_id,
            )
        )
        is None
    ):
        raise HTTPException(status_code=422, detail="Responsável inválido")
    if (
        "contract_id" in changes
        and changes["contract_id"] is not None
        and session.scalar(
            select(Contract).where(
                Contract.id == changes["contract_id"],
                Contract.organization_id == actor.organization_id,
                Contract.business_unit_id == service.business_unit_id,
                Contract.customer_company_id == service.customer_company_id,
            )
        )
        is None
    ):
        raise HTTPException(status_code=422, detail="Contrato inválido")
    for key, value in changes.items():
        setattr(service, key, value)
    if service.service_type == "recurring" and service.recurrence is None:
        raise HTTPException(status_code=422, detail="Serviço recorrente exige periodicidade")
    if service.installment_total is not None and service.service_type != "one_time":
        raise HTTPException(
            status_code=422, detail="Parcelamento é permitido somente para serviço avulso"
        )
    highest_installment = session.scalar(
        select(func.max(ClientServiceOccurrence.installment_number)).where(
            ClientServiceOccurrence.client_service_id == service.id
        )
    )
    if highest_installment:
        if service.installment_total is None:
            raise HTTPException(
                status_code=422,
                detail="Serviço com parcelas programadas deve manter o total",
            )
        if highest_installment > service.installment_total:
            raise HTTPException(
                status_code=422,
                detail="Total não pode ser menor que parcela já programada",
            )
    record_change(
        session,
        actor=actor,
        correlation_id=request.state.correlation_id,
        action="client_service.updated",
        resource_type="client_service",
        resource_id=service.id,
        before_state=before,
        after_state={
            "status": service.status,
            "contract_id": str(service.contract_id) if service.contract_id else None,
        },
        event_type="client_service.updated.v1",
        event_payload={"client_service_id": str(service.id)},
    )
    session.commit()
    return response_for(session, service)


@router.post("/{service_id}/occurrences/generate", response_model=ClientServiceResponse)
def generate_occurrences(
    service_id: uuid.UUID,
    command: OccurrenceGenerate,
    request: Request,
    session: SessionDep,
    idempotency_key: IdempotencyHeader,
    actor: Annotated[ActorContext, Depends(require_permission("services:write"))],
) -> ClientServiceResponse:
    service = get_service(session, actor, service_id)
    record, cached = begin_command(
        session,
        actor=actor,
        command_name="client_service.generate_occurrences.v1",
        idempotency_key=idempotency_key,
        payload={"service_id": str(service_id), **command.model_dump(mode="json")},
        correlation_id=request.state.correlation_id,
    )
    if cached:
        return ClientServiceResponse.model_validate(cached)
    if service.status != "active":
        raise HTTPException(status_code=409, detail="Serviço inativo não gera ocorrências")
    if service.service_type == "one_time" and service.installment_total is not None:
        if command.scheduled_for is None or command.installment_number is None:
            raise HTTPException(
                status_code=422,
                detail="Serviço avulso parcelado exige data e número da parcela",
            )
        if command.through is not None:
            raise HTTPException(
                status_code=422,
                detail="Serviço avulso parcelado usa scheduled_for, não through",
            )
        if command.installment_number > service.installment_total:
            raise HTTPException(
                status_code=422,
                detail="Número da parcela não pode superar o total",
            )
        existing_number = session.scalar(
            select(ClientServiceOccurrence).where(
                ClientServiceOccurrence.client_service_id == service.id,
                ClientServiceOccurrence.installment_number == command.installment_number,
            )
        )
        existing_date = session.scalar(
            select(ClientServiceOccurrence).where(
                ClientServiceOccurrence.client_service_id == service.id,
                ClientServiceOccurrence.scheduled_for == command.scheduled_for,
            )
        )
        if existing_number and existing_number.scheduled_for != command.scheduled_for:
            raise HTTPException(status_code=409, detail="Parcela já programada em outra data")
        if existing_date and existing_date.installment_number != command.installment_number:
            raise HTTPException(status_code=409, detail="Data já utilizada por outra parcela")
        existing = existing_number or existing_date
        generated = 0
        if existing is None:
            session.add(
                ClientServiceOccurrence(
                    organization_id=service.organization_id,
                    client_service_id=service.id,
                    scheduled_for=command.scheduled_for,
                    due_on=command.scheduled_for,
                    installment_number=command.installment_number,
                    status="planned",
                    billing_status="to_bill",
                    owner_actor_id=service.owner_actor_id,
                    created_by_actor_id=actor.id,
                )
            )
            generated = 1
        service.next_occurrence_on = None
        cursor = None
    else:
        if command.scheduled_for is not None or command.installment_number is not None:
            raise HTTPException(
                status_code=422,
                detail="Data/número explícitos são exclusivos de serviço avulso parcelado",
            )
        if command.through is None:
            raise HTTPException(status_code=422, detail="Informe through")
        cursor = service.next_occurrence_on
        generated = 0
        while cursor is not None and cursor <= command.through and generated < 240:
            existing = session.scalar(
                select(ClientServiceOccurrence).where(
                    ClientServiceOccurrence.client_service_id == service.id,
                    ClientServiceOccurrence.scheduled_for == cursor,
                )
            )
            if existing is None:
                session.add(
                    ClientServiceOccurrence(
                        organization_id=service.organization_id,
                        client_service_id=service.id,
                        scheduled_for=cursor,
                        due_on=cursor,
                        status="planned",
                        billing_status="to_bill",
                        owner_actor_id=service.owner_actor_id,
                        created_by_actor_id=actor.id,
                    )
                )
            generated += 1
            cursor = (
                None
                if service.service_type == "one_time"
                else add_months(cursor, recurrence_months(service))
            )
        service.next_occurrence_on = cursor
    if generated == 0:
        result = response_for(session, service)
    else:
        session.flush()
        record_change(
            session,
            actor=actor,
            correlation_id=request.state.correlation_id,
            action="client_service.occurrences_generated",
            resource_type="client_service",
            resource_id=service.id,
            before_state=None,
            after_state={
                "generated": generated,
                "next_occurrence_on": cursor.isoformat() if cursor else None,
            },
            event_type="client_service.occurrences_generated.v1",
            event_payload={"client_service_id": str(service.id), "generated": generated},
        )
        result = response_for(session, service)
    if record:
        complete_command(record, result.model_dump(mode="json"), response_status=200)
    session.commit()
    return result


@router.patch("/{service_id}/occurrences/{occurrence_id}", response_model=ClientServiceResponse)
def update_occurrence(
    service_id: uuid.UUID,
    occurrence_id: uuid.UUID,
    command: OccurrenceUpdate,
    request: Request,
    session: SessionDep,
    actor: Annotated[ActorContext, Depends(require_permission("services:write"))],
) -> ClientServiceResponse:
    service = get_service(session, actor, service_id)
    occurrence = session.scalar(
        select(ClientServiceOccurrence).where(
            ClientServiceOccurrence.id == occurrence_id,
            ClientServiceOccurrence.client_service_id == service.id,
        )
    )
    if occurrence is None:
        raise HTTPException(status_code=404, detail="Ocorrência não encontrada")
    before = occurrence.status
    occurrence.status = command.status
    if command.status == "billed":
        occurrence.billing_status = "billed"
    record_change(
        session,
        actor=actor,
        correlation_id=request.state.correlation_id,
        action="client_service.occurrence_updated",
        resource_type="client_service_occurrence",
        resource_id=occurrence.id,
        before_state={"status": before},
        after_state={"status": occurrence.status, "billing_status": occurrence.billing_status},
        event_type="client_service.occurrence_updated.v1",
        event_payload={"occurrence_id": str(occurrence.id)},
    )
    session.commit()
    return response_for(session, service)


@router.post(
    "/{service_id}/occurrences/{occurrence_id}/billing-item", response_model=dict, status_code=201
)
def create_billing_item(
    service_id: uuid.UUID,
    occurrence_id: uuid.UUID,
    request: Request,
    session: SessionDep,
    idempotency_key: IdempotencyHeader,
    actor: Annotated[ActorContext, Depends(require_permission("billing:generate"))],
) -> dict[str, object]:
    service = get_service(session, actor, service_id)
    occurrence = session.scalar(
        select(ClientServiceOccurrence).where(
            ClientServiceOccurrence.id == occurrence_id,
            ClientServiceOccurrence.client_service_id == service.id,
        )
    )
    if occurrence is None:
        raise HTTPException(status_code=404, detail="Ocorrência não encontrada")
    record, cached = begin_command(
        session,
        actor=actor,
        command_name="client_service.create_billing_item.v1",
        idempotency_key=idempotency_key,
        payload={"service_id": str(service_id), "occurrence_id": str(occurrence_id)},
        correlation_id=request.state.correlation_id,
    )
    if cached:
        return cached
    existing = session.scalar(
        select(BillingItem).where(BillingItem.service_occurrence_id == occurrence.id)
    )
    if existing:
        body = {
            "id": str(existing.id),
            "source_type": existing.source_type,
            "status": existing.status,
            "reused": True,
        }
        if record:
            complete_command(record, body, response_status=200)
        session.commit()
        return body
    competence = occurrence.scheduled_for.replace(day=1)
    contract = session.get(Contract, service.contract_id) if service.contract_id else None
    version = None
    if contract:
        version = session.scalar(
            select(ContractVersion)
            .where(
                ContractVersion.contract_id == contract.id,
                ContractVersion.effective_from <= occurrence.scheduled_for,
            )
            .order_by(ContractVersion.effective_from.desc())
            .limit(1)
        )
        contract_existing = session.scalar(
            select(BillingItem).where(
                BillingItem.contract_id == contract.id, BillingItem.competence_month == competence
            )
        )
        if contract_existing:
            occurrence.billing_item_id = contract_existing.id
            occurrence.billing_status = "item_created"
            body = {
                "id": str(contract_existing.id),
                "source_type": contract_existing.source_type,
                "status": contract_existing.status,
                "reused": True,
            }
            if record:
                complete_command(record, body, response_status=200)
            session.commit()
            return body
    unit = session.get(BusinessUnit, service.business_unit_id)
    issuer_id = (
        version.issuer_establishment_id
        if version
        else (None if contract else unit.primary_establishment_id if unit else None)
    )
    source_type = (
        "contract_recurring"
        if contract
        else ("service_recurring" if service.service_type == "recurring" else "service_one_time")
    )
    blockers = []
    if contract and version is None:
        blockers.append(
            {
                "code": "NO_VALID_CONTRACT_VERSION",
                "reason": "Contrato sem versão válida para a ocorrência.",
            }
        )
    if issuer_id is None:
        blockers.append(
            {"code": "ISSUER_UNAVAILABLE", "reason": "Unidade sem estabelecimento emissor ativo."}
        )
    billing_reference = None
    if service.service_type == "one_time":
        if service.installment_total is None:
            if occurrence.installment_number is not None:
                raise HTTPException(
                    status_code=422,
                    detail="Serviço não parcelado não aceita número de parcela",
                )
            billing_reference = {"type": "single", "position": None, "total": None}
        else:
            if occurrence.installment_number is None:
                raise HTTPException(
                    status_code=422,
                    detail="Serviço parcelado exige número da parcela",
                )
            if occurrence.installment_number > service.installment_total:
                raise HTTPException(
                    status_code=422,
                    detail="Número da parcela não pode superar o total",
                )
            billing_reference = {
                "type": "installment",
                "position": occurrence.installment_number,
                "total": service.installment_total,
            }
    snapshot = {
        "schema_version": "billing-item-snapshot.v2",
        "source": {
            "type": source_type,
            "client_service_id": str(service.id),
            "service_occurrence_id": str(occurrence.id),
            "contract_id": str(contract.id) if contract else None,
        },
        "service": {"name": service.name, "scheduled_for": occurrence.scheduled_for.isoformat()},
        "customer": {"id": str(service.customer_company_id)},
        "currency": service.currency,
        "gross_amount": str(service.amount),
        "billing_reference": billing_reference,
        "blockers": blockers,
    }
    first = blockers[0] if blockers else None
    item = BillingItem(
        organization_id=service.organization_id,
        business_unit_id=service.business_unit_id,
        created_by_run_id=None,
        source_type=source_type,
        client_service_id=service.id,
        service_occurrence_id=occurrence.id,
        contract_id=contract.id if contract else None,
        contract_version_id=version.id if version else None,
        competence_month=competence,
        customer_company_id=service.customer_company_id,
        issuer_establishment_id=issuer_id,
        currency=service.currency,
        gross_amount=service.amount,
        snapshot=snapshot,
        snapshot_sha256=canonical_hash(snapshot),
        status="blocked" if blockers else "ready",
        blocking_code=first["code"] if first else None,
        blocking_reason=first["reason"] if first else None,
        correlation_id=request.state.correlation_id,
        causation_id=occurrence.id,
        created_by_actor_id=actor.id,
    )
    session.add(item)
    session.flush()
    occurrence.billing_item_id = item.id
    occurrence.billing_status = "item_created"
    record_change(
        session,
        actor=actor,
        correlation_id=request.state.correlation_id,
        action="billing.item.created",
        resource_type="billing_item",
        resource_id=item.id,
        before_state=None,
        after_state={
            "status": item.status,
            "source_type": source_type,
            "snapshot_sha256": item.snapshot_sha256,
        },
        event_type="billing.item.ready.v1" if item.status == "ready" else "billing.item.blocked.v1",
        event_payload={
            "billing_item_id": str(item.id),
            "source_type": source_type,
            "service_occurrence_id": str(occurrence.id),
        },
    )
    body = {"id": str(item.id), "source_type": source_type, "status": item.status, "reused": False}
    if record:
        complete_command(record, body, response_status=201)
    session.commit()
    return body
