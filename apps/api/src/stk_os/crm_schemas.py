from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field, model_validator

ContactKind = Literal["email", "phone", "whatsapp"]
OpportunityStatus = Literal["open", "won", "lost"]


class ContactMethodInput(BaseModel):
    kind: ContactKind
    value: str = Field(min_length=3, max_length=320)
    label: str | None = Field(default=None, max_length=100)
    is_primary: bool = False


class ContactMethodResponse(ContactMethodInput):
    id: uuid.UUID
    normalized_value: str
    status: str


class PersonCreate(BaseModel):
    full_name: str = Field(min_length=2, max_length=255)
    tax_id: str | None = Field(default=None, min_length=11, max_length=14)
    city: str | None = Field(default=None, max_length=255)
    state_code: str | None = Field(default=None, min_length=2, max_length=2)
    notes: str | None = Field(default=None, max_length=4000)
    business_unit_ids: list[uuid.UUID] = Field(min_length=1, max_length=3)
    lead_source_id: uuid.UUID | None = None
    contacts: list[ContactMethodInput] = Field(default_factory=list, max_length=10)


class PersonUpdate(BaseModel):
    full_name: str | None = Field(default=None, min_length=2, max_length=255)
    city: str | None = Field(default=None, max_length=255)
    state_code: str | None = Field(default=None, min_length=2, max_length=2)
    notes: str | None = Field(default=None, max_length=4000)
    status: Literal["active", "inactive"] | None = None


class PersonSummary(BaseModel):
    id: uuid.UUID
    full_name: str
    tax_id: str | None
    city: str | None
    state_code: str | None
    status: str
    business_unit_ids: list[uuid.UUID]
    contacts: list[ContactMethodResponse]
    created_at: datetime
    updated_at: datetime


class CompanyCreate(BaseModel):
    legal_name: str = Field(min_length=2, max_length=255)
    trade_name: str | None = Field(default=None, max_length=255)
    tax_id: str | None = Field(default=None, min_length=14, max_length=18)
    address_line: str | None = Field(default=None, max_length=1000)
    city: str | None = Field(default=None, max_length=255)
    state_code: str | None = Field(default=None, min_length=2, max_length=2)
    site: str | None = Field(default=None, max_length=500)
    notes: str | None = Field(default=None, max_length=4000)
    business_unit_ids: list[uuid.UUID] = Field(min_length=1, max_length=3)
    lead_source_id: uuid.UUID | None = None
    contacts: list[ContactMethodInput] = Field(default_factory=list, max_length=10)


class CompanyUpdate(BaseModel):
    legal_name: str | None = Field(default=None, min_length=2, max_length=255)
    trade_name: str | None = Field(default=None, max_length=255)
    address_line: str | None = Field(default=None, max_length=1000)
    city: str | None = Field(default=None, max_length=255)
    state_code: str | None = Field(default=None, min_length=2, max_length=2)
    site: str | None = Field(default=None, max_length=500)
    notes: str | None = Field(default=None, max_length=4000)
    status: Literal["active", "inactive"] | None = None


class CompanySummary(BaseModel):
    id: uuid.UUID
    legal_name: str
    trade_name: str | None
    tax_id: str | None
    city: str | None
    state_code: str | None
    site: str | None
    status: str
    business_unit_ids: list[uuid.UUID]
    contacts: list[ContactMethodResponse]
    created_at: datetime
    updated_at: datetime


class PersonCompanyLinkCreate(BaseModel):
    person_id: uuid.UUID
    company_id: uuid.UUID
    role: str = Field(min_length=2, max_length=100)
    is_primary: bool = False


class PersonCompanyLinkResponse(PersonCompanyLinkCreate):
    id: uuid.UUID
    status: str


class CatalogItem(BaseModel):
    id: uuid.UUID
    code: str
    name: str
    business_unit_id: uuid.UUID | None = None
    category: str | None = None


class PipelineStageItem(BaseModel):
    id: uuid.UUID
    code: str
    name: str
    position: int
    sla_days: int | None


class PipelineItem(BaseModel):
    id: uuid.UUID
    business_unit_id: uuid.UUID
    code: str
    name: str
    kind: str
    stages: list[PipelineStageItem]


