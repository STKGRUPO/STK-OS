from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

Recurrence = Literal["monthly", "quarterly", "semiannual", "annual", "custom"]
OccurrenceStatus = Literal[
    "planned", "preparing", "scheduled", "in_progress", "completed", "to_bill", "billed", "closed"
]


class ClientServiceCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    business_unit_id: uuid.UUID
    customer_company_id: uuid.UUID
    product_service_id: uuid.UUID | None = None
    contract_id: uuid.UUID | None = None
    name: str = Field(min_length=2, max_length=255)
    description: str | None = Field(default=None, max_length=4000)
    service_type: Literal["recurring", "one_time"]
    recurrence: Recurrence | None = None
    interval_months: int | None = Field(default=None, ge=1, le=120)
    installment_total: int | None = Field(default=None, ge=2, le=120)
    start_date: date
    owner_actor_id: uuid.UUID
    amount: Decimal = Field(ge=0, max_digits=18, decimal_places=2)
    currency: str = Field(default="BRL", pattern=r"^[A-Z]{3}$")
    operational_lead_days: int = Field(default=0, ge=0, le=365)
    reminder_lead_days: int = Field(default=0, ge=0, le=365)

    @model_validator(mode="after")
    def recurrence_matches_type(self) -> ClientServiceCreate:
        if self.service_type == "one_time" and (self.recurrence or self.interval_months):
            raise ValueError("Serviço pontual não possui recorrência")
        if self.installment_total is not None and self.service_type != "one_time":
            raise ValueError("Parcelamento é permitido somente para serviço avulso")
        if self.service_type == "recurring" and self.recurrence is None:
            raise ValueError("Serviço recorrente exige periodicidade")
        if self.recurrence == "custom" and self.interval_months is None:
            raise ValueError("Intervalo configurável exige quantidade de meses")
        return self


class ClientServiceUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=2, max_length=255)
    description: str | None = Field(default=None, max_length=4000)
    contract_id: uuid.UUID | None = None
    recurrence: Recurrence | None = None
    interval_months: int | None = Field(default=None, ge=1, le=120)
    installment_total: int | None = Field(default=None, ge=2, le=120)
    owner_actor_id: uuid.UUID | None = None
    amount: Decimal | None = Field(default=None, ge=0, max_digits=18, decimal_places=2)
    operational_lead_days: int | None = Field(default=None, ge=0, le=365)
    reminder_lead_days: int | None = Field(default=None, ge=0, le=365)
    status: Literal["active", "inactive"] | None = None


class OccurrenceGenerate(BaseModel):
    through: date | None = None
    scheduled_for: date | None = None
    installment_number: int | None = Field(default=None, ge=1)

    @model_validator(mode="after")
    def has_generation_target(self) -> OccurrenceGenerate:
        if self.through is None and self.scheduled_for is None:
            raise ValueError("Informe through ou scheduled_for")
        return self


class OccurrenceUpdate(BaseModel):
    status: OccurrenceStatus


class ClientServiceOccurrenceResponse(BaseModel):
    id: uuid.UUID
    scheduled_for: date
    due_on: date
    status: str
    billing_status: str
    billing_item_id: uuid.UUID | None
    installment_number: int | None
    created_at: datetime


class ClientServiceResponse(BaseModel):
    id: uuid.UUID
    organization_id: uuid.UUID
    business_unit_id: uuid.UUID
    customer_company_id: uuid.UUID
    customer_name: str
    product_service_id: uuid.UUID | None
    contract_id: uuid.UUID | None
    contract_number: str | None
    name: str
    description: str | None
    service_type: str
    recurrence: str | None
    interval_months: int | None
    installment_total: int | None
    start_date: date
    next_occurrence_on: date | None
    owner_actor_id: uuid.UUID
    owner_name: str
    amount: Decimal
    currency: str
    operational_lead_days: int
    reminder_lead_days: int
    status: str
    occurrences: list[ClientServiceOccurrenceResponse]
    created_at: datetime
    updated_at: datetime
