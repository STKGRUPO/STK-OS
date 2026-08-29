from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class BillingGenerate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    business_unit_id: uuid.UUID
    competence_month: str = Field(pattern=r"^\d{4}-(0[1-9]|1[0-2])$")
    run_type: Literal["manual", "scheduled"] = "manual"
    causation_id: uuid.UUID | None = None

    @field_validator("competence_month")
    @classmethod
    def competence_year_must_be_a_calendar_year(cls, value: str) -> str:
        if value.startswith("0000-"):
            raise ValueError("Competência deve usar um ano civil válido")
        return value


class BillingRunContractResponse(BaseModel):
    contract_id: uuid.UUID
    contract_number: str
    customer_name: str
    billing_item_id: uuid.UUID | None
    outcome: str
    reason_code: str | None
    reason_detail: str | None


class BillingRunResponse(BaseModel):
    id: uuid.UUID
    organization_id: uuid.UUID
    business_unit_id: uuid.UUID
    business_unit_name: str
    competence_month: str
    run_type: str
    status: str
    operational_timezone: str
    rule_version: str
    actor_id: uuid.UUID
    correlation_id: uuid.UUID
    causation_id: uuid.UUID | None
    metrics: dict[str, Any]
    started_at: datetime
    completed_at: datetime | None
    contracts: list[BillingRunContractResponse] = []


class BillingItemSummary(BaseModel):
    id: uuid.UUID
    created_by_run_id: uuid.UUID | None
    source_type: str
    client_service_id: uuid.UUID | None
    service_occurrence_id: uuid.UUID | None
    contract_id: uuid.UUID | None
    contract_number: str
    contract_version_id: uuid.UUID | None
    contract_version_number: int | None
    competence_month: str
    business_unit_id: uuid.UUID
    business_unit_name: str
    customer_company_id: uuid.UUID
    customer_name: str
    issuer_establishment_id: uuid.UUID | None
    issuer_name: str | None
    currency: str | None
    gross_amount: Decimal | None
    status: str
    blocking_code: str | None
    blocking_reason: str | None
    snapshot_sha256: str
    correlation_id: uuid.UUID
    causation_id: uuid.UUID | None
    created_at: datetime
    updated_at: datetime


class BillingHistoryEvent(BaseModel):
    kind: Literal["audit", "outbox"]
    name: str
    occurred_at: datetime
    correlation_id: uuid.UUID
    status: str | None = None


class BillingItemDetail(BillingItemSummary):
    snapshot: dict[str, Any]
    history: list[BillingHistoryEvent]


class BillingExceptionResponse(BaseModel):
    billing_item_id: uuid.UUID
    contract_id: uuid.UUID | None = None
    contract_number: str
    competence_month: str
    customer_name: str
    # ↓ novos campos
    business_unit_id: uuid.UUID
    business_unit_name: str
    customer_company_id: uuid.UUID | None = None
    status: str = "blocked"
    code: str
    reason: str
    created_at: datetime


class BillingSummaryResponse(BaseModel):
    competence_month: str
    predicted_gross_amount: Decimal
    eligible_contracts: int
    blocked_contracts: int
    blocked_gross_amount: Decimal
    ready_contracts: int
    by_business_unit: list[dict[str, Any]]
