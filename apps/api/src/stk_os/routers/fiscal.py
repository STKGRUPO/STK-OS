from __future__ import annotations

import hashlib
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from fastapi.responses import FileResponse
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from stk_os.commands import begin_command, complete_command, record_change
from stk_os.config import get_settings
from stk_os.database import SessionDep
from stk_os.dependencies import require_permission
from stk_os.fiscal.dps import build_dps
from stk_os.fiscal.provider import ProviderResult
from stk_os.fiscal.runtime import FiscalRuntime, get_fiscal_runtime
from stk_os.fiscal_schemas import (
    FiscalAttemptResponse,
    FiscalDocumentResponse,
    FiscalIssuanceResponse,
    FiscalReconcileRequest,
    OneTimeBillingCreate,
    OneTimeBillingResponse,
)
from stk_os.models import (
    BillingItem,
    BusinessUnit,
    ClientService,
    ClientServiceOccurrence,
    Company,
    CompanyBusinessUnit,
    FiscalAttempt,
    FiscalDocument,
    FiscalEstablishment,
    FiscalEstablishmentConfig,
    FiscalIssuance,
    LegalEntity,
    OperationalException,
    ProductService,
)
from stk_os.routers.billing import ensure_unit_access
from stk_os.schemas import ActorContext
from stk_os.security import canonical_hash

router = APIRouter(tags=["fiscal"])
IdempotencyHeader = Annotated[str, Header(alias="Idempotency-Key", min_length=8, max_length=255)]
RuntimeDep = Annotated[FiscalRuntime, Depends(get_fiscal_runtime)]


def utc(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=UTC)


def get_item(
    session: Session, actor: ActorContext, item_id: uuid.UUID, permission: str
) -> BillingItem:
    item = session.scalar(
        select(BillingItem).where(
            BillingItem.id == item_id, BillingItem.organization_id == actor.organization_id
        )
    )
    if item is None:
        raise HTTPException(status_code=404, detail="Item faturável não encontrado")
    ensure_unit_access(session, actor, permission, item.business_unit_id)
    return item


def service_description(item: BillingItem) -> str:
    snapshot = item.snapshot
    if item.source_type == "contract_recurring":
        version = snapshot.get("contract_version") or {}
        services = snapshot.get("services") or []
        return str(
            version.get("invoice_description")
            or (services[0].get("description") if services else None)
            or "Serviço recorrente"
        )
    service = snapshot.get("service") or {}
    return str(service.get("description") or service.get("name") or "Serviço prestado")


def build_fiscal_snapshot(
    session: Session,
    item: BillingItem,
    config: FiscalEstablishmentConfig,
    *,
    issued_at: datetime,
) -> dict[str, Any]:
    customer = session.get(Company, item.customer_company_id)
    issuer = session.get(FiscalEstablishment, item.issuer_establishment_id)
    entity = session.get(LegalEntity, issuer.legal_entity_id) if issuer else None
    if customer is None or issuer is None or entity is None:
        raise HTTPException(status_code=422, detail="Cliente ou emissor fiscal indisponível")
    missing: list[str] = []
    if not customer.tax_id or len(customer.tax_id) != 14:
        missing.append("CNPJ do cliente")
    if not customer.address_line:
        missing.append("endereço do cliente")
    if not customer.municipality_code or len(customer.municipality_code) != 7:
        missing.append("código IBGE do município do cliente")
    if not customer.postal_code or len(customer.postal_code) != 8:
        missing.append("CEP do cliente")
    issuer_tax_id = issuer.tax_id or entity.tax_id
    if not issuer_tax_id or len(issuer_tax_id) != 14:
        missing.append("CNPJ do emissor")
    if item.gross_amount is None or Decimal(item.gross_amount) <= 0:
        missing.append("valor positivo")
    if missing:
        raise HTTPException(
            status_code=422,
            detail="Validação fiscal pendente: " + ", ".join(missing),
        )
    return {
        "schema_version": "fiscal-issuance-snapshot.v1",
        "billing_item_id": str(item.id),
        "billing_source_type": item.source_type,
        "billing_snapshot_sha256": item.snapshot_sha256,
        "environment": config.environment,
        "issued_at": issued_at.isoformat(),
        "competence_date": item.competence_month.isoformat(),
        "reference": (item.snapshot.get("service") or {}).get("reference")
        or item.competence_month.strftime("%Y-%m"),
        "gross_amount": str(Decimal(item.gross_amount)),
        "currency": item.currency,
        "issuer": {
            "establishment_id": str(issuer.id),
            "name": issuer.name,
            "tax_id": issuer_tax_id,
            "municipality_code": config.municipality_code,
            "certificate_key_id": config.certificate_key_id,
        },
        "customer": {
            "company_id": str(customer.id),
            "legal_name": customer.legal_name,
            "tax_id": customer.tax_id,
            "address_line": customer.address_line,
            "municipality_code": customer.municipality_code,
            "postal_code": customer.postal_code,
        },
        "service_description": service_description(item),
        "service_code": config.service_code,
        "nbs_code": config.nbs_code,
        "fiscal_rules": config.fiscal_rules,
    }


