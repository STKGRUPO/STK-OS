from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class IdentityRole(BaseModel):
    id: uuid.UUID
    code: str
    name: str
    capabilities: list[str]


class CurrentUser(BaseModel):
    id: uuid.UUID
    actor_id: uuid.UUID
    organization_id: uuid.UUID
    email: str
    display_name: str
    status: str
    first_access_completed: bool
    roles: list[IdentityRole]
    business_unit_ids: list[uuid.UUID]
    capabilities: list[str]


class UserInvite(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: str = Field(min_length=3, max_length=320)
    display_name: str = Field(min_length=2, max_length=255)
    role_id: uuid.UUID
    business_unit_ids: list[uuid.UUID] = []


class UserAccessUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role_id: uuid.UUID
    business_unit_ids: list[uuid.UUID] = []


class UserSummary(BaseModel):
    id: uuid.UUID
    actor_id: uuid.UUID
    email: str
    display_name: str
    status: str
    first_access_completed: bool
    last_login_at: datetime | None
    roles: list[IdentityRole]
    business_unit_ids: list[uuid.UUID]


class IssuedAccessLink(BaseModel):
    user: UserSummary
    purpose: Literal["invite", "password_reset"]
    token: str
    expires_at: datetime


class PasswordDefinition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=12, max_length=1024)
    token: str | None = Field(default=None, min_length=32, max_length=1024)

    @field_validator("email", mode="before")
    @classmethod
    def normalize_email(cls, value: object) -> object:
        return value.strip().lower() if isinstance(value, str) else value

    @field_validator("token", mode="before")
    @classmethod
    def empty_token_is_absent(cls, value: object) -> object:
        if not isinstance(value, str):
            return value
        return value.strip() or None


class PasswordResetRequest(BaseModel):
    email: str = Field(min_length=3, max_length=320)


class GenericMessage(BaseModel):
    message: str
