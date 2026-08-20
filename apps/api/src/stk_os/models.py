from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class Organization(TimestampMixin, Base):
    __tablename__ = "organizations"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    code: Mapped[str] = mapped_column(String(100), unique=True)
    name: Mapped[str] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(20), default="active")


class LegalEntity(TimestampMixin, Base):
    __tablename__ = "legal_entities"
    __table_args__ = (
        UniqueConstraint("organization_id", "code"),
        UniqueConstraint("organization_id", "tax_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"))
    code: Mapped[str] = mapped_column(String(100))
    registered_name: Mapped[str] = mapped_column(String(255))
    trade_name: Mapped[str | None] = mapped_column(String(255))
    tax_id: Mapped[str | None] = mapped_column(String(14))
    status: Mapped[str] = mapped_column(String(20), default="active")


class FiscalEstablishment(TimestampMixin, Base):
    __tablename__ = "fiscal_establishments"
    __table_args__ = (UniqueConstraint("legal_entity_id", "code"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    legal_entity_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("legal_entities.id"))
    code: Mapped[str] = mapped_column(String(100))
    name: Mapped[str] = mapped_column(String(255))
    kind: Mapped[str] = mapped_column(String(20))
    tax_id: Mapped[str | None] = mapped_column(String(14), unique=True)
    status: Mapped[str] = mapped_column(String(20), default="active")


class BusinessUnit(TimestampMixin, Base):
    __tablename__ = "business_units"
    __table_args__ = (UniqueConstraint("organization_id", "code"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"))
    primary_establishment_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("fiscal_establishments.id")
    )
    code: Mapped[str] = mapped_column(String(100))
    name: Mapped[str] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(20), default="active")


class Actor(TimestampMixin, Base):
    __tablename__ = "actors"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"))
    kind: Mapped[str] = mapped_column(String(30))
    display_name: Mapped[str] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(20), default="active")


class User(TimestampMixin, Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    actor_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("actors.id"), unique=True)
    email: Mapped[str] = mapped_column(String(320), unique=True)
    password_hash: Mapped[str] = mapped_column(Text)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ServiceAccount(TimestampMixin, Base):
    __tablename__ = "service_accounts"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    actor_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("actors.id"), unique=True)
    client_id: Mapped[str] = mapped_column(String(255), unique=True)
    secret_hash: Mapped[str] = mapped_column(Text)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Role(Base):
    __tablename__ = "roles"
    __table_args__ = (UniqueConstraint("organization_id", "code"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"))
    code: Mapped[str] = mapped_column(String(100))
    name: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Permission(Base):
    __tablename__ = "permissions"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    code: Mapped[str] = mapped_column(String(150), unique=True)
    description: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ActorRole(Base):
    __tablename__ = "actor_roles"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    actor_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("actors.id"))
    role_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("roles.id"))
    business_unit_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("business_units.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class RolePermission(Base):
    __tablename__ = "role_permissions"

    role_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("roles.id"), primary_key=True)
    permission_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("permissions.id"), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AuditEvent(Base):
    __tablename__ = "audit_events"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"))
    actor_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("actors.id"))
    correlation_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    action: Mapped[str] = mapped_column(String(150))
    resource_type: Mapped[str] = mapped_column(String(100))
    resource_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    before_state: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    after_state: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    event_metadata: Mapped[dict[str, Any]] = mapped_column("metadata", JSON, default=dict)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class IdempotencyKey(Base):
    __tablename__ = "idempotency_keys"
    __table_args__ = (UniqueConstraint("actor_id", "command_name", "idempotency_key"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    actor_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("actors.id"))
    command_name: Mapped[str] = mapped_column(String(150))
    idempotency_key: Mapped[str] = mapped_column(String(255))
    request_hash: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(20), default="processing")
    response_status: Mapped[int | None] = mapped_column(Integer)
    response_body: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    correlation_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    locked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class InboxEvent(Base):
    __tablename__ = "inbox_events"
    __table_args__ = (UniqueConstraint("organization_id", "source", "external_event_id"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"))
    source: Mapped[str] = mapped_column(String(100))
    external_event_id: Mapped[str] = mapped_column(String(255))
    event_type: Mapped[str] = mapped_column(String(150))
    payload: Mapped[dict[str, Any]] = mapped_column(JSON)
    payload_sha256: Mapped[str] = mapped_column(String(64))
    correlation_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    status: Mapped[str] = mapped_column(String(20), default="received")
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class OutboxEvent(Base):
    __tablename__ = "outbox_events"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"))
    aggregate_type: Mapped[str] = mapped_column(String(100))
    aggregate_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    event_type: Mapped[str] = mapped_column(String(150))
    payload: Mapped[dict[str, Any]] = mapped_column(JSON)
    correlation_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    status: Mapped[str] = mapped_column(String(20), default="pending")
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    available_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error_code: Mapped[str | None] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class OperationalException(Base):
    __tablename__ = "exceptions"
    __table_args__ = (
        CheckConstraint("severity IN ('low', 'medium', 'high', 'critical')"),
        Index("exceptions_status_idx", "status", "severity", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"))
    actor_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("actors.id"))
    correlation_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    exception_type: Mapped[str] = mapped_column(String(150))
    severity: Mapped[str] = mapped_column(String(20))
    title: Mapped[str] = mapped_column(String(255))
    context: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(20), default="open")
    resolution: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Person(TimestampMixin, Base):
    __tablename__ = "people"
    __table_args__ = (UniqueConstraint("organization_id", "tax_id"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"))
    full_name: Mapped[str] = mapped_column(String(255))
    tax_id: Mapped[str | None] = mapped_column(String(11))
    city: Mapped[str | None] = mapped_column(String(255))
    state_code: Mapped[str | None] = mapped_column(String(2))
    notes: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="active")
    created_by_actor_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("actors.id"))


class Company(TimestampMixin, Base):
    __tablename__ = "companies"
    __table_args__ = (UniqueConstraint("organization_id", "tax_id"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"))
    legal_name: Mapped[str] = mapped_column(String(255))
    trade_name: Mapped[str | None] = mapped_column(String(255))
    tax_id: Mapped[str | None] = mapped_column(String(14))
    address_line: Mapped[str | None] = mapped_column(Text)
    city: Mapped[str | None] = mapped_column(String(255))
    state_code: Mapped[str | None] = mapped_column(String(2))
    site: Mapped[str | None] = mapped_column(String(500))
    notes: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="active")
    created_by_actor_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("actors.id"))


class ContactMethod(TimestampMixin, Base):
    __tablename__ = "contact_methods"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"))
    person_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("people.id"))
    company_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("companies.id"))
    kind: Mapped[str] = mapped_column(String(20))
    label: Mapped[str | None] = mapped_column(String(100))
    value: Mapped[str] = mapped_column(String(320))
    normalized_value: Mapped[str] = mapped_column(String(320))
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False)
    status: Mapped[str] = mapped_column(String(20), default="active")