def response_for(session: Session, issuance: FiscalIssuance) -> FiscalIssuanceResponse:
    config = session.get(FiscalEstablishmentConfig, issuance.establishment_config_id)
    issuer = session.get(FiscalEstablishment, config.establishment_id) if config else None
    attempts = list(
        session.scalars(
            select(FiscalAttempt)
            .where(FiscalAttempt.issuance_id == issuance.id)
            .order_by(FiscalAttempt.attempt_number)
        ).all()
    )
    documents = list(
        session.scalars(
            select(FiscalDocument)
            .where(FiscalDocument.issuance_id == issuance.id)
            .order_by(FiscalDocument.document_type)
        ).all()
    )
    return FiscalIssuanceResponse(
        id=issuance.id,
        billing_item_id=issuance.billing_item_id,
        status=issuance.status,
        environment=issuance.environment,
        issuer_establishment_id=config.establishment_id if config else uuid.UUID(int=0),
        issuer_name=issuer.name if issuer else "Emissor indisponível",
        series=issuance.series,
        dps_number=issuance.dps_number,
        dps_id=issuance.dps_id,
        nfse_number=issuance.nfse_number,
        access_key=issuance.access_key,
        provider_reference=issuance.provider_reference,
        error_category=issuance.error_category,
        error_code=issuance.error_code,
        error_message=issuance.error_message,
        requested_at=utc(issuance.requested_at),
        last_reconciled_at=utc(issuance.last_reconciled_at)
        if issuance.last_reconciled_at
        else None,
        completed_at=utc(issuance.completed_at) if issuance.completed_at else None,
        documents=[
            FiscalDocumentResponse(
                id=document.id,
                document_type=document.document_type,
                content_type=document.content_type,
                content_sha256=document.content_sha256,
                size_bytes=document.size_bytes,
                status=document.status,
                download_path=f"/api/v1/fiscal/documents/{document.id}/content"
                if document.status == "available"
                else None,
            )
            for document in documents
        ],
        attempts=[
            FiscalAttemptResponse(
                attempt_number=attempt.attempt_number,
                operation=attempt.operation,
                outcome=attempt.outcome,
                external_status=attempt.external_status,
                error_category=attempt.error_category,
                error_code=attempt.error_code,
                sanitized_detail=attempt.sanitized_detail,
                started_at=utc(attempt.started_at),
                completed_at=utc(attempt.completed_at) if attempt.completed_at else None,
            )
            for attempt in attempts
        ],
    )


def next_attempt_number(session: Session, issuance_id: uuid.UUID) -> int:
    return (
        int(
            session.scalar(
                select(func.coalesce(func.max(FiscalAttempt.attempt_number), 0)).where(
                    FiscalAttempt.issuance_id == issuance_id
                )
            )
            or 0
        )
        + 1
    )


def persist_exception(
    session: Session,
    actor: ActorContext,
    correlation_id: uuid.UUID,
    *,
    issuance_id: uuid.UUID | None,
    category: str,
    code: str,
    detail: str,
) -> None:
    session.add(
        OperationalException(
            organization_id=actor.organization_id,
            actor_id=actor.id,
            correlation_id=correlation_id,
            exception_type=f"fiscal.{category}",
            severity="high" if category in ("uncertain", "configuration") else "medium",
            title="Exceção na emissão fiscal",
            context={
                "issuance_id": str(issuance_id) if issuance_id else None,
                "code": code,
                "detail": detail[:1000],
            },
        )
    )


