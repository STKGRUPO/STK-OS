from __future__ import annotations

import hashlib
import logging
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from fastapi.responses import FileResponse, Response
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from stk_os.commands import begin_command, complete_command, record_change
from stk_os.config import get_settings
from stk_os.database import SessionDep
from stk_os.dependencies import require_permission
from stk_os.fiscal.configuration import FiscalConfigurationError, validate_fiscal_config
from stk_os.fiscal.documents import (
    extract_authorized_nfse_metadata,
    friendly_nfse_filename,
    render_danfse_from_authorized_xml,
)
from stk_os.fiscal.dps import build_dps
from stk_os.fiscal.provider import FiscalGateway, ProviderDocument, ProviderResult
from stk_os.fiscal.runtime import FiscalRuntime, get_fiscal_runtime
from stk_os.fiscal.sequence import (
    reserve_dps_number,
    sync_dps_sequence,
)
from stk_os.fiscal_schemas import (
    FiscalAttemptResponse,
    FiscalBatchIssueRequest,
    FiscalBatchIssueResponse,
    FiscalBatchItemResult,
    FiscalDocumentResponse,
    FiscalIssuanceResponse,
    FiscalReconcileRequest,
    OneTimeBillingCreate,
    OneTimeBillingResponse,
)
from stk_os.models import (
    BillingItem,
    BillingItemRemoval,
    BusinessUnit,
    ClientService,
    ClientServiceOccurrence,
    Company,
    CompanyBusinessUnit,
    ContactMethod,
    FiscalAttempt,
    FiscalDocument,
    FiscalEstablishment,
    FiscalEstablishmentConfig,
    FiscalIssuance,
    LegalEntity,
    OperationalException,
    ProductService,
)
from stk_os.routers.billing import (
    FISCAL_FIELD_LABELS,
    ensure_unit_access,
    missing_customer_fiscal_fields,
)
from stk_os.schemas import ActorContext
from stk_os.security import canonical_hash

router = APIRouter(tags=["fiscal"])
logger = logging.getLogger(__name__)
DPS_COLLISION_CONSTRAINTS = {
    "fiscal_issuances_dps_id_key",
    "fiscal_issuances_establishment_config_id_environment_series_dps_number_key",
}
IdempotencyHeader = Annotated[str, Header(alias="Idempotency-Key", min_length=8, max_length=255)]
RuntimeDep = Annotated[FiscalRuntime, Depends(get_fiscal_runtime)]


class FiscalDocumentRecoveryError(RuntimeError):
    def __init__(self, code: str, detail: str, *, status_code: int = 409) -> None:
        super().__init__(detail)
        self.code = code
        self.detail = detail
        self.status_code = status_code


def utc(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=UTC)


