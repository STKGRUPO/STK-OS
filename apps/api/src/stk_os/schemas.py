from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal
from decimal import

from pydantic import BaseModel, ConfigDict, Field, field_validator


class TokenResponse(BaseModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_in: int


class UserLogin(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=12, max_length=1024)


class ServiceLogin(BaseModel):
    client_id: str = Field(min_length=3, max_length=255)
    client_secret: str = Field(min_length=16, max_length=1024)


class ActorContext(BaseModel):
    id: uuid.UUID
    organization_id: uuid.UUID
    kind: Literal["user", "service_account"]
    display_name: str
    permissions: frozenset[str]


class BusinessUnitUpdate(BaseModel):
    name: str = Field(min_length=2, max_length=255)


class BusinessUnitResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    code: str
    name: str
    status: str
    primary_establishment_id: uuid.UUID


def normalize_tax_id(value: object) -> object:
    if value is None or not isinstance(value, str):
        return value
    digits = "".join(character for character in value if character.isdigit())
    return digits or None


class LegalEntityCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    registered_name: str = Field(min_length=2, max_length=255)
    trade_name: str | None = Field(default=None, max_length=255)
    tax_id: str | None = Field(default=None, min_length=14, max_length=14)
    status: Literal["active", "inactive"] = "active"
    code: str | None = Field(default=None, min_length=2, max_length=100, pattern=r"^[a-z0-9-]+$")

    _normalize_tax_id = field_validator("tax_id", mode="before")(normalize_tax_id)


class LegalEntityUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    registered_name: str = Field(min_length=2, max_length=255)
    trade_name: str | None = Field(default=None, max_length=255)
    tax_id: str | None = Field(default=None, min_length=14, max_length=14)
    status: Literal["active", "inactive"]

    _normalize_tax_id = field_validator("tax_id", mode="before")(normalize_tax_id)


class FiscalEstablishmentCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=2, max_length=255)
    tax_id: str | None = Field(default=None, min_length=14, max_length=14)
    kind: Literal["headquarters", "branch"]
    status: Literal["active", "inactive"] = "active"
    business_unit_ids: list[uuid.UUID] = []
    code: str | None = Field(default=None, min_length=2, max_length=100, pattern=r"^[a-z0-9-]+$")

    _normalize_tax_id = field_validator("tax_id", mode="before")(normalize_tax_id)


class FiscalEstablishmentUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=2, max_length=255)
    tax_id: str | None = Field(default=None, min_length=14, max_length=14)
    kind: Literal["headquarters", "branch"]
    status: Literal["active", "inactive"]
    business_unit_ids: list[uuid.UUID] = []

    _normalize_tax_id = field_validator("tax_id", mode="before")(normalize_tax_id)


class FiscalEstablishmentResponse(BaseModel):
    id: uuid.UUID
    code: str
    name: str
    kind: str
    tax_id: str | None
    status: str
    legal_entity_id: uuid.UUID
    business_units: list[BusinessUnitResponse]


class LegalEntityResponse(BaseModel):
    id: uuid.UUID
    code: str
    registered_name: str
    trade_name: str | None
    tax_id: str | None
    status: str
    establishments: list[FiscalEstablishmentResponse]


class OrganizationResponse(BaseModel):
    id: uuid.UUID
    code: str
    name: str
    status: str
    legal_entities: list[LegalEntityResponse]


class InboxEventCreate(BaseModel):
    source: str = Field(min_length=1, max_length=100)
    external_event_id: str = Field(min_length=1, max_length=255)
    event_type: str = Field(min_length=1, max_length=150)
    payload: dict[str, Any]


class InboxEventResponse(BaseModel):
    id: uuid.UUID
    status: str
    duplicate: bool
    correlation_id: uuid.UUID


class ExceptionCreate(BaseModel):
    exception_type: str = Field(min_length=1, max_length=150)
    severity: Literal["low", "medium", "high", "critical"]
    title: str = Field(min_length=1, max_length=255)
    context: dict[str, Any] = Field(default_factory=dict)


class ExceptionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    exception_type: str
    severity: str
    title: str
    context: dict[str, Any]
    status: str
    correlation_id: uuid.UUID
    created_at: datetime


class AuditEventResponse(BaseModel):
    id: uuid.UUID
    actor_id: uuid.UUID | None
    correlation_id: uuid.UUID
    action: str
    resource_type: str
    resource_id: uuid.UUID | None
    before_state: dict[str, Any] | None
    after_state: dict[str, Any] | None
    occurred_at: datetime


class FiscalConfigUpsert(BaseModel):
    model_config = ConfigDict(extra="forbid")

    environment: Literal["homologation", "production"]
    emission_method: Literal["api_a1", "blocked"] = "api_a1"
    endpoint: str = Field(min_length=12, max_length=500, pattern=r"^https://")
    query_base_url: str = Field(min_length=12, max_length=500, pattern=r"^https://")
    certificate_secret_ref: str = Field(min_length=2, max_length=500)
    certificate_key_id: str = Field(min_length=2, max_length=255)
    municipality_code: str = Field(pattern=r"^\d{7}$")
    series: int = Field(ge=1, le=99999)
    next_dps_number: int = Field(ge=1)
    service_code: str = Field(min_length=1, max_length=20)
    nbs_code: str = Field(min_length=1, max_length=20)
    fiscal_rules: dict[str, object] = {}
    status: Literal["active", "inactive"] = "active"


class FiscalConfigResponse(BaseModel):
    id: uuid.UUID
    establishment_id: uuid.UUID
    environment: str
    provider: str
    emission_method: str
    endpoint: str
    query_base_url: str
    certificate_secret_ref: str
    certificate_key_id: str
    municipality_code: str
    series: int
    next_dps_number: int
    service_code: str
    nbs_code: str
    fiscal_rules: dict[str, object]
    status: str


class FiscalConfigListResponse(BaseModel):
    configs: list[FiscalConfigResponse]


class ProductServiceUpsert(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=2, max_length=255)
    business_unit_ids: list[uuid.UUID] = []
    code: str | None = Field(default=None, max_length=50)
    description: str | None = Field(default=None, max_length=2000)
    default_amount: Decimal | None = None
    service_code: str | None = Field(default=None, max_length=20)
    nbs_code: str | None = Field(default=None, max_length=20)
    status: Literal["active", "inactive"] = "active"


class ProductServiceResponse(BaseModel):
    id: uuid.UUID
    name: str
    code: str | None = None
    description: str | None = None
    default_amount: Decimal | None = None
    service_code: str | None = None
    nbs_code: str | None = None
    business_unit_ids: list[uuid.UUID] = []
    status: str


class ProductServiceListResponse(BaseModel):
    items: list[ProductServiceResponse]