def apply_provider_result(
    session: Session,
    runtime: FiscalRuntime,
    actor: ActorContext,
    issuance: FiscalIssuance,
    attempt: FiscalAttempt,
    result: ProviderResult,
) -> None:
    now = datetime.now(UTC)
    attempt.external_status = result.http_status
    attempt.provider_reference = result.provider_reference
    attempt.outcome = result.status
    attempt.error_code = result.error_code
    attempt.sanitized_detail = result.detail[:1000] if result.detail else None
    attempt.completed_at = now
    issuance.provider_reference = result.provider_reference or issuance.provider_reference
    issuance.lease_owner = None
    issuance.lease_expires_at = None
    item = session.get(BillingItem, issuance.billing_item_id)
    if result.status == "completed" and result.nfse_number and result.access_key:
        issuance.nfse_number = result.nfse_number
        issuance.access_key = result.access_key
        issuance.error_category = issuance.error_code = issuance.error_message = None
        issuance.completed_at = now
        document_failed = False
        for provider_document in result.documents:
            extension = "xml" if provider_document.content_type == "application/xml" else "pdf"
            key = (
                f"{issuance.organization_id}/{issuance.id}/"
                f"{provider_document.document_type}.{extension}"
            )
            try:
                digest, size = runtime.document_store.put(key, provider_document.content)
                session.add(
                    FiscalDocument(
                        issuance_id=issuance.id,
                        document_type=provider_document.document_type,
                        storage_key=key,
                        content_type=provider_document.content_type,
                        content_sha256=digest,
                        size_bytes=size,
                        status="available",
                    )
                )
            except OSError:
                document_failed = True
                session.add(
                    FiscalDocument(
                        issuance_id=issuance.id,
                        document_type=provider_document.document_type,
                        content_type=provider_document.content_type,
                        status="failed",
                        error_code="DOCUMENT_STORAGE_FAILED",
                    )
                )
        issuance.status = "document_error" if document_failed else "completed"
        if item:
            item.status = "completed"
    else:
        if result.error_code == "CERTIFICATE_INVALID":
            result_status = "configuration_error"
            result_category = "configuration"
        else:
            result_status = ""
            result_category = ""
        mapping = {
            "rejected": ("rejected", "known_fiscal", result.error_code or "FISCAL_REJECTION"),
            "uncertain": ("uncertain", "uncertain", result.error_code or "TRANSMISSION_UNCERTAIN"),
            "external_unavailable": (
                "external_unavailable",
                "external_unavailable",
                result.error_code or "SEFIN_UNAVAILABLE",
            ),
            "not_found": ("external_unavailable", "external_unavailable", "CONFIRMED_NOT_FOUND"),
        }
        status, category, code = mapping[result.status]
        status = result_status or status
        category = result_category or category
        issuance.status = status
        issuance.error_category = category
        issuance.error_code = code
        issuance.error_message = result.detail or code
        attempt.error_category = category
        persist_exception(
            session,
            actor,
            issuance.correlation_id,
            issuance_id=issuance.id,
            category=category,
            code=code,
            detail=issuance.error_message,
        )
    record_change(
        session,
        actor=actor,
        correlation_id=issuance.correlation_id,
        action=f"fiscal.issuance.{issuance.status}",
        resource_type="fiscal_issuance",
        resource_id=issuance.id,
        before_state={"status": "processing"},
        after_state={
            "status": issuance.status,
            "nfse_number": issuance.nfse_number,
            "error_code": issuance.error_code,
        },
        event_type=f"fiscal.issuance.{issuance.status}.v1",
        event_payload={
            "issuance_id": str(issuance.id),
            "billing_item_id": str(issuance.billing_item_id),
            "status": issuance.status,
        },
    )