class LeadSource(TimestampMixin, Base):
    __tablename__ = "lead_sources"
    __table_args__ = (UniqueConstraint("organization_id", "code"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"))
    code: Mapped[str] = mapped_column(String(100))
    name: Mapped[str] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(20), default="active")


class PersonBusinessUnit(TimestampMixin, Base):
    __tablename__ = "person_business_units"
    __table_args__ = (UniqueConstraint("person_id", "business_unit_id"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"))
    person_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("people.id"))
    business_unit_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("business_units.id"))
    lead_source_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("lead_sources.id"))
    owner_actor_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("actors.id"))
    status: Mapped[str] = mapped_column(String(20), default="active")
    notes: Mapped[str | None] = mapped_column(Text)


class CompanyBusinessUnit(TimestampMixin, Base):
    __tablename__ = "company_business_units"
    __table_args__ = (UniqueConstraint("company_id", "business_unit_id"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"))
    company_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("companies.id"))
    business_unit_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("business_units.id"))
    lead_source_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("lead_sources.id"))
    owner_actor_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("actors.id"))
    status: Mapped[str] = mapped_column(String(20), default="active")
    notes: Mapped[str | None] = mapped_column(Text)


class PersonCompanyRelationship(TimestampMixin, Base):
    __tablename__ = "person_company_relationships"
    __table_args__ = (UniqueConstraint("person_id", "company_id", "role"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"))
    person_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("people.id"))
    company_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("companies.id"))
    role: Mapped[str] = mapped_column(String(100))
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False)
    status: Mapped[str] = mapped_column(String(20), default="active")


