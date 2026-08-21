from __future__ import annotations

import uuid
from calendar import monthrange
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from stk_os.billing_schemas import (
    BillingExceptionResponse,
    BillingGenerate,
    BillingHistoryEvent,
    BillingItemDetail,
    BillingItemSummary,
    BillingRunContractResponse,
    BillingRunResponse,
    BillingSummaryResponse,
)
from stk_os.commands import begin_command, complete_command, record_change
from stk_os.config import get_settings
from stk_os.database import SessionDep
from stk_os.dependencies import require_permission
from stk_os.models import (
    ActorRole,
    AuditEvent,
    BillingItem,
    BillingRun,
    BillingRunContract,
    BusinessUnit,
    Company,
    ContactMethod,
    Contract,
    ContractOperationalEvent,
    ContractVersion,
    ContractVersionContact,
    ContractVersionService,
    FiscalEstablishment,
    LegalEntity,
    OperationalException,
    OutboxEvent,
    Permission,
    ProductService,
    RolePermission,
)
from stk_os.schemas import ActorContext
from stk_os.security import canonical_hash

router = APIRouter(prefix="/billing", tags=["billing"])
IdempotencyHeader = Annotated[str, Header(alias="Idempotency-Key", min_length=8, max_length=255)]


def competence_date(value: str) -> date:
    year, month = (int(part) for part in value.split("-"))
    return date(year, month, 1)


def competence_label(value: date) -> str:
    return value.strftime("%Y-%m")