def transmit_existing(
    session: Session,
    runtime: FiscalRuntime,
    actor: ActorContext,
    issuance: FiscalIssuance,
) -> FiscalIssuanceResponse:
    config = session.get(FiscalEstablishmentConfig, issuance.establishment_config_id)
    if config is None:
        raise HTTPException(status_code=422, detail="Configuração fiscal não encontrada")
    issued_at = datetime.fromisoformat(str(issuance.snapshot["issued_at"]))
    unsigned, identifier, _decision = build_dps(
        issuance.snapshot,
        series=issuance.series,
        number=issuance.dps_number,
        issued_at=issued_at,
    )
    if identifier != issuance.dps_id:
        raise HTTPException(status_code=409, detail="Identidade DPS divergente; emissão bloqueada")
    try:
        gateway = runtime.gateway_for(session, config)
    except (RuntimeError, ValueError) as error:
        issuance.status = "configuration_error"
        issuance.error_category = "configuration"
        issuance.error_code = "CERTIFICATE_INVALID"
        issuance.error_message = str(error)
        persist_exception(
            session,
            actor,
            issuance.correlation_id,
            issuance_id=issuance.id,
            category="configuration",
            code="CERTIFICATE_INVALID",
            detail=str(error),
        )
        session.commit()
        return response_for(session, issuance)
    request_sha256 = hashlib.sha256(unsigned).hexdigest()
    issuance.status = "processing"
    issuance.error_category = issuance.error_code = issuance.error_message = None
    issuance.lease_owner = str(uuid.uuid4())
    issuance.lease_expires_at = datetime.now(UTC) + timedelta(minutes=2)
    attempt = FiscalAttempt(
        issuance_id=issuance.id,
        attempt_number=next_attempt_number(session, issuance.id),
        operation="issue",
        request_sha256=request_sha256,
        outcome="processing",
    )
    session.add(attempt)
    session.commit()  # intenção e DPS ficam duráveis antes do efeito externo
    result = gateway.issue(endpoint=config.endpoint, dps_id=issuance.dps_id, signed_xml=unsigned)
    issuance = session.get(FiscalIssuance, issuance.id)
    attempt = session.get(FiscalAttempt, attempt.id)
    assert issuance is not None and attempt is not None
    issuance.signed_dps_sha256 = result.signed_dps_sha256
    apply_provider_result(session, runtime, actor, issuance, attempt, result)
    session.commit()
    return response_for(session, issuance)


