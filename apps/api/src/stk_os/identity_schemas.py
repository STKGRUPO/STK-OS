from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


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
    token: str = Field(min_length=32, max_length=1024)
    password: str = Field(min_length=12, max_length=1024)


class PasswordResetRequest(BaseModel):
    email: str = Field(min_length=3, max_length=320)


class GenericMessage(BaseModel):
    message: str