class ReferenceDataResponse(BaseModel):
    business_units: list[CatalogItem]
    lead_sources: list[CatalogItem]
    products_services: list[CatalogItem]
    loss_reasons: list[CatalogItem]
    pipelines: list[PipelineItem]


class OpportunityCreate(BaseModel):
    business_unit_id: uuid.UUID
    pipeline_id: uuid.UUID
    stage_id: uuid.UUID
    company_id: uuid.UUID | None = None
    person_ids: list[uuid.UUID] = Field(default_factory=list, max_length=20)
    title: str = Field(min_length=2, max_length=255)
    value: Decimal | None = Field(default=None, ge=0, decimal_places=2)
    currency: str = Field(default="BRL", min_length=3, max_length=3)
    lead_source_id: uuid.UUID
    product_service_ids: list[uuid.UUID] = Field(default_factory=list, max_length=20)
    expected_close_date: date | None = None
    notes: str | None = Field(default=None, max_length=4000)
    next_action_title: str = Field(min_length=2, max_length=255)
    next_action_due_at: datetime

    @model_validator(mode="after")
    def requires_participant(self) -> OpportunityCreate:
        if self.company_id is None and not self.person_ids:
            raise ValueError("A oportunidade exige ao menos uma pessoa ou empresa")
        return self


class OpportunityStageMove(BaseModel):
    stage_id: uuid.UUID
    note: str | None = Field(default=None, max_length=1000)
    source: Literal["api", "ui", "import", "system"] = "api"


class OpportunityStatusUpdate(BaseModel):
    status: OpportunityStatus
    loss_reason_id: uuid.UUID | None = None
    note: str | None = Field(default=None, max_length=1000)

    @model_validator(mode="after")
    def lost_requires_reason(self) -> OpportunityStatusUpdate:
        if self.status == "lost" and self.loss_reason_id is None:
            raise ValueError("Negócio perdido exige motivo")
        if self.status != "lost" and self.loss_reason_id is not None:
            raise ValueError("Motivo de perda só se aplica a negócio perdido")
        return self


class TaskCreate(BaseModel):
    business_unit_id: uuid.UUID
    opportunity_id: uuid.UUID | None = None
    person_id: uuid.UUID | None = None
    company_id: uuid.UUID | None = None
    title: str = Field(min_length=2, max_length=255)
    due_at: datetime
    priority: Literal["low", "medium", "high"] = "medium"
    notes: str | None = Field(default=None, max_length=4000)

    @model_validator(mode="after")
    def requires_reference(self) -> TaskCreate:
        if not any((self.opportunity_id, self.person_id, self.company_id)):
            raise ValueError("A tarefa exige referência a oportunidade, pessoa ou empresa")
        return self


class TaskResponse(BaseModel):
    id: uuid.UUID
    business_unit_id: uuid.UUID
    opportunity_id: uuid.UUID | None
    person_id: uuid.UUID | None
    company_id: uuid.UUID | None
    title: str
    due_at: datetime
    priority: str
    status: str
    completed_at: datetime | None


class ActivityCreate(BaseModel):
    business_unit_id: uuid.UUID
    opportunity_id: uuid.UUID | None = None
    person_id: uuid.UUID | None = None
    company_id: uuid.UUID | None = None
    activity_type: Literal[
        "whatsapp",
        "email",
        "call",
        "meeting",
        "proposal",
        "follow_up",
        "service",
        "note",
        "automatic_interaction",
        "ai_action",
    ]
    occurred_at: datetime
    summary: str = Field(min_length=2, max_length=4000)
    origin: str = Field(min_length=1, max_length=100)
    next_step: str | None = Field(default=None, max_length=1000)
    performed_by: Literal["human", "agent", "system"] = "human"
    workflow_reference: str | None = Field(default=None, max_length=255)

    @model_validator(mode="after")
    def requires_reference(self) -> ActivityCreate:
        if not any((self.opportunity_id, self.person_id, self.company_id)):
            raise ValueError("A atividade exige referência a oportunidade, pessoa ou empresa")
        return self