@router.post(
    "/billing/items/{item_id}/issue", response_model=FiscalIssuanceResponse, status_code=202
)
def issue_billing_item(
    item_id: uuid.UUID,
    request: Request,
    session: SessionDep,
    runtime: RuntimeDep,
    idempotency_key: IdempotencyHeader,
    actor: Annotated[ActorContext, Depends(require_permission("fiscal:issue"))],
) -> FiscalIssuanceResponse:
    item = get_item(session, actor, item_id, "fiscal:issue")
    record, cached = begin_command(
        session,
        actor=actor,
        command_name="fiscal.issue_billing_item.v1",
        idempotency_key=idempotency_key,
        payload={"billing_item_id": str(item.id)},
        correlation_id=request.state.correlation_id,
    )
    if cached:
        return FiscalIssuanceResponse.model_validate(cached)
    existing = session.scalar(
        select(FiscalIssuance).where(FiscalIssuance.billing_item_id == item.id).with_for_update()
    )
    if existing:
        if existing.status in ("completed", "document_error"):
            response = response_for(session, existing)
        elif existing.status == "configuration_error" or (
            existing.status == "external_unavailable"
            and existing.error_code == "CONFIRMED_NOT_FOUND"
        ):
            response = transmit_existing(session, runtime, actor, existing)
        else:
            response = response_for(session, existing)
        if record:
            complete_command(record, response.model_dump(mode="json"), response_status=202)
            session.commit()
        return response
    if item.status != "ready":
        raise HTTPException(status_code=409, detail="Item não está pronto para emissão")
    if item.issuer_establishment_id is None:
        raise HTTPException(status_code=422, detail="Item sem estabelecimento emissor definido")
    settings = get_settings()
    config = session.scalar(
        select(FiscalEstablishmentConfig)
        .where(
            FiscalEstablishmentConfig.organization_id == actor.organization_id,
            FiscalEstablishmentConfig.establishment_id == item.issuer_establishment_id,
            FiscalEstablishmentConfig.environment == settings.fiscal_environment,
            FiscalEstablishmentConfig.status == "active",
            FiscalEstablishmentConfig.emission_method == "api_a1",
        )
        .with_for_update()
    )
    if config is None:
        persist_exception(
            session,
            actor,
            request.state.correlation_id,
            issuance_id=None,
            category="configuration",
            code="ISSUER_CONFIG_UNAVAILABLE",
            detail="Emissor do billing item não possui configuração fiscal ativa",
        )
        session.commit()
        raise HTTPException(status_code=422, detail="Emissor sem configuração fiscal ativa")
    issued_at = datetime.now(UTC)
    try:
        snapshot = build_fiscal_snapshot(session, item, config, issued_at=issued_at)
    except HTTPException as error:
        persist_exception(
            session,
            actor,
            request.state.correlation_id,
            issuance_id=None,
            category="validation",
            code="FISCAL_VALIDATION_FAILED",
            detail=str(error.detail),
        )
        session.commit()
        raise
    number = config.next_dps_number
    config.next_dps_number += 1
    identifier = (
        "DPS"
        + config.municipality_code
        + "2"
        + str(snapshot["issuer"]["tax_id"])
        + f"{config.series:05d}"
        + f"{number:015d}"
    )
    issuance = FiscalIssuance(
        organization_id=actor.organization_id,
        billing_item_id=item.id,
        establishment_config_id=config.id,
        environment=config.environment,
        status="validating",
        series=config.series,
        dps_number=number,
        dps_id=identifier,
        snapshot=snapshot,
        snapshot_sha256=canonical_hash(snapshot),
        requested_by_actor_id=actor.id,
        correlation_id=request.state.correlation_id,
    )
    session.add(issuance)
    item.status = "requested"
    try:
        session.flush()
    except IntegrityError as error:
        session.rollback()
        existing = session.scalar(
            select(FiscalIssuance).where(FiscalIssuance.billing_item_id == item.id)
        )
        if existing:
            return response_for(session, existing)
        raise HTTPException(status_code=409, detail="Emissão concorrente detectada") from error
    record_change(
        session,
        actor=actor,
        correlation_id=request.state.correlation_id,
        action="fiscal.issuance.requested",
        resource_type="fiscal_issuance",
        resource_id=issuance.id,
        before_state=None,
        after_state={"status": "validating", "billing_item_id": str(item.id)},
        event_type="fiscal.issuance.requested.v1",
        event_payload={"issuance_id": str(issuance.id), "billing_item_id": str(item.id)},
    )
    session.commit()
    response = transmit_existing(session, runtime, actor, issuance)
    if record:
        record = session.merge(record)
        complete_command(record, response.model_dump(mode="json"), response_status=202)
        session.commit()
    return response


@router.get("/billing/items/{item_id}/issuance", response_model=FiscalIssuanceResponse)
def get_item_issuance(
    item_id: uuid.UUID,
    session: SessionDep,
    actor: Annotated[ActorContext, Depends(require_permission("fiscal:read"))],
) -> FiscalIssuanceResponse:
    item = get_item(session, actor, item_id, "fiscal:read")
    issuance = session.scalar(
        select(FiscalIssuance).where(FiscalIssuance.billing_item_id == item.id)
    )
    if issuance is None:
        raise HTTPException(status_code=404, detail="Item ainda não possui emissão fiscal")
    return response_for(session, issuance)