def get_item(
    session: Session, actor: ActorContext, item_id: uuid.UUID, permission: str
) -> BillingItem:
    item = session.scalar(
    select(BillingItem).where(
        BillingItem.id == item_id,
        BillingItem.organization_id == actor.organization_id,
        ~select(BillingItemRemoval.id).where(
            BillingItemRemoval.billing_item_id == BillingItem.id
        ).exists(),
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


CUSTOMER_ADDRESS_FIELDS = {
    "address_line": "logradouro",
    "address_number": "número",
    "district": "bairro",
    "postal_code": "CEP",
    "municipality_code": "código IBGE do município",
}


def canonical_company_contact(session: Session, company_id: uuid.UUID, kind: str) -> str | None:
    contact = session.scalar(
        select(ContactMethod)
        .where(
            ContactMethod.company_id == company_id,
            ContactMethod.kind == kind,
            ContactMethod.status == "active",
        )
        .order_by(
            ContactMethod.is_primary.desc(),
            ContactMethod.created_at.asc(),
            ContactMethod.id.asc(),
        )
        .limit(1)
    )
    if contact is None:
        return None
    value = (contact.normalized_value or contact.value).strip()
    return value or None


def validate_customer_address(customer: Company) -> None:
    values = {
        field: str(getattr(customer, field) or "").strip()
        for field in CUSTOMER_ADDRESS_FIELDS
    }
    has_address_data = any(values.values()) or any(
        str(getattr(customer, field) or "").strip()
        for field in ("address_complement", "city", "state_code")
    )
    if not has_address_data:
        return
    missing = [label for field, label in CUSTOMER_ADDRESS_FIELDS.items() if not values[field]]
    if missing:
        raise HTTPException(
            status_code=422,
            detail="Endereço do tomador incompleto: " + ", ".join(missing) + ".",
        )


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
    validate_customer_address(customer)
    missing: list[str] = []
    if not customer.tax_id or len(customer.tax_id) != 14:
        missing.append("CNPJ do cliente")
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
            "email": issuer.email,
            "phone": issuer.phone,
        },
        "customer": {
            "company_id": str(customer.id),
            "legal_name": customer.legal_name,
            "tax_id": customer.tax_id,
            "address_line": customer.address_line,
            "address_number": customer.address_number,
            "address_complement": customer.address_complement,
            "district": customer.district,
            "city": customer.city,
            "state_code": customer.state_code,
            "municipality_code": customer.municipality_code,
            "postal_code": customer.postal_code,
            "email": canonical_company_contact(session, customer.id, "email"),
            "phone": canonical_company_contact(session, customer.id, "phone"),
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
    item = session.get(BillingItem, issuance.billing_item_id)
    customer = session.get(Company, item.customer_company_id) if item else None
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
                filename=(
                    friendly_nfse_filename(
                        document_type=document.document_type,
                        nfse_number=issuance.nfse_number or str(issuance.dps_number),
                        trade_name=customer.trade_name,
                        legal_name=customer.legal_name,
                    )
                    if customer and document.document_type in {"nfse_xml", "danfse_pdf"}
                    else None
                ),
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


def fiscal_document_is_intact(document: FiscalDocument | None) -> bool:
    if (
        document is None
        or document.status != "available"
        or document.content_bytes is None
        or document.content_sha256 is None
        or document.size_bytes is None
    ):
        return False
    return (
        len(document.content_bytes) == document.size_bytes
        and hashlib.sha256(document.content_bytes).hexdigest() == document.content_sha256
    )


def persist_recovered_document(
    session: Session,
    issuance: FiscalIssuance,
    *,
    document_type: str,
    content_type: str,
    content: bytes,
) -> str:
    digest = hashlib.sha256(content).hexdigest()
    size = len(content)
    document = session.scalar(
        select(FiscalDocument)
        .where(
            FiscalDocument.issuance_id == issuance.id,
            FiscalDocument.document_type == document_type,
        )
        .with_for_update()
    )
    if document is None:
        document_id = uuid.uuid4()
        session.add(
            FiscalDocument(
                id=document_id,
                issuance_id=issuance.id,
                document_type=document_type,
                storage_key=f"db://fiscal_documents/{document_id}",
                content_type=content_type,
                content_sha256=digest,
                size_bytes=size,
                content_bytes=content,
                status="available",
            )
        )
        return "inserted"
    if document.status != "available":
        raise FiscalDocumentRecoveryError(
            "DOCUMENT_METADATA_DIVERGENCE",
            f"Documento {document_type} existente não está disponível para hidratação",
        )
    if document.content_bytes is not None:
        if not fiscal_document_is_intact(document):
            raise FiscalDocumentRecoveryError(
                "DOCUMENT_CONTENT_DIVERGENCE",
                f"Documento {document_type} persistido diverge de seu hash ou tamanho",
            )
        return "unchanged"
    if document.content_sha256 != digest or document.size_bytes != size:
        raise FiscalDocumentRecoveryError(
            "DOCUMENT_METADATA_DIVERGENCE",
            f"Conteúdo recuperado de {document_type} diverge do hash ou tamanho existente",
        )
    document.content_bytes = content
    return "hydrated"


def validate_recovered_nfse_identity(
    session: Session,
    issuance: FiscalIssuance,
    config: FiscalEstablishmentConfig,
    xml: bytes,
) -> None:
    metadata = extract_authorized_nfse_metadata(xml)
    establishment = session.get(FiscalEstablishment, config.establishment_id)
    entity = session.get(LegalEntity, establishment.legal_entity_id) if establishment else None
    snapshot_issuer = issuance.snapshot.get("issuer") or {}
    expected_tax_id = establishment.tax_id if establishment and establishment.tax_id else None
    if expected_tax_id is None and entity:
        expected_tax_id = entity.tax_id
    same_dps = metadata.dps_number.lstrip("0") == str(issuance.dps_number).lstrip("0")
    if (
        config.organization_id != issuance.organization_id
        or establishment is None
        or entity is None
        or entity.organization_id != issuance.organization_id
        or str(snapshot_issuer.get("establishment_id") or "") != str(config.establishment_id)
        or str(snapshot_issuer.get("tax_id") or "") != str(expected_tax_id or "")
        or metadata.issuer_tax_id != str(expected_tax_id or "")
        or metadata.access_key != issuance.access_key
        or metadata.nfse_number != issuance.nfse_number
        or not same_dps
    ):
        raise FiscalDocumentRecoveryError(
            "AUTHORIZED_DOCUMENT_IDENTITY_DIVERGENCE",
            "XML recuperado não corresponde à emissão fiscal autorizada",
        )


def record_document_recovery_failure(
    session: Session,
    actor: ActorContext,
    issuance_id: uuid.UUID,
    correlation_id: uuid.UUID,
    error: FiscalDocumentRecoveryError,
) -> None:
    persist_exception(
        session,
        actor,
        correlation_id,
        issuance_id=issuance_id,
        category="document",
        code=error.code,
        detail=error.detail,
    )
    record_change(
        session,
        actor=actor,
        correlation_id=correlation_id,
        action="fiscal.documents.recovery_failed",
        resource_type="fiscal_issuance",
        resource_id=issuance_id,
        before_state=None,
        after_state={"document_recovery": "failed", "error_code": error.code},
        event_type="fiscal.documents.recovery_failed.v1",
        event_payload={"issuance_id": str(issuance_id), "error_code": error.code},
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
        provider_documents = {document.document_type: document for document in result.documents}
        xml_document = provider_documents.get("nfse_xml")
        generated_documents: dict[str, ProviderDocument] = {}
        document_failed = False
        if xml_document is not None:
            try:
                metadata = extract_authorized_nfse_metadata(xml_document.content)
                issuance.nfse_number = metadata.nfse_number
                issuance.access_key = metadata.access_key
                generated_documents["nfse_xml"] = xml_document
                pdf = render_danfse_from_authorized_xml(xml_document.content)
                generated_documents["danfse_pdf"] = ProviderDocument(
                    "danfse_pdf", "application/pdf", pdf
                )
            except Exception:
                logger.exception(
                    "authorized_nfse_document_generation_failed",
                    extra={"issuance_id": str(issuance.id)},
                )
                document_failed = True
        else:
            document_failed = True
        issuance.nfse_number = issuance.nfse_number or result.nfse_number
        issuance.access_key = issuance.access_key or result.access_key
        issuance.error_category = issuance.error_code = issuance.error_message = None
        issuance.completed_at = now
        for document_type, content_type in (
            ("nfse_xml", "application/xml"),
            ("danfse_pdf", "application/pdf"),
        ):
            provider_document = generated_documents.get(document_type)
            if provider_document is not None:
                document_id = uuid.uuid4()
                content = provider_document.content
                session.add(
                    FiscalDocument(
                        id=document_id,
                        issuance_id=issuance.id,
                        document_type=document_type,
                        storage_key=f"db://fiscal_documents/{document_id}",
                        content_type=content_type,
                        content_sha256=hashlib.sha256(content).hexdigest(),
                        size_bytes=len(content),
                        content_bytes=content,
                        status="available",
                    )
                )
            else:
                document_failed = True
                session.add(
                    FiscalDocument(
                        issuance_id=issuance.id,
                        document_type=document_type,
                        content_type=content_type,
                        status="failed",
                        error_code=(
                            "AUTHORIZED_XML_UNAVAILABLE"
                            if document_type == "nfse_xml"
                            else "DANFSE_GENERATION_FAILED"
                        ),
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
    *,
    gateway: FiscalGateway | None = None,
) -> FiscalIssuanceResponse:
    config = session.get(FiscalEstablishmentConfig, issuance.establishment_config_id)
    if config is None:
        raise HTTPException(status_code=422, detail="Configuração fiscal não encontrada")
    issued_at = datetime.fromisoformat(str(issuance.snapshot["issued_at"]))
    # Snapshot antigo com regime incoerente nao pode ir para a SEFIN.
    # Erro de cadastro tem de virar 422 legivel, nunca 500.
    try:
        validate_fiscal_config(config)
        unsigned, identifier, _decision = build_dps(
            issuance.snapshot,
            series=issuance.series,
            number=issuance.dps_number,
            issued_at=issued_at,
        )
    except FiscalConfigurationError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    if identifier != issuance.dps_id:
        raise HTTPException(status_code=409, detail="Identidade DPS divergente; emissão bloqueada")
    try:
        gateway = gateway or runtime.gateway_for(session, config)
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


def issue_item_core(
    *,
    item: BillingItem,
    request: Request,
    session: Session,
    runtime: FiscalRuntime,
    actor: ActorContext,
) -> FiscalIssuanceResponse:
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
        return response
    if item.status != "ready":
        raise HTTPException(
            status_code=409,
            detail=item.blocking_reason or "Item não está pronto para emissão",
        )
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
    # Bloqueia configuracao fiscal incompleta/incoerente antes de montar XML,
    # antes de consumir numero de DPS e antes de qualquer POST na SEFIN.
    try:
        validate_fiscal_config(config)
    except FiscalConfigurationError as error:
        persist_exception(
            session,
            actor,
            request.state.correlation_id,
            issuance_id=None,
            category="validation",
            code="FISCAL_CONFIG_INVALID",
            detail=str(error),
        )
        session.commit()
        raise HTTPException(status_code=422, detail=str(error)) from error
    try:
        gateway = runtime.gateway_for(session, config)
    except (RuntimeError, ValueError) as error:
        persist_exception(
            session,
            actor,
            request.state.correlation_id,
            issuance_id=None,
            category="configuration",
            code="CERTIFICATE_INVALID",
            detail=str(error),
        )
        session.commit()
        raise HTTPException(status_code=422, detail=str(error)) from error
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
    number = reserve_dps_number(session, config)
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
        constraint = getattr(getattr(error, "orig", None), "diag", None)
        constraint_name = getattr(constraint, "constraint_name", None) or "desconhecida"
        logger.error(
            "fiscal_integrity_error constraint=%s billing_item_id=%s "
            "establishment_config_id=%s environment=%s series=%s dps_number=%s "
            "dps_id=%s correlation_id=%s",
            constraint_name,
            item.id,
            config.id,
            config.environment,
            config.series,
            number,
            identifier,
            request.state.correlation_id,
        )
        existing = session.scalar(
            select(FiscalIssuance).where(FiscalIssuance.billing_item_id == item.id)
        )
        if existing:
            return response_for(session, existing)
        if constraint_name in DPS_COLLISION_CONSTRAINTS:
            raise HTTPException(
                status_code=409,
                detail=(
                    "Colisão de numeração de DPS "
                    f"(constraint {constraint_name}, número {number}); "
                    "sequência resincronizada, tente emitir novamente."
                ),
            ) from error
        raise HTTPException(
            status_code=409,
            detail=f"Violação de integridade ao registrar a emissão (constraint {constraint_name})",
        ) from error
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
    return transmit_existing(session, runtime, actor, issuance, gateway=gateway)


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
    response = issue_item_core(
        item=item,
        request=request,
        session=session,
        runtime=runtime,
        actor=actor,
    )
    if record:
        record = session.merge(record)
        complete_command(record, response.model_dump(mode="json"), response_status=202)
        session.commit()
    return response


@router.post("/billing/items/issue-batch", response_model=FiscalBatchIssueResponse)
def issue_billing_items_batch(
    command: FiscalBatchIssueRequest,
    request: Request,
    session: SessionDep,
    runtime: RuntimeDep,
    idempotency_key: IdempotencyHeader,
    actor: Annotated[ActorContext, Depends(require_permission("fiscal:issue"))],
) -> FiscalBatchIssueResponse:
    item_ids = command.billing_item_ids
    if len(item_ids) != len(set(item_ids)):
        raise HTTPException(status_code=422, detail="A lista contém billing items duplicados")

    # Todo o lote é validado antes do primeiro efeito externo.
    items = [get_item(session, actor, item_id, "fiscal:issue") for item_id in item_ids]
    competences = {item.competence_month for item in items}
    issuers = {item.issuer_establishment_id for item in items}
    if len(competences) != 1:
        raise HTTPException(status_code=422, detail="Todos os itens devem ter a mesma competência")
    if None in issuers or len(issuers) != 1:
        raise HTTPException(status_code=422, detail="Todos os itens devem ter o mesmo emissor")

    completed_issuances: dict[uuid.UUID, FiscalIssuance] = {}
    for item in items:
        if item.status not in {"ready", "completed"}:
            raise HTTPException(
                status_code=409,
                detail=f"Item {item.id} não está pronto nem concluído",
            )
        if item.status == "completed":
            issuance = session.scalar(
                select(FiscalIssuance).where(FiscalIssuance.billing_item_id == item.id)
            )
            if issuance is None or issuance.status not in {"completed", "document_error"}:
                raise HTTPException(
                    status_code=409,
                    detail=f"Item concluído {item.id} não possui emissão autorizada",
                )
            completed_issuances[item.id] = issuance

    payload = {"billing_item_ids": [str(item_id) for item_id in item_ids]}
    record, cached = begin_command(
        session,
        actor=actor,
        command_name="fiscal.issue_billing_items_batch.v1",
        idempotency_key=idempotency_key,
        payload=payload,
        correlation_id=request.state.correlation_id,
    )
    if cached:
        return FiscalBatchIssueResponse.model_validate(cached)

    results: list[FiscalBatchItemResult] = []
    for item in items:
        if item.id in completed_issuances:
            results.append(
                FiscalBatchItemResult(
                    billing_item_id=item.id,
                    outcome="reused_completed",
                    issuance=response_for(session, completed_issuances[item.id]),
                )
            )
            continue
        try:
            response = issue_item_core(
                item=item,
                request=request,
                session=session,
                runtime=runtime,
                actor=actor,
            )
            outcome = (
                "completed"
                if response.status in {"completed", "document_error"}
                else "failed"
            )
            results.append(
                FiscalBatchItemResult(
                    billing_item_id=item.id,
                    outcome=outcome,
                    issuance=response,
                    error_code=response.error_code if outcome == "failed" else None,
                    error_message=response.error_message if outcome == "failed" else None,
                )
            )
        except HTTPException as error:
            session.rollback()
            results.append(
                FiscalBatchItemResult(
                    billing_item_id=item.id,
                    outcome="failed",
                    error_code=f"HTTP_{error.status_code}",
                    error_message=str(error.detail),
                )
            )
        except Exception:
            session.rollback()
            logger.exception("fiscal_batch_item_failed billing_item_id=%s", item.id)
            results.append(
                FiscalBatchItemResult(
                    billing_item_id=item.id,
                    outcome="failed",
                    error_code="INTERNAL_ERROR",
                    error_message="Falha interna ao emitir o item",
                )
            )

    response = FiscalBatchIssueResponse(
        competence_month=next(iter(competences)).strftime("%Y-%m"),
        issuer_establishment_id=next(iter(issuers)),
        results=results,
    )
    if record:
        record = session.merge(record)
        complete_command(record, response.model_dump(mode="json"), response_status=200)
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


@router.post(
    "/fiscal/issuances/{issuance_id}/documents/reconcile",
    response_model=FiscalIssuanceResponse,
)
def reconcile_issuance_documents(
    issuance_id: uuid.UUID,
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
    get_item(session, actor, issuance.billing_item_id, "fiscal:reconcile")
    if issuance.status not in {"completed", "document_error"}:
        raise HTTPException(
            status_code=409,
            detail="Recuperação documental exige NFS-e previamente autorizada",
        )
    if not issuance.access_key or not issuance.nfse_number:
        raise HTTPException(status_code=409, detail="Emissão autorizada sem identidade da NFS-e")
    config = session.get(FiscalEstablishmentConfig, issuance.establishment_config_id)
    if config is None or config.organization_id != actor.organization_id:
        raise HTTPException(status_code=422, detail="Configuração fiscal indisponível")
    record, cached = begin_command(
        session,
        actor=actor,
        command_name="fiscal.reconcile_issuance_documents.v1",
        idempotency_key=idempotency_key,
        payload={"issuance_id": str(issuance_id)},
        correlation_id=request.state.correlation_id,
    )
    if cached:
        return FiscalIssuanceResponse.model_validate(cached)

    documents = {
        document.document_type: document
        for document in session.scalars(
            select(FiscalDocument).where(FiscalDocument.issuance_id == issuance.id)
        )
    }
    actions = {"nfse_xml": "unchanged", "danfse_pdf": "unchanged"}
    try:
        if not all(
            fiscal_document_is_intact(documents.get(document_type))
            for document_type in ("nfse_xml", "danfse_pdf")
        ):
            try:
                gateway = runtime.gateway_for(session, config)
            except (RuntimeError, ValueError) as error:
                raise FiscalDocumentRecoveryError(
                    "DOCUMENT_RECOVERY_CONFIGURATION_ERROR",
                    "Configuração segura para consulta documental indisponível",
                    status_code=503,
                ) from error
            result = gateway.fetch_authorized_nfse(
                query_base_url=config.query_base_url,
                access_key=issuance.access_key,
                dps_id=issuance.dps_id,
            )
            xml_document = next(
                (
                    document
                    for document in result.documents
                    if document.document_type == "nfse_xml"
                ),
                None,
            )
            if result.status != "completed" or xml_document is None:
                raise FiscalDocumentRecoveryError(
                    result.error_code or "AUTHORIZED_DOCUMENT_UNAVAILABLE",
                    "SEFIN não retornou o XML autorizado para recuperação documental",
                    status_code=503 if result.status == "external_unavailable" else 409,
                )
            validate_recovered_nfse_identity(session, issuance, config, xml_document.content)
            pdf = render_danfse_from_authorized_xml(xml_document.content)
            actions["nfse_xml"] = persist_recovered_document(
                session,
                issuance,
                document_type="nfse_xml",
                content_type="application/xml",
                content=xml_document.content,
            )
            actions["danfse_pdf"] = persist_recovered_document(
                session,
                issuance,
                document_type="danfse_pdf",
                content_type="application/pdf",
                content=pdf,
            )
            session.flush()
    except FiscalDocumentRecoveryError as error:
        session.rollback()
        record_document_recovery_failure(
            session,
            actor,
            issuance_id,
            request.state.correlation_id,
            error,
        )
        session.commit()
        raise HTTPException(status_code=error.status_code, detail=error.detail) from error
    except Exception as error:
        logger.exception(
            "fiscal_document_recovery_failed",
            extra={"issuance_id": str(issuance_id)},
        )
        session.rollback()
        safe_error = FiscalDocumentRecoveryError(
            "DOCUMENT_RECOVERY_FAILED",
            "Não foi possível validar e persistir os documentos autorizados",
            status_code=502,
        )
        record_document_recovery_failure(
            session,
            actor,
            issuance_id,
            request.state.correlation_id,
            safe_error,
        )
        session.commit()
        raise HTTPException(
            status_code=safe_error.status_code, detail=safe_error.detail
        ) from error

    record_change(
        session,
        actor=actor,
        correlation_id=request.state.correlation_id,
        action="fiscal.documents.reconciled",
        resource_type="fiscal_issuance",
        resource_id=issuance.id,
        before_state={"status": issuance.status},
        after_state={"status": issuance.status, "documents": actions},
        event_type="fiscal.documents.reconciled.v1",
        event_payload={
            "issuance_id": str(issuance.id),
            "status": issuance.status,
            "documents": actions,
        },
    )
    response = response_for(session, issuance)
    if record:
        complete_command(record, response.model_dump(mode="json"), response_status=200)
    session.commit()
    return response


@router.post("/fiscal/configs/{config_id}/sequence/sync")
def sync_fiscal_sequence(
    config_id: uuid.UUID,
    request: Request,
    session: SessionDep,
    idempotency_key: IdempotencyHeader,
    actor: Annotated[ActorContext, Depends(require_permission("fiscal:reconcile"))],
) -> dict[str, Any]:
    config = session.scalar(
        select(FiscalEstablishmentConfig)
        .join(
            FiscalEstablishment,
            FiscalEstablishment.id == FiscalEstablishmentConfig.establishment_id,
        )
        .where(
            FiscalEstablishmentConfig.id == config_id,
            FiscalEstablishment.organization_id == actor.organization_id,
        )
    )
    if config is None:
        raise HTTPException(status_code=404, detail="Configuração fiscal não encontrada")
    record, cached = begin_command(
        session,
        actor=actor,
        command_name="fiscal.sync_sequence.v1",
        idempotency_key=idempotency_key,
        payload={"config_id": str(config_id)},
        correlation_id=request.state.correlation_id,
    )
    if cached:
        return cached
    previous, updated, historic = sync_dps_sequence(session, config_id)
    logger.info(
        "fiscal_sequence_sync config_id=%s environment=%s series=%s "
        "previous=%s updated=%s highest=%s correlation_id=%s",
        config_id,
        config.environment,
        config.series,
        previous,
        updated,
        historic,
        request.state.correlation_id,
    )
    record_change(
        session,
        actor=actor,
        correlation_id=request.state.correlation_id,
        action="fiscal.sequence.sync",
        resource_type="fiscal_establishment_config",
        resource_id=config_id,
        before_state={"next_dps_number": previous},
        after_state={"next_dps_number": updated},
        event_type="fiscal.sequence.synced",
        event_payload={
            "config_id": str(config_id),
            "environment": config.environment,
            "series": config.series,
            "previous_next_dps_number": previous,
            "next_dps_number": updated,
            "highest_dps_number": historic,
        },
    )
    response = {
        "config_id": str(config_id),
        "environment": config.environment,
        "series": config.series,
        "previous_next_dps_number": previous,
        "next_dps_number": updated,
        "highest_dps_number": historic,
        "changed": updated != previous,
    }
    if record:
        complete_command(record, response, response_status=200)
    session.commit()
    return response


@router.get("/fiscal/documents/{document_id}/content")
def fiscal_document_content(
    document_id: uuid.UUID,
    session: SessionDep,
    runtime: RuntimeDep,
    actor: Annotated[ActorContext, Depends(require_permission("fiscal:read"))],
) -> Response:
    document = session.scalar(
        select(FiscalDocument)
        .join(FiscalIssuance, FiscalIssuance.id == FiscalDocument.issuance_id)
        .where(
            FiscalDocument.id == document_id,
            FiscalIssuance.organization_id == actor.organization_id,
        )
    )
    if document is None or document.status != "available":
        raise HTTPException(status_code=404, detail="Documento fiscal indisponível")
    issuance = session.get(FiscalIssuance, document.issuance_id)
    assert issuance is not None
    get_item(session, actor, issuance.billing_item_id, "fiscal:read")
    item = session.get(BillingItem, issuance.billing_item_id)
    customer = session.get(Company, item.customer_company_id) if item else None
    if customer is None or document.document_type not in {"nfse_xml", "danfse_pdf"}:
        raise HTTPException(status_code=404, detail="Documento fiscal sem cliente vinculado")
    filename = friendly_nfse_filename(
        document_type=document.document_type,
        nfse_number=issuance.nfse_number or str(issuance.dps_number),
        trade_name=customer.trade_name,
        legal_name=customer.legal_name,
    )
    if document.content_bytes is not None:
        return Response(
            content=document.content_bytes,
            media_type=document.content_type,
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
    if document.storage_key:
        path = runtime.document_store.path_for(document.storage_key)
        if path.is_file():
            return FileResponse(path, media_type=document.content_type, filename=filename)
    raise HTTPException(status_code=404, detail="Documento fiscal indisponível no storage")


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
        installment_total=command.installment_total,
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
        installment_number=command.installment_number,
        owner_actor_id=actor.id,
        created_by_actor_id=actor.id,
    )
    session.add(occurrence)
    session.flush()
    blockers: list[dict[str, str]] = []
    missing_customer_fields = missing_customer_fiscal_fields(company)
    if missing_customer_fields:
        labels = ", ".join(
            FISCAL_FIELD_LABELS[field] for field in missing_customer_fields
        )
        blockers.append(
            {
                "code": "CUSTOMER_FISCAL_DATA_INCOMPLETE",
                "reason": f"Cadastro do cliente incompleto para fins fiscais: {labels}.",
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
        "billing_reference": (
            {
                "type": "installment",
                "position": command.installment_number,
                "total": command.installment_total,
            }
            if command.installment_total is not None
            else {"type": "single", "position": None, "total": None}
        ),
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