class ActivityResponse(BaseModel):
    id: uuid.UUID
    business_unit_id: uuid.UUID
    opportunity_id: uuid.UUID | None
    person_id: uuid.UUID | None
    company_id: uuid.UUID | None
    activity_type: str
    occurred_at: datetime
    summary: str
    origin: str
    performed_by: str
    status: str


class StageHistoryResponse(BaseModel):
    id: uuid.UUID
    from_stage_id: uuid.UUID | None
    to_stage_id: uuid.UUID
    actor_id: uuid.UUID
    source: str
    note: str | None
    changed_at: datetime


class OpportunityResponse(BaseModel):
    id: uuid.UUID
    business_unit_id: uuid.UUID
    pipeline_id: uuid.UUID
    stage_id: uuid.UUID
    company_id: uuid.UUID | None
    title: str
    status: str
    value: Decimal | None
    currency: str
    lead_source_id: uuid.UUID
    loss_reason_id: uuid.UUID | None
    expected_close_date: date | None
    person_ids: list[uuid.UUID]
    product_service_ids: list[uuid.UUID]
    customer_name: str
    product_names: list[str]
    last_interaction_at: datetime | None
    stage_entered_at: datetime
    next_action: TaskResponse | None
    created_at: datetime
    updated_at: datetime


class KanbanColumn(BaseModel):
    stage: PipelineStageItem
    opportunities: list[OpportunityResponse]


class KanbanResponse(BaseModel):
    pipeline: PipelineItem
    columns: list[KanbanColumn]


class SearchResult(BaseModel):
    resource_type: Literal["person", "company", "opportunity"]
    id: uuid.UUID
    title: str
    subtitle: str | None
    business_unit_ids: list[uuid.UUID]


class Person360Response(BaseModel):
    person: PersonSummary
    companies: list[PersonCompanyLinkResponse]
    opportunities: list[OpportunityResponse]
    activities: list[ActivityResponse]
    tasks: list[TaskResponse]


class Company360Response(BaseModel):
    company: CompanySummary
    people: list[PersonCompanyLinkResponse]
    opportunities: list[OpportunityResponse]
    activities: list[ActivityResponse]
    tasks: list[TaskResponse]


class ImportPersonRow(BaseModel):
    full_name: str = Field(min_length=2, max_length=255)
    tax_id: str | None = Field(default=None, min_length=11, max_length=14)
    email: str | None = Field(default=None, max_length=320)
    phone: str | None = Field(default=None, max_length=50)
    business_unit_ids: list[uuid.UUID] = Field(min_length=1, max_length=3)


class ImportCompanyRow(BaseModel):
    legal_name: str = Field(min_length=2, max_length=255)
    trade_name: str | None = Field(default=None, max_length=255)
    tax_id: str | None = Field(default=None, min_length=14, max_length=18)
    email: str | None = Field(default=None, max_length=320)
    phone: str | None = Field(default=None, max_length=50)
    business_unit_ids: list[uuid.UUID] = Field(min_length=1, max_length=3)


class ImportRow(BaseModel):
    entity_type: Literal["person", "company"]
    person: ImportPersonRow | None = None
    company: ImportCompanyRow | None = None

    @model_validator(mode="after")
    def payload_matches_type(self) -> ImportRow:
        if self.entity_type == "person" and (self.person is None or self.company is not None):
            raise ValueError("Linha de pessoa exige somente o payload person")
        if self.entity_type == "company" and (self.company is None or self.person is not None):
            raise ValueError("Linha de empresa exige somente o payload company")
        return self


class CrmImportCreate(BaseModel):
    source_label: str = Field(min_length=2, max_length=255)
    rows: list[ImportRow] = Field(min_length=1, max_length=100)


class ImportRowResult(BaseModel):
    row_number: int
    entity_type: str
    result: str
    resource_id: uuid.UUID | None
    error_code: str | None


class CrmImportResponse(BaseModel):
    id: uuid.UUID
    source_label: str
    status: str
    total_rows: int
    created_rows: int
    matched_rows: int
    failed_rows: int
    rows: list[ImportRowResult]