def utc_datetime(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


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
        raise HTTPException(status_code=404, detail="Recurso de faturamento não encontrado")


def version_at(session: Session, contract_id: uuid.UUID, on_date: date) -> ContractVersion | None:
    return session.scalar(
        select(ContractVersion)
        .where(
            ContractVersion.contract_id == contract_id,
            ContractVersion.effective_from <= on_date,
        )
        .order_by(ContractVersion.effective_from.desc(), ContractVersion.version_number.desc())
        .limit(1)
    )


def state_at(session: Session, contract_id: uuid.UUID, on_date: date) -> str:
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


def calculate_gross(version: ContractVersion) -> tuple[Decimal | None, tuple[str, str] | None]:
    amount = Decimal(version.amount)
    if version.billing_frequency != "monthly":
        return None, (
            "UNSUPPORTED_BILLING_FREQUENCY",
            "Somente cobrança mensal recorrente possui regra aprovada nesta etapa.",
        )
    if version.pricing_model == "monthly":
        return amount, None
    if version.pricing_model == "annual":
        cents = int(amount * 100)
        if cents % 12:
            return None, (
                "GATE_A_ANNUAL_ROUNDING_PENDING",
                "O valor anual dividido por 12 produz centavos residuais; "
                "o Gate A não definiu a distribuição.",
            )
        return Decimal(cents // 12) / Decimal(100), None
    return None, (
        "UNSUPPORTED_PRICING_MODEL",
        "O modelo de preço não possui regra mensal aprovada para geração automática.",
    )


def snapshot_for(
    session: Session,
    *,
    contract: Contract,
    version: ContractVersion | None,
    competence: date,
    competence_end: date,
    operational_state: str,
    gross_amount: Decimal | None,
    blockers: list[dict[str, str]],
) -> dict[str, Any]:
    settings = get_settings()
    company = session.get(Company, contract.customer_company_id)
    unit = session.get(BusinessUnit, contract.business_unit_id)
    issuer = session.get(FiscalEstablishment, version.issuer_establishment_id) if version else None
    services: list[dict[str, Any]] = []
    contacts: list[dict[str, Any]] = []
    if version:
        for item in session.scalars(
            select(ContractVersionService)
            .where(ContractVersionService.contract_version_id == version.id)
            .order_by(ContractVersionService.created_at, ContractVersionService.id)
        ):
            product = (
                session.get(ProductService, item.product_service_id)
                if item.product_service_id
                else None
            )
            services.append(
                {
                    "product_service_id": str(item.product_service_id)
                    if item.product_service_id
                    else None,
                    "product_name": product.name if product else None,
                    "description": item.contractual_description,
                    "quantity": str(Decimal(item.quantity)),
                    "unit_amount": str(Decimal(item.unit_amount))
                    if item.unit_amount is not None
                    else None,
                    "is_active": item.is_active,
                }
            )
        for item in session.scalars(
            select(ContractVersionContact)
            .where(ContractVersionContact.contract_version_id == version.id)
            .order_by(
                ContractVersionContact.recipient_role.desc(), ContractVersionContact.created_at
            )
        ):
            method = session.get(ContactMethod, item.contact_method_id)
            contacts.append(
                {
                    "contact_method_id": str(item.contact_method_id),
                    "recipient_role": item.recipient_role,
                    "purpose": item.purpose,
                    "preferred_channel": item.preferred_channel,
                    "value": method.value if method else None,
                    "method_status": method.status if method else "missing",
                }
            )
    return {
        "schema_version": "billing-item-snapshot.v1",
        "rule_version": settings.billing_rule_version,
        "competence": {
            "month": competence_label(competence),
            "starts_on": competence.isoformat(),
            "ends_on": competence_end.isoformat(),
            "timezone": settings.operational_timezone,
        },
        "contract": {
            "id": str(contract.id),
            "internal_number": contract.internal_number,
            "start_date": contract.start_date.isoformat(),
            "contract_type": contract.contract_type,
            "administrative_status": contract.administrative_status,
            "operational_state_at_month_start": operational_state,
        },
        "contract_version": (
            {
                "id": str(version.id),
                "version_number": version.version_number,
                "effective_from": version.effective_from.isoformat(),
                "configuration_sha256": version.configuration_sha256,
                "billing_frequency": version.billing_frequency,
                "pricing_model": version.pricing_model,
                "contract_amount": str(Decimal(version.amount)),
                "billing_installments": version.billing_installments,
                "billing_day": version.billing_day,
                "payment_terms_days": version.payment_terms_days,
                "invoice_description": version.invoice_description,
            }
            if version
            else None
        ),
        "customer": {
            "id": str(contract.customer_company_id),
            "legal_name": company.legal_name if company else None,
            "trade_name": company.trade_name if company else None,
        },
        "business_unit": {
            "id": str(contract.business_unit_id),
            "code": unit.code if unit else None,
            "name": unit.name if unit else None,
        },
        "issuer": (
            {
                "id": str(issuer.id),
                "code": issuer.code,
                "name": issuer.name,
                "legal_entity_id": str(issuer.legal_entity_id),
                "status": issuer.status,
            }
            if issuer
            else None
        ),
        "currency": version.currency if version else None,
        "gross_amount": str(gross_amount) if gross_amount is not None else None,
        "services": services,
        "financial_contacts": contacts,
        "blockers": blockers,
    }


def item_summary(session: Session, item: BillingItem) -> BillingItemSummary:
    contract = session.get(Contract, item.contract_id) if item.contract_id else None
    version = (
        session.get(ContractVersion, item.contract_version_id) if item.contract_version_id else None
    )
    company = session.get(Company, item.customer_company_id)
    unit = session.get(BusinessUnit, item.business_unit_id)
    issuer = (
        session.get(FiscalEstablishment, item.issuer_establishment_id)
        if item.issuer_establishment_id
        else None
    )
    return BillingItemSummary(
        id=item.id,
        created_by_run_id=item.created_by_run_id,
        source_type=item.source_type,
        client_service_id=item.client_service_id,
        service_occurrence_id=item.service_occurrence_id,
        contract_id=item.contract_id,
        contract_number=contract.internal_number if contract else "Sem contrato",
        contract_version_id=item.contract_version_id,
        contract_version_number=version.version_number if version else None,
        competence_month=competence_label(item.competence_month),
        business_unit_id=item.business_unit_id,
        business_unit_name=unit.name if unit else "Unidade indisponível",
        customer_company_id=item.customer_company_id,
        customer_name=(company.trade_name or company.legal_name)
        if company
        else "Cliente indisponível",
        issuer_establishment_id=item.issuer_establishment_id,
        issuer_name=issuer.name if issuer else None,
        currency=item.currency,
        gross_amount=Decimal(item.gross_amount) if item.gross_amount is not None else None,
        status=item.status,
        blocking_code=item.blocking_code,
        blocking_reason=item.blocking_reason,
        snapshot_sha256=item.snapshot_sha256,
        correlation_id=item.correlation_id,
        causation_id=item.causation_id,
        created_at=utc_datetime(item.created_at),
        updated_at=utc_datetime(item.updated_at),
    )


def run_response(
    session: Session, run: BillingRun, *, include_contracts: bool = True
) -> BillingRunResponse:
    unit = session.get(BusinessUnit, run.business_unit_id)
    contracts: list[BillingRunContractResponse] = []
    if include_contracts:
        entries = session.scalars(
            select(BillingRunContract)
            .where(BillingRunContract.billing_run_id == run.id)
            .order_by(BillingRunContract.created_at, BillingRunContract.id)
        ).all()
        for entry in entries:
            contract = session.get(Contract, entry.contract_id)
            company = session.get(Company, contract.customer_company_id) if contract else None
            contracts.append(
                BillingRunContractResponse(
                    contract_id=entry.contract_id,
                    contract_number=contract.internal_number
                    if contract
                    else "Contrato indisponível",
                    customer_name=(company.trade_name or company.legal_name)
                    if company
                    else "Cliente indisponível",
                    billing_item_id=entry.billing_item_id,
                    outcome=entry.outcome,
                    reason_code=entry.reason_code,
                    reason_detail=entry.reason_detail,
                )
            )
    return BillingRunResponse(
        id=run.id,
        organization_id=run.organization_id,
        business_unit_id=run.business_unit_id,
        business_unit_name=unit.name if unit else "Unidade indisponível",
        competence_month=competence_label(run.competence_month),
        run_type=run.run_type,
        status=run.status,
        operational_timezone=run.operational_timezone,
        rule_version=run.rule_version,
        actor_id=run.actor_id,
        correlation_id=run.correlation_id,
        causation_id=run.causation_id,
        metrics=run.metrics,
        started_at=utc_datetime(run.started_at),
        completed_at=utc_datetime(run.completed_at) if run.completed_at else None,
        contracts=contracts,
    )


def not_eligible(run: BillingRun, contract: Contract, code: str, detail: str) -> BillingRunContract:
    return BillingRunContract(
        billing_run_id=run.id,
        contract_id=contract.id,
        outcome="not_eligible",
        reason_code=code,
        reason_detail=detail,
    )


def create_item_for_contract(
    session: Session,
    *,
    actor: ActorContext,
    run: BillingRun,
    contract: Contract,
    competence: date,
    competence_end: date,
) -> tuple[BillingItem, bool]:
    existing = session.scalar(
        select(BillingItem).where(
            BillingItem.contract_id == contract.id,
            BillingItem.competence_month == competence,
        )
    )
    if existing:
        return existing, False

    version = version_at(session, contract.id, competence)
    operational_state = state_at(session, contract.id, competence)
    blockers: list[dict[str, str]] = []
    gross_amount: Decimal | None = None
    if version is None:
        blockers.append(
            {
                "code": "NO_VALID_CONTRACT_VERSION",
                "reason": "Não existe versão contratual válida no início da competência.",
            }
        )
    else:
        gross_amount, amount_blocker = calculate_gross(version)
        if amount_blocker:
            blockers.append({"code": amount_blocker[0], "reason": amount_blocker[1]})
        issuer = session.scalar(
            select(FiscalEstablishment)
            .join(LegalEntity, LegalEntity.id == FiscalEstablishment.legal_entity_id)
            .where(
                FiscalEstablishment.id == version.issuer_establishment_id,
                FiscalEstablishment.status == "active",
                LegalEntity.organization_id == contract.organization_id,
            )
        )
        if issuer is None:
            blockers.append(
                {
                    "code": "ISSUER_UNAVAILABLE",
                    "reason": "O estabelecimento emissor da versão está ausente ou inativo.",
                }
            )
        active_services = session.scalar(
            select(func.count())
            .select_from(ContractVersionService)
            .where(
                ContractVersionService.contract_version_id == version.id,
                ContractVersionService.is_active.is_(True),
            )
        )
        if not active_services:
            blockers.append(
                {
                    "code": "NO_ACTIVE_SERVICE",
                    "reason": "A versão não possui serviço contratual ativo.",
                }
            )
        primary_contacts = session.scalars(
            select(ContactMethod)
            .join(
                ContractVersionContact, ContractVersionContact.contact_method_id == ContactMethod.id
            )
            .where(
                ContractVersionContact.contract_version_id == version.id,
                ContractVersionContact.recipient_role == "primary",
                ContractVersionContact.purpose == "billing",
                ContactMethod.status == "active",
            )
        ).all()
        if len(primary_contacts) != 1:
            blockers.append(
                {
                    "code": "FINANCIAL_CONTACT_UNAVAILABLE",
                    "reason": (
                        "A versão não possui exatamente um contato financeiro principal ativo."
                    ),
                }
            )

    changes_inside_month = session.scalar(
        select(func.count())
        .select_from(ContractVersion)
        .where(
            ContractVersion.contract_id == contract.id,
            ContractVersion.effective_from > competence,
            ContractVersion.effective_from <= competence_end,
        )
    )
    if changes_inside_month:
        blockers.append(
            {
                "code": "GATE_A_VERSION_DURING_COMPETENCE",
                "reason": (
                    "Há alteração contratual dentro da competência e sua data de corte "
                    "ainda depende do Gate A."
                ),
            }
        )
    events_inside_month = session.scalar(
        select(func.count())
        .select_from(ContractOperationalEvent)
        .where(
            ContractOperationalEvent.contract_id == contract.id,
            ContractOperationalEvent.event_type.in_(("suspended", "resumed", "terminated")),
            ContractOperationalEvent.effective_on > competence,
            ContractOperationalEvent.effective_on <= competence_end,
        )
    )
    if events_inside_month:
        blockers.append(
            {
                "code": "GATE_A_EVENT_DURING_COMPETENCE",
                "reason": (
                    "Há suspensão, retomada ou encerramento dentro da competência; "
                    "não foi aplicado pró-rata nem retroatividade."
                ),
            }
        )

    snapshot = snapshot_for(
        session,
        contract=contract,
        version=version,
        competence=competence,
        competence_end=competence_end,
        operational_state=operational_state,
        gross_amount=gross_amount,
        blockers=blockers,
    )
    status = "blocked" if blockers else "ready"
    first_blocker = blockers[0] if blockers else None
    item = BillingItem(
        organization_id=contract.organization_id,
        business_unit_id=contract.business_unit_id,
        created_by_run_id=run.id,
        source_type="contract_recurring",
        contract_id=contract.id,
        contract_version_id=version.id if version else None,
        competence_month=competence,
        customer_company_id=contract.customer_company_id,
        issuer_establishment_id=version.issuer_establishment_id if version else None,
        currency=version.currency if version else None,
        gross_amount=gross_amount,
        snapshot=snapshot,
        snapshot_sha256=canonical_hash(snapshot),
        status=status,
        blocking_code=first_blocker["code"] if first_blocker else None,
        blocking_reason=first_blocker["reason"] if first_blocker else None,
        correlation_id=run.correlation_id,
        causation_id=run.causation_id,
        created_by_actor_id=actor.id,
    )
    session.add(item)
    session.flush()
    event_type = "billing.item.blocked.v1" if blockers else "billing.item.ready.v1"
    record_change(
        session,
        actor=actor,
        correlation_id=run.correlation_id,
        action="billing.item.created",
        resource_type="billing_item",
        resource_id=item.id,
        before_state=None,
        after_state={
            "status": item.status,
            "competence_month": competence_label(competence),
            "snapshot_sha256": item.snapshot_sha256,
        },
        event_type=event_type,
        event_payload={
            "schema_version": 1,
            "billing_item_id": str(item.id),
            "contract_id": str(contract.id),
            "contract_version_id": str(version.id) if version else None,
            "competence_month": competence_label(competence),
            "organization_id": str(contract.organization_id),
            "business_unit_id": str(contract.business_unit_id),
            "issuer_establishment_id": str(version.issuer_establishment_id) if version else None,
            "gross_amount": str(gross_amount) if gross_amount is not None else None,
            "currency": version.currency if version else None,
            "snapshot_sha256": item.snapshot_sha256,
            "status": item.status,
        },
    )
    if blockers:
        session.add(
            OperationalException(
                organization_id=contract.organization_id,
                actor_id=actor.id,
                correlation_id=run.correlation_id,
                exception_type="billing.item.blocked",
                severity="medium",
                title="Obrigação de faturamento bloqueada",
                context={
                    "billing_item_id": str(item.id),
                    "contract_id": str(contract.id),
                    "competence_month": competence_label(competence),
                    "blocking_codes": [blocker["code"] for blocker in blockers],
                },
            )
        )
    return item, True


@router.post("/runs", response_model=BillingRunResponse, status_code=201)
def generate_competence(
    command: BillingGenerate,
    request: Request,
    session: SessionDep,
    idempotency_key: IdempotencyHeader,
    actor: Annotated[ActorContext, Depends(require_permission("billing:generate"))],
) -> BillingRunResponse:
    ensure_unit_access(session, actor, "billing:generate", command.business_unit_id)
    competence = competence_date(command.competence_month)
    competence_end = date(
        competence.year, competence.month, monthrange(competence.year, competence.month)[1]
    )
    correlation_id = request.state.correlation_id
    # Authentication and scope checks use SQLAlchemy autobegin. Close that read-only
    # transaction before opening the atomic billing command transaction.
    session.commit()
    with session.begin():
        if session.bind and session.bind.dialect.name == "postgresql":
            session.execute(
                text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"),
                {
                    "key": (
                        f"{actor.organization_id}:{command.business_unit_id}:"
                        f"{command.competence_month}"
                    )
                },
            )
        idempotency, cached = begin_command(
            session,
            actor=actor,
            command_name="billing.generate_competence.v1",
            idempotency_key=idempotency_key,
            payload=command.model_dump(mode="json"),
            correlation_id=correlation_id,
        )
        if cached:
            return BillingRunResponse.model_validate(cached)
        if idempotency:
            idempotency.expires_at = datetime.now(UTC) + timedelta(days=3650)

        existing_run = session.scalar(
            select(BillingRun).where(
                BillingRun.organization_id == actor.organization_id,
                BillingRun.business_unit_id == command.business_unit_id,
                BillingRun.competence_month == competence,
            )
        )
        if existing_run:
            response = run_response(session, existing_run)
            if idempotency:
                complete_command(idempotency, response.model_dump(mode="json"), response_status=200)
            return response

        unit = session.scalar(
            select(BusinessUnit).where(
                BusinessUnit.id == command.business_unit_id,
                BusinessUnit.organization_id == actor.organization_id,
                BusinessUnit.status == "active",
            )
        )
        if unit is None:
            raise HTTPException(status_code=422, detail="Unidade de negócio inválida ou inativa")
        settings = get_settings()
        run = BillingRun(
            organization_id=actor.organization_id,
            business_unit_id=command.business_unit_id,
            competence_month=competence,
            run_type=command.run_type,
            operational_timezone=settings.operational_timezone,
            rule_version=settings.billing_rule_version,
            actor_id=actor.id,
            correlation_id=correlation_id,
            causation_id=command.causation_id,
            metrics={},
        )
        session.add(run)
        session.flush()

        counters = {
            "considered": 0,
            "created": 0,
            "reused": 0,
            "not_eligible": 0,
            "ready": 0,
            "blocked": 0,
        }
        contracts = session.scalars(
            select(Contract)
            .where(
                Contract.organization_id == actor.organization_id,
                Contract.business_unit_id == command.business_unit_id,
            )
            .order_by(Contract.internal_number, Contract.id)
        ).all()
        for contract in contracts:
            counters["considered"] += 1
            entry: BillingRunContract
            if contract.administrative_status != "active":
                entry = not_eligible(
                    run,
                    contract,
                    "CONTRACT_NOT_ACTIVE",
                    "O contrato não está administrativamente ativo.",
                )
            elif contract.start_date > competence:
                detail = (
                    "O contrato começou durante a competência; a regra aprovada inicia "
                    "a cobrança no mês seguinte."
                    if contract.start_date <= competence_end
                    else "O contrato ainda não havia iniciado nesta competência."
                )
                entry = not_eligible(run, contract, "CONTRACT_NOT_STARTED_FOR_FULL_MONTH", detail)
            else:
                state = state_at(session, contract.id, competence)
                has_mid_month_event = session.scalar(
                    select(func.count())
                    .select_from(ContractOperationalEvent)
                    .where(
                        ContractOperationalEvent.contract_id == contract.id,
                        ContractOperationalEvent.event_type.in_(
                            ("suspended", "resumed", "terminated")
                        ),
                        ContractOperationalEvent.effective_on > competence,
                        ContractOperationalEvent.effective_on <= competence_end,
                    )
                )
                if state != "active" and not has_mid_month_event:
                    entry = not_eligible(
                        run,
                        contract,
                        "CONTRACT_OPERATIONALLY_INELIGIBLE",
                        f"O contrato estava {state} no início e durante toda a competência.",
                    )
                else:
                    item, created = create_item_for_contract(
                        session,
                        actor=actor,
                        run=run,
                        contract=contract,
                        competence=competence,
                        competence_end=competence_end,
                    )
                    entry = BillingRunContract(
                        billing_run_id=run.id,
                        contract_id=contract.id,
                        billing_item_id=item.id,
                        outcome="created" if created else "reused",
                    )
                    counters["created" if created else "reused"] += 1
                    counters[item.status] += 1
                    session.add(entry)
                    continue
            counters["not_eligible"] += 1
            session.add(entry)

        run.metrics = counters
        run.status = "completed_with_exceptions" if counters["blocked"] else "completed"
        run.completed_at = datetime.now(UTC)
        record_change(
            session,
            actor=actor,
            correlation_id=correlation_id,
            action="billing.run.completed",
            resource_type="billing_run",
            resource_id=run.id,
            before_state={"status": "processing"},
            after_state={"status": run.status, "metrics": counters},
            event_type="billing.run.completed.v1",
            event_payload={
                "schema_version": 1,
                "billing_run_id": str(run.id),
                "organization_id": str(run.organization_id),
                "business_unit_id": str(run.business_unit_id),
                "competence_month": competence_label(competence),
                "status": run.status,
                "metrics": counters,
            },
        )
        session.flush()
        response = run_response(session, run)
        if idempotency:
            complete_command(idempotency, response.model_dump(mode="json"), response_status=201)
        return response


@router.get("/runs", response_model=list[BillingRunResponse])
def list_runs(
    session: SessionDep,
    actor: Annotated[ActorContext, Depends(require_permission("billing:read"))],
    competence_month: Annotated[str | None, Query(pattern=r"^\d{4}-(0[1-9]|1[0-2])$")] = None,
    business_unit_id: uuid.UUID | None = None,
) -> list[BillingRunResponse]:
    scope = unit_scope(session, actor, "billing:read")
    statement = select(BillingRun).where(BillingRun.organization_id == actor.organization_id)
    if scope is not None:
        statement = statement.where(BillingRun.business_unit_id.in_(scope))
    if competence_month:
        statement = statement.where(
            BillingRun.competence_month == competence_date(competence_month)
        )
    if business_unit_id:
        ensure_unit_access(session, actor, "billing:read", business_unit_id)
        statement = statement.where(BillingRun.business_unit_id == business_unit_id)
    runs = session.scalars(
        statement.order_by(BillingRun.competence_month.desc(), BillingRun.started_at.desc())
    ).all()
    return [run_response(session, run, include_contracts=False) for run in runs]


@router.get("/runs/{run_id}", response_model=BillingRunResponse)
def get_run(
    run_id: uuid.UUID,
    session: SessionDep,
    actor: Annotated[ActorContext, Depends(require_permission("billing:read"))],
) -> BillingRunResponse:
    run = session.scalar(
        select(BillingRun).where(
            BillingRun.id == run_id, BillingRun.organization_id == actor.organization_id
        )
    )
    if run is None:
        raise HTTPException(status_code=404, detail="Execução de faturamento não encontrada")
    ensure_unit_access(session, actor, "billing:read", run.business_unit_id)
    return run_response(session, run)


@router.post("/runs/{run_id}/reprocess", response_model=BillingRunResponse)
def reprocess_run(
    run_id: uuid.UUID,
    request: Request,
    session: SessionDep,
    idempotency_key: IdempotencyHeader,
    actor: Annotated[ActorContext, Depends(require_permission("billing:reprocess"))],
) -> BillingRunResponse:
    session.commit()
    with session.begin():
        run = session.scalar(
            select(BillingRun).where(
                BillingRun.id == run_id, BillingRun.organization_id == actor.organization_id
            )
        )
        if run is None:
            raise HTTPException(status_code=404, detail="Execução de faturamento não encontrada")
        ensure_unit_access(session, actor, "billing:reprocess", run.business_unit_id)
        record, cached = begin_command(
            session,
            actor=actor,
            command_name="billing.reprocess_safe.v1",
            idempotency_key=idempotency_key,
            payload={"billing_run_id": str(run_id)},
            correlation_id=request.state.correlation_id,
        )
        if cached:
            return BillingRunResponse.model_validate(cached)
        response = run_response(session, run)
        if record:
            record.expires_at = datetime.now(UTC) + timedelta(days=3650)
            complete_command(record, response.model_dump(mode="json"), response_status=200)
        return response


@router.get("/items", response_model=list[BillingItemSummary])
def list_items(
    session: SessionDep,
    actor: Annotated[ActorContext, Depends(require_permission("billing:read"))],
    competence_month: Annotated[str | None, Query(pattern=r"^\d{4}-(0[1-9]|1[0-2])$")] = None,
    business_unit_id: uuid.UUID | None = None,
    customer_company_id: uuid.UUID | None = None,
    status: Annotated[
        str | None, Query(pattern=r"^(blocked|ready|requested|completed|cancelled)$")
    ] = None,
    run_id: uuid.UUID | None = None,
) -> list[BillingItemSummary]:
    scope = unit_scope(session, actor, "billing:read")
    statement = select(BillingItem).where(BillingItem.organization_id == actor.organization_id)
    if scope is not None:
        statement = statement.where(BillingItem.business_unit_id.in_(scope))
    if competence_month:
        statement = statement.where(
            BillingItem.competence_month == competence_date(competence_month)
        )
    if business_unit_id:
        ensure_unit_access(session, actor, "billing:read", business_unit_id)
        statement = statement.where(BillingItem.business_unit_id == business_unit_id)
    if customer_company_id:
        statement = statement.where(BillingItem.customer_company_id == customer_company_id)
    if status:
        statement = statement.where(BillingItem.status == status)
    if run_id:
        statement = statement.join(
            BillingRunContract, BillingRunContract.billing_item_id == BillingItem.id
        ).where(BillingRunContract.billing_run_id == run_id)
    items = session.scalars(
        statement.order_by(BillingItem.competence_month.desc(), BillingItem.created_at)
    ).all()
    return [item_summary(session, item) for item in items]


@router.get("/items/{item_id}", response_model=BillingItemDetail)
def get_item(
    item_id: uuid.UUID,
    session: SessionDep,
    actor: Annotated[ActorContext, Depends(require_permission("billing:read"))],
) -> BillingItemDetail:
    item = session.scalar(
        select(BillingItem).where(
            BillingItem.id == item_id, BillingItem.organization_id == actor.organization_id
        )
    )
    if item is None:
        raise HTTPException(status_code=404, detail="Obrigação de faturamento não encontrada")
    ensure_unit_access(session, actor, "billing:read", item.business_unit_id)
    history: list[BillingHistoryEvent] = []
    for audit in session.scalars(
        select(AuditEvent).where(
            AuditEvent.resource_type == "billing_item", AuditEvent.resource_id == item.id
        )
    ):
        history.append(
            BillingHistoryEvent(
                kind="audit",
                name=audit.action,
                occurred_at=utc_datetime(audit.occurred_at),
                correlation_id=audit.correlation_id,
            )
        )
    for event in session.scalars(
        select(OutboxEvent).where(
            OutboxEvent.aggregate_type == "billing_item", OutboxEvent.aggregate_id == item.id
        )
    ):
        history.append(
            BillingHistoryEvent(
                kind="outbox",
                name=event.event_type,
                occurred_at=utc_datetime(event.created_at),
                correlation_id=event.correlation_id,
                status=event.status,
            )
        )
    history.sort(key=lambda value: value.occurred_at)
    return BillingItemDetail(
        **item_summary(session, item).model_dump(), snapshot=item.snapshot, history=history
    )


@router.get("/exceptions", response_model=list[BillingExceptionResponse])
def list_exceptions(
    session: SessionDep,
    actor: Annotated[ActorContext, Depends(require_permission("billing:review"))],
    competence_month: Annotated[str | None, Query(pattern=r"^\d{4}-(0[1-9]|1[0-2])$")] = None,
    business_unit_id: uuid.UUID | None = None,
) -> list[BillingExceptionResponse]:
    scope = unit_scope(session, actor, "billing:review")
    statement = select(BillingItem).where(
        BillingItem.organization_id == actor.organization_id, BillingItem.status == "blocked"
    )
    if scope is not None:
        statement = statement.where(BillingItem.business_unit_id.in_(scope))
    if competence_month:
        statement = statement.where(
            BillingItem.competence_month == competence_date(competence_month)
        )
    if business_unit_id:
        ensure_unit_access(session, actor, "billing:review", business_unit_id)
        statement = statement.where(BillingItem.business_unit_id == business_unit_id)
    result = []
    for item in session.scalars(statement.order_by(BillingItem.created_at.desc())):
        base = item_summary(session, item)
        result.append(
            BillingExceptionResponse(
                billing_item_id=item.id,
                contract_id=item.contract_id,
                contract_number=base.contract_number,
                competence_month=base.competence_month,
                customer_name=base.customer_name,
                code=item.blocking_code or "UNKNOWN",
                reason=item.blocking_reason or "Bloqueio sem detalhe",
                created_at=item.created_at,
            )
        )
    return result


@router.get("/summary", response_model=BillingSummaryResponse)
def billing_summary(
    competence_month: Annotated[str, Query(pattern=r"^\d{4}-(0[1-9]|1[0-2])$")],
    session: SessionDep,
    actor: Annotated[ActorContext, Depends(require_permission("billing:read"))],
    business_unit_id: uuid.UUID | None = None,
) -> BillingSummaryResponse:
    scope = unit_scope(session, actor, "billing:read")
    competence = competence_date(competence_month)
    statement = select(BillingItem).where(
        BillingItem.organization_id == actor.organization_id,
        BillingItem.competence_month == competence,
    )
    if scope is not None:
        statement = statement.where(BillingItem.business_unit_id.in_(scope))
    if business_unit_id:
        ensure_unit_access(session, actor, "billing:read", business_unit_id)
        statement = statement.where(BillingItem.business_unit_id == business_unit_id)
    items = session.scalars(statement).all()
    grouped: dict[uuid.UUID, dict[str, Any]] = {}
    for item in items:
        unit = session.get(BusinessUnit, item.business_unit_id)
        bucket = grouped.setdefault(
            item.business_unit_id,
            {
                "business_unit_id": str(item.business_unit_id),
                "business_unit_name": unit.name if unit else "Unidade indisponível",
                "count": 0,
                "gross_amount": Decimal("0.00"),
            },
        )
        bucket["count"] += 1
        bucket["gross_amount"] += Decimal(item.gross_amount or 0)
    ready = [item for item in items if item.status == "ready"]
    blocked = [item for item in items if item.status == "blocked"]
    return BillingSummaryResponse(
        competence_month=competence_month,
        predicted_gross_amount=sum(
            (Decimal(item.gross_amount or 0) for item in ready), Decimal("0.00")
        ),
        eligible_contracts=len(items),
        blocked_contracts=len(blocked),
        blocked_gross_amount=sum(
            (Decimal(item.gross_amount or 0) for item in blocked), Decimal("0.00")
        ),
        ready_contracts=len(ready),
        by_business_unit=list(grouped.values()),
    )
