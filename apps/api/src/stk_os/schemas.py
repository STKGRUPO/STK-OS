from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

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