@router.post("/fiscal/issuances/{issuance_id}/reconcile", response_model=FiscalIssuanceResponse)
def reconcile_issuance(
    issuance_id: uuid.UUID,
    command: FiscalReconcileRequest,
    request: Request,
    session: SessionDep,
    runtime: RuntimeDep,
    idempotency_key: IdempotencyHeader,
    actor: Annotated[ActorContext, Depends(require_permission("fiscal:reconcile"))],
) -> FiscalIssuanceResponse:
    issuance = session.scalar(
        select(FiscalIssuance)
        .where(
            FiscalIssuance.id == issuance_id,
            FiscalIssuance.organization_id == actor.organization_id,
        )
        .with_for_update()
    )
    if issuance is None:
        raise HTTPException(status_code=404, detail="Emissão fiscal não encontrada")
    item = get_item(session, actor, issuance.billing_item_id, "fiscal:reconcile")
    del item
    record, cached = begin_command(
        session,
        actor=actor,
        command_name="fiscal.reconcile.v1",
        idempotency_key=idempotency_key,
        payload={
            "issuance_id": str(issuance_id),
            "resend_if_confirmed_not_found": command.resend_if_confirmed_not_found,
        },
        correlation_id=request.state.correlation_id,
    )
    if cached:
        return FiscalIssuanceResponse.model_validate(cached)
    if issuance.status == "completed":
        response = response_for(session, issuance)
    else:
        config = session.get(FiscalEstablishmentConfig, issuance.establishment_config_id)
        if config is None:
            raise HTTPException(status_code=422, detail="Configuração fiscal indisponível")
        gateway = runtime.gateway_for(session, config)
        attempt = FiscalAttempt(
            issuance_id=issuance.id,
            attempt_number=next_attempt_number(session, issuance.id),
            operation="reconcile",
            outcome="processing",
        )
        session.add(attempt)
        session.commit()
        result = gateway.reconcile(query_base_url=config.query_base_url, dps_id=issuance.dps_id)
        issuance = session.get(FiscalIssuance, issuance.id)
        attempt = session.get(FiscalAttempt, attempt.id)
        assert issuance is not None and attempt is not None
        issuance.last_reconciled_at = datetime.now(UTC)
        apply_provider_result(session, runtime, actor, issuance, attempt, result)
        session.commit()
        if result.status == "not_found" and command.resend_if_confirmed_not_found:
            response = transmit_existing(session, runtime, actor, issuance)
        else:
            response = response_for(session, issuance)
    if record:
        record = session.merge(record)
        complete_command(record, response.model_dump(mode="json"), response_status=200)
        session.commit()
    return response


@router.get("/fiscal/documents/{document_id}/content")
def fiscal_document_content(
    document_id: uuid.UUID,
    session: SessionDep,
    runtime: RuntimeDep,
    actor: Annotated[ActorContext, Depends(require_permission("fiscal:read"))],
) -> FileResponse:
    document = session.scalar(
        select(FiscalDocument)
        .join(FiscalIssuance, FiscalIssuance.id == FiscalDocument.issuance_id)
        .where(
            FiscalDocument.id == document_id,
            FiscalIssuance.organization_id == actor.organization_id,
        )
    )
    if document is None or document.status != "available" or not document.storage_key:
        raise HTTPException(status_code=404, detail="Documento fiscal indisponível")
    issuance = session.get(FiscalIssuance, document.issuance_id)
    assert issuance is not None
    get_item(session, actor, issuance.billing_item_id, "fiscal:read")
    path = runtime.document_store.path_for(document.storage_key)
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Documento fiscal indisponível no storage")
    extension = "xml" if document.content_type == "application/xml" else "pdf"
    return FileResponse(
        path,
        media_type=document.content_type,
        filename=(
            f"{document.document_type}-{issuance.nfse_number or issuance.dps_number}.{extension}"
        ),
    )


