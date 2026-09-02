from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ContractCreate(StrictModel):
    business_unit_id: uuid.UUID
    customer_company_id: uuid.UUID
    internal_number: str = Field(min_length=1, max_length=100)
    signed_on: date | None = None
    start_date: date
    contract_type: Literal["recurring_service", "project", "retainer", "other"]
    owner_actor_id: uuid.UUID | None = None
    controlled_notes: str | None = Field(default=None, max_length=2000)


class VersionServiceInput(StrictModel):
    product_service_id: uuid.UUID | None = None
    contractual_description: str = Field(min_length=1, max_length=1000)
    quantity: Decimal = Field(default=Decimal("1"), gt=0, max_digits=14, decimal_places=3)
    unit_amount: Decimal | None = Field(default=None, ge=0, max_digits=18, decimal_places=2)
    is_active: bool = True


class VersionContactInput(StrictModel):
    contact_method_id: uuid.UUID
    recipient_role: Literal["primary", "cc"]
    purpose: str = Field(default="billing", min_length=1, max_length=100)
    preferred_channel: Literal["email", "phone", "whatsapp"] = "email"


class ContractVersionCreate(StrictModel):
    effective_from: date
    issuer_establishment_id: uuid.UUID
    currency: str = Field(default="BRL", pattern=r"^[A-Z]{3}$")
    billing_frequency: Literal["monthly", "annual", "one_time", "other"]
    pricing_model: Literal["monthly", "annual", "project", "per_service", "other"]
    amount: Decimal = Field(ge=0, max_digits=18, decimal_places=2)
    billing_installments: int | None = Field(default=None, gt=0, le=120)
    billing_anchor_competence: date | None = None
    billing_anchor_position: int | None = Field(default=None, ge=1)
    billing_cycle_total: int | None = Field(default=None, ge=1)
    billing_day: int | None = Field(default=None, ge=1, le=31)
    payment_terms_days: int | None = Field(default=None, ge=0, le=365)
    invoice_description: str | None = Field(default=None, max_length=2000)
    adjustment_reference: str | None = Field(default=None, max_length=100)
    adjustment_frequency: Literal["annual", "custom", "none"] | None = None
    adjustment_base_date: date | None = None
    adjustment_applied_percentage: Decimal | None = Field(
        default=None, max_digits=9, decimal_places=6
    )
    adjustment_source: Literal["manual", "index", "not_applied"] | None = None
    change_type: Literal[
        "initial",
        "service_change",
        "value_change",
        "issuer_change",
        "conditions_change",
        "adjustment",
        "renewal",
    ]
    change_reason: str = Field(min_length=3, max_length=1000)
    source: Literal["ui", "api", "import", "system"] = "api"
    services: list[VersionServiceInput] = Field(min_length=1, max_length=100)
    financial_contacts: list[VersionContactInput] = Field(min_length=1, max_length=50)

    @model_validator(mode="after")
    def validate_snapshot(self) -> ContractVersionCreate:
        cycle = (
            self.billing_anchor_competence,
            self.billing_anchor_position,
            self.billing_cycle_total,
        )
        if any(value is not None for value in cycle) and not all(
            value is not None for value in cycle
        ):
            raise ValueError("Âncora do ciclo exige competência, posição e total")
        if self.billing_anchor_competence is not None:
            if self.billing_frequency != "monthly":
                raise ValueError("Âncora do ciclo é permitida somente para cobrança mensal")
            if self.billing_anchor_competence.day != 1:
                raise ValueError("Competência-âncora deve ser o primeiro dia do mês")
            if self.billing_anchor_position > self.billing_cycle_total:
                raise ValueError("Posição inicial não pode superar o total do ciclo")
        if not any(item.is_active for item in self.services):
            raise ValueError("A versão deve possuir ao menos um serviço ativo")
        primary = [
            item
            for item in self.financial_contacts
            if item.recipient_role == "primary" and item.purpose == "billing"
        ]
        if len(primary) != 1:
            raise ValueError("A versão deve possuir exatamente um contato financeiro principal")
        if self.pricing_model == "annual" and self.billing_frequency == "monthly":
            if self.billing_installments is None:
                raise ValueError("Contrato anual cobrado mensalmente exige número de parcelas")
        if self.change_type == "adjustment" and self.adjustment_applied_percentage is None:
            raise ValueError("Reajuste efetivado exige percentual aplicado")
        return self