class ProductService(TimestampMixin, Base):
    __tablename__ = "products_services"
    __table_args__ = (UniqueConstraint("business_unit_id", "code"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"))
    business_unit_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("business_units.id"))
    code: Mapped[str] = mapped_column(String(100))
    name: Mapped[str] = mapped_column(String(255))
    category: Mapped[str | None] = mapped_column(String(100))
    status: Mapped[str] = mapped_column(String(20), default="active")


class Pipeline(TimestampMixin, Base):
    __tablename__ = "pipelines"
    __table_args__ = (UniqueConstraint("business_unit_id", "code"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"))
    business_unit_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("business_units.id"))
    code: Mapped[str] = mapped_column(String(100))
    name: Mapped[str] = mapped_column(String(255))
    kind: Mapped[str] = mapped_column(String(20), default="sales")
    status: Mapped[str] = mapped_column(String(20), default="active")


class PipelineStage(TimestampMixin, Base):
    __tablename__ = "pipeline_stages"
    __table_args__ = (
        UniqueConstraint("pipeline_id", "code"),
        UniqueConstraint("pipeline_id", "position"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    pipeline_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("pipelines.id"))
    code: Mapped[str] = mapped_column(String(100))
    name: Mapped[str] = mapped_column(String(255))
    position: Mapped[int] = mapped_column(Integer)
    sla_days: Mapped[int | None] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(20), default="active")


class LossReason(TimestampMixin, Base):
    __tablename__ = "loss_reasons"
    __table_args__ = (UniqueConstraint("business_unit_id", "code"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"))
    business_unit_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("business_units.id"))
    code: Mapped[str] = mapped_column(String(100))
    name: Mapped[str] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(20), default="active")


class Opportunity(TimestampMixin, Base):
    __tablename__ = "opportunities"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"))
    business_unit_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("business_units.id"))
    pipeline_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("pipelines.id"))
    stage_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("pipeline_stages.id"))
    company_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("companies.id"))
    title: Mapped[str] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(20), default="open")
    value: Mapped[float | None] = mapped_column(Numeric(14, 2))
    currency: Mapped[str] = mapped_column(String(3), default="BRL")
    lead_source_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("lead_sources.id"))
    loss_reason_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("loss_reasons.id"))
    owner_actor_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("actors.id"))
    expected_close_date: Mapped[datetime | None] = mapped_column(Date)
    notes: Mapped[str | None] = mapped_column(Text)
    entered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class OpportunityContact(Base):
    __tablename__ = "opportunity_contacts"
    __table_args__ = (UniqueConstraint("opportunity_id", "person_id", "role"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    opportunity_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("opportunities.id"))
    person_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("people.id"))
    role: Mapped[str] = mapped_column(String(100), default="contact")
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class OpportunityProduct(Base):
    __tablename__ = "opportunity_products"
    __table_args__ = (UniqueConstraint("opportunity_id", "product_service_id"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    opportunity_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("opportunities.id"))
    product_service_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("products_services.id"))
    quantity: Mapped[float] = mapped_column(Numeric(12, 3), default=1)
    unit_value: Mapped[float | None] = mapped_column(Numeric(14, 2))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class OpportunityStageHistory(Base):
    __tablename__ = "opportunity_stage_history"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"))
    opportunity_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("opportunities.id"))
    from_stage_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("pipeline_stages.id"))
    to_stage_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("pipeline_stages.id"))
    actor_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("actors.id"))
    source: Mapped[str] = mapped_column(String(20))
    note: Mapped[str | None] = mapped_column(Text)
    changed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Activity(Base):
    __tablename__ = "activities"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"))
    business_unit_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("business_units.id"))
    opportunity_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("opportunities.id"))
    person_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("people.id"))
    company_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("companies.id"))
    activity_type: Mapped[str] = mapped_column(String(30))
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    responsible_actor_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("actors.id"))
    summary: Mapped[str] = mapped_column(Text)
    origin: Mapped[str] = mapped_column(String(100))
    next_step: Mapped[str | None] = mapped_column(Text)
    performed_by: Mapped[str] = mapped_column(String(20))
    workflow_reference: Mapped[str | None] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(20), default="active")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Task(TimestampMixin, Base):
    __tablename__ = "tasks"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"))
    business_unit_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("business_units.id"))
    opportunity_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("opportunities.id"))
    person_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("people.id"))
    company_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("companies.id"))
    title: Mapped[str] = mapped_column(String(255))
    due_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    owner_actor_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("actors.id"))
    priority: Mapped[str] = mapped_column(String(20), default="medium")
    status: Mapped[str] = mapped_column(String(20), default="open")
    notes: Mapped[str | None] = mapped_column(Text)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class CrmImportJob(Base):
    __tablename__ = "crm_import_jobs"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"))
    actor_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("actors.id"))
    correlation_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    source_label: Mapped[str] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(30))
    total_rows: Mapped[int] = mapped_column(Integer)
    created_rows: Mapped[int] = mapped_column(Integer, default=0)
    matched_rows: Mapped[int] = mapped_column(Integer, default=0)
    failed_rows: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class CrmImportRow(Base):
    __tablename__ = "crm_import_rows"
    __table_args__ = (UniqueConstraint("import_job_id", "row_number"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    import_job_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("crm_import_jobs.id"))
    row_number: Mapped[int] = mapped_column(Integer)
    entity_type: Mapped[str] = mapped_column(String(20))
    input_sha256: Mapped[str] = mapped_column(String(64))
    result: Mapped[str] = mapped_column(String(20))
    resource_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    error_code: Mapped[str | None] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