@router.post("/billing/one-time", response_model=OneTimeBillingResponse, status_code=201)
def create_one_time_billing(
    command: OneTimeBillingCreate,
    request: Request,
    session: SessionDep,
    idempotency_key: IdempotencyHeader,
    actor: Annotated[ActorContext, Depends(require_permission("billing:generate"))],
) -> OneTimeBillingResponse:
    ensure_unit_access(session, actor, "billing:generate", command.business_unit_id)
    record, cached = begin_command(
        session,
        actor=actor,
        command_name="billing.create_one_time.v1",
        idempotency_key=idempotency_key,
        payload=command.model_dump(mode="json"),
        correlation_id=request.state.correlation_id,
    )
    if cached:
        return OneTimeBillingResponse.model_validate(cached)
    company = session.scalar(
        select(Company)
        .join(CompanyBusinessUnit, CompanyBusinessUnit.company_id == Company.id)
        .where(
            Company.id == command.customer_company_id,
            Company.organization_id == actor.organization_id,
            Company.status == "active",
            CompanyBusinessUnit.business_unit_id == command.business_unit_id,
            CompanyBusinessUnit.status == "active",
        )
    )
    if company is None:
        raise HTTPException(
            status_code=422, detail="Cliente deve existir no CRM e pertencer à unidade"
        )
    unit = session.get(BusinessUnit, command.business_unit_id)
    if unit is None or unit.primary_establishment_id != command.issuer_establishment_id:
        raise HTTPException(
            status_code=422, detail="Emissor não permitido para a unidade selecionada"
        )
    product = (
        session.get(ProductService, command.product_service_id)
        if command.product_service_id
        else None
    )
    if product and product.business_unit_id != command.business_unit_id:
        raise HTTPException(status_code=422, detail="Serviço não pertence à unidade selecionada")
    service = ClientService(
        organization_id=actor.organization_id,
        business_unit_id=command.business_unit_id,
        customer_company_id=company.id,
        product_service_id=product.id if product else None,
        contract_id=None,
        name=command.service_name,
        description=command.description,
        service_type="one_time",
        recurrence=None,
        interval_months=None,
        start_date=command.service_date,
        next_occurrence_on=None,
        owner_actor_id=actor.id,
        amount=command.amount,
        currency=command.currency,
        operational_lead_days=0,
        reminder_lead_days=0,
        status="active",
        created_by_actor_id=actor.id,
    )
    session.add(service)
    session.flush()
    occurrence = ClientServiceOccurrence(
        organization_id=actor.organization_id,
        client_service_id=service.id,
        scheduled_for=command.service_date,
        due_on=command.service_date,
        status="to_bill",
        billing_status="item_created",
        owner_actor_id=actor.id,
        created_by_actor_id=actor.id,
    )
    session.add(occurrence)
    session.flush()
    blockers: list[dict[str, str]] = []
    if not company.tax_id or not company.municipality_code or not company.postal_code:
        blockers.append(
            {
                "code": "CUSTOMER_FISCAL_DATA_INCOMPLETE",
                "reason": "Complete CNPJ, código IBGE e CEP no cadastro CRM do cliente.",
            }
        )
    snapshot = {
        "schema_version": "billing-item-snapshot.v3",
        "source": {
            "type": "service_one_time",
            "client_service_id": str(service.id),
            "service_occurrence_id": str(occurrence.id),
        },
        "service": {
            "name": command.service_name,
            "description": command.description,
            "reference": command.reference,
            "scheduled_for": command.service_date.isoformat(),
            "product_service_id": str(product.id) if product else None,
        },
        "customer": {"id": str(company.id)},
        "issuer": {"id": str(command.issuer_establishment_id)},
        "currency": command.currency,
        "gross_amount": str(command.amount),
        "blockers": blockers,
    }
    first = blockers[0] if blockers else None
    item = BillingItem(
        organization_id=actor.organization_id,
        business_unit_id=command.business_unit_id,
        created_by_run_id=None,
        source_type="service_one_time",
        client_service_id=service.id,
        service_occurrence_id=occurrence.id,
        contract_id=None,
        contract_version_id=None,
        competence_month=command.service_date.replace(day=1),
        customer_company_id=company.id,
        issuer_establishment_id=command.issuer_establishment_id,
        currency=command.currency,
        gross_amount=command.amount,
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
    record_change(
        session,
        actor=actor,
        correlation_id=request.state.correlation_id,
        action="billing.item.created",
        resource_type="billing_item",
        resource_id=item.id,
        before_state=None,
        after_state={"status": item.status, "source_type": "service_one_time"},
        event_type="billing.item.ready.v1" if item.status == "ready" else "billing.item.blocked.v1",
        event_payload={"billing_item_id": str(item.id), "source_type": "service_one_time"},
    )
    body = OneTimeBillingResponse(
        client_service_id=service.id,
        service_occurrence_id=occurrence.id,
        billing_item_id=item.id,
        billing_status=item.status,
    )
    if record:
        complete_command(record, body.model_dump(mode="json"), response_status=201)
    session.commit()
    return body
