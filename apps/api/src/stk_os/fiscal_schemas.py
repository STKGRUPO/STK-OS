from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class FiscalDocumentResponse(BaseModel):
    id: uuid.UUID
    document_type: str
    content_type: str
    content_sha256: str | None
    size_bytes: int | None
    status: str
    download_path: str | None
    filename: str | None


class FiscalAttemptResponse(BaseModel):
    attempt_number: int
    operation: str
    outcome: str
    external_status: int | None
    error_category: str | None
    error_code: str | None
    sanitized_detail: str | None
    started_at: datetime
    completed_at: datetime | None


class FiscalIssuanceResponse(BaseModel):
    id: uuid.UUID
    billing_item_id: uuid.UUID
    status: str
    environment: str
    issuer_establishment_id: uuid.UUID
    issuer_name: str
    series: int
    dps_number: int
    dps_id: str
    nfse_number: str | None
    access_key: str | None
    provider_reference: str | None
    error_category: str | None
    error_code: str | None
    error_message: str | None
    requested_at: datetime
    last_reconciled_at: datetime | None
    completed_at: datetime | None
    documents: list[FiscalDocumentResponse]
    attempts: list[FiscalAttemptResponse]


class FiscalReconcileRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    resend_if_confirmed_not_found: bool = False


class OneTimeBillingCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    business_unit_id: uuid.UUID
    customer_company_id: uuid.UUID
    product_service_id: uuid.UUID | None = None
    service_name: str = Field(min_length=2, max_length=255)
    description: str = Field(min_length=2, max_length=2000)
    reference: str = Field(min_length=1, max_length=255)
    service_date: date
    amount: Decimal = Field(gt=0, max_digits=18, decimal_places=2)
    currency: Literal["BRL"] = "BRL"
    issuer_establishment_id: uuid.UUID
    installment_total: int | None = Field(default=None, ge=2, le=120)
    installment_number: int | None = Field(default=None, ge=1)

    @model_validator(mode="after")
    def validate_installment(self) -> OneTimeBillingCreate:
        if (self.installment_total is None) != (self.installment_number is None):
            raise ValueError("Parcela exige número e total")
        if (
            self.installment_total is not None
            and self.installment_number > self.installment_total
        ):
            raise ValueError("Número da parcela não pode superar o total")
        return self


class OneTimeBillingResponse(BaseModel):
    client_service_id: uuid.UUID
    service_occurrence_id: uuid.UUID
    billing_item_id: uuid.UUID
    billing_status: str
    fiscal_issuance: FiscalIssuanceResponse | None = None


class FiscalBatchIssueRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    billing_item_ids: list[uuid.UUID] = Field(min_length=1, max_length=100)


class FiscalBatchItemResult(BaseModel):
    billing_item_id: uuid.UUID
    outcome: Literal["completed", "reused_completed", "failed"]
    issuance: FiscalIssuanceResponse | None = None
    error_code: str | None = None
    error_message: str | None = None


class FiscalBatchIssueResponse(BaseModel):
    competence_month: str
    issuer_establishment_id: uuid.UUID
    results: list[FiscalBatchItemResult]