class OperationalEventCreate(StrictModel):
    effective_on: date
    reason: str = Field(min_length=3, max_length=1000)
    source: Literal["ui", "api", "import", "system"] = "api"


class ContractReferenceItem(BaseModel):
    id: uuid.UUID
    name: str
    business_unit_id: uuid.UUID | None = None
    company_id: uuid.UUID | None = None
    person_id: uuid.UUID | None = None
    kind: str | None = None
    value: str | None = None
    primary_establishment_id: uuid.UUID | None = None


class ContractReferenceData(BaseModel):
    business_units: list[ContractReferenceItem]
    companies: list[ContractReferenceItem]
    fiscal_establishments: list[ContractReferenceItem]
    products_services: list[ContractReferenceItem]
    contact_methods: list[ContractReferenceItem]


class VersionServiceResponse(BaseModel):
    id: uuid.UUID
    product_service_id: uuid.UUID | None
    product_name: str | None
    contractual_description: str
    quantity: Decimal
    unit_amount: Decimal | None
    is_active: bool


class VersionContactResponse(BaseModel):
    id: uuid.UUID
    contact_method_id: uuid.UUID
    contact_name: str
    contact_value: str
    recipient_role: str
    purpose: str
    preferred_channel: str


class ContractVersionResponse(BaseModel):
    id: uuid.UUID
    contract_id: uuid.UUID
    version_number: int
    effective_from: date
    effective_until: date | None
    temporal_status: Literal["historical", "current", "scheduled"]
    issuer_establishment_id: uuid.UUID
    issuer_name: str
    currency: str
    billing_frequency: str
    pricing_model: str
    amount: Decimal
    billing_installments: int | None
    billing_anchor_competence: date | None
    billing_anchor_position: int | None
    billing_cycle_total: int | None
    billing_day: int | None
    payment_terms_days: int | None
    invoice_description: str | None
    adjustment_reference: str | None
    adjustment_frequency: str | None
    adjustment_base_date: date | None
    adjustment_applied_percentage: Decimal | None
    adjustment_source: str | None
    change_type: str
    change_reason: str
    source: str
    configuration_sha256: str
    services: list[VersionServiceResponse]
    financial_contacts: list[VersionContactResponse]
    created_at: datetime


class ContractEventResponse(BaseModel):
    id: uuid.UUID
    event_type: str
    effective_on: date
    reason: str
    source: str
    related_version_id: uuid.UUID | None
    actor_id: uuid.UUID
    correlation_id: uuid.UUID
    created_at: datetime


class ContractSummary(BaseModel):
    id: uuid.UUID
    business_unit_id: uuid.UUID
    business_unit_name: str
    customer_company_id: uuid.UUID
    customer_name: str
    internal_number: str
    administrative_status: str
    signed_on: date | None
    start_date: date
    contract_type: str
    owner_actor_id: uuid.UUID
    current_operational_state: Literal["active", "suspended", "terminated"]
    current_version_number: int | None
    current_issuer_establishment_id: uuid.UUID | None
    current_issuer_name: str | None
    current_amount: Decimal | None
    current_currency: str | None
    scheduled_versions: int
    created_at: datetime
    updated_at: datetime


class ContractDetail(ContractSummary):
    controlled_notes: str | None
    versions: list[ContractVersionResponse]
    operational_events: list[ContractEventResponse]


class ContractConfiguration(BaseModel):
    contract: ContractSummary
    on_date: date
    operational_state: Literal["active", "suspended", "terminated"]
    version: ContractVersionResponse
