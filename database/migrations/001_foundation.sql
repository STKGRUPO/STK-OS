CREATE EXTENSION IF NOT EXISTS citext;
CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE IF NOT EXISTS schema_migrations (
    version text PRIMARY KEY,
    checksum_sha256 text NOT NULL,
    applied_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE organizations (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    code text NOT NULL UNIQUE,
    name text NOT NULL,
    status text NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'inactive')),
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE legal_entities (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id uuid NOT NULL REFERENCES organizations(id),
    code text NOT NULL,
    registered_name text NOT NULL,
    trade_name text,
    tax_id text,
    status text NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'inactive')),
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (organization_id, code),
    UNIQUE (organization_id, tax_id),
    CHECK (tax_id IS NULL OR tax_id ~ '^[0-9]{14}$')
);

CREATE TABLE fiscal_establishments (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    legal_entity_id uuid NOT NULL REFERENCES legal_entities(id),
    code text NOT NULL,
    name text NOT NULL,
    kind text NOT NULL CHECK (kind IN ('headquarters', 'branch')),
    tax_id text,
    status text NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'inactive')),
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (legal_entity_id, code),
    UNIQUE (tax_id),
    CHECK (tax_id IS NULL OR tax_id ~ '^[0-9]{14}$')
);

CREATE TABLE business_units (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id uuid NOT NULL REFERENCES organizations(id),
    primary_establishment_id uuid NOT NULL REFERENCES fiscal_establishments(id),
    code text NOT NULL,
    name text NOT NULL,
    status text NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'inactive')),
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (organization_id, code)
);

CREATE TABLE actors (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id uuid NOT NULL REFERENCES organizations(id),
    kind text NOT NULL CHECK (kind IN ('user', 'service_account')),
    display_name text NOT NULL,
    status text NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'disabled')),
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE users (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    actor_id uuid NOT NULL UNIQUE REFERENCES actors(id),
    email citext NOT NULL UNIQUE,
    password_hash text NOT NULL,
    last_login_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE service_accounts (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    actor_id uuid NOT NULL UNIQUE REFERENCES actors(id),
    client_id citext NOT NULL UNIQUE,
    secret_hash text NOT NULL,
    expires_at timestamptz,
    last_used_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE roles (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id uuid NOT NULL REFERENCES organizations(id),
    code text NOT NULL,
    name text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (organization_id, code)
);

CREATE TABLE permissions (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    code text NOT NULL UNIQUE,
    description text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE actor_roles (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    actor_id uuid NOT NULL REFERENCES actors(id),
    role_id uuid NOT NULL REFERENCES roles(id),
    business_unit_id uuid REFERENCES business_units(id),
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX actor_roles_org_wide_unique
    ON actor_roles (actor_id, role_id)
    WHERE business_unit_id IS NULL;

CREATE UNIQUE INDEX actor_roles_unit_unique
    ON actor_roles (actor_id, role_id, business_unit_id)
    WHERE business_unit_id IS NOT NULL;

CREATE TABLE role_permissions (
    role_id uuid NOT NULL REFERENCES roles(id),
    permission_id uuid NOT NULL REFERENCES permissions(id),
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (role_id, permission_id)
);

CREATE TABLE audit_events (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id uuid NOT NULL REFERENCES organizations(id),
    actor_id uuid REFERENCES actors(id),
    correlation_id uuid NOT NULL,
    action text NOT NULL,
    resource_type text NOT NULL,
    resource_id uuid,
    before_state jsonb,
    after_state jsonb,
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
    occurred_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX audit_events_correlation_idx ON audit_events (correlation_id);
CREATE INDEX audit_events_resource_idx ON audit_events (resource_type, resource_id);
CREATE INDEX audit_events_occurred_idx ON audit_events (occurred_at DESC);

CREATE TABLE idempotency_keys (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    actor_id uuid NOT NULL REFERENCES actors(id),
    command_name text NOT NULL,
    idempotency_key text NOT NULL,
    request_hash text NOT NULL,
    status text NOT NULL DEFAULT 'processing' CHECK (status IN ('processing', 'completed', 'failed')),
    response_status integer,
    response_body jsonb,
    correlation_id uuid NOT NULL,
    locked_at timestamptz NOT NULL DEFAULT now(),
    completed_at timestamptz,
    expires_at timestamptz NOT NULL,
    UNIQUE (actor_id, command_name, idempotency_key)
);

CREATE INDEX idempotency_keys_expires_idx ON idempotency_keys (expires_at);

CREATE TABLE inbox_events (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id uuid NOT NULL REFERENCES organizations(id),
    source text NOT NULL,
    external_event_id text NOT NULL,
    event_type text NOT NULL,
    payload jsonb NOT NULL,
    payload_sha256 text NOT NULL,
    correlation_id uuid NOT NULL,
    status text NOT NULL DEFAULT 'received' CHECK (status IN ('received', 'processing', 'processed', 'failed')),
    received_at timestamptz NOT NULL DEFAULT now(),
    processed_at timestamptz,
    UNIQUE (organization_id, source, external_event_id)
);

CREATE INDEX inbox_events_status_idx ON inbox_events (status, received_at);

CREATE TABLE outbox_events (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id uuid NOT NULL REFERENCES organizations(id),
    aggregate_type text NOT NULL,
    aggregate_id uuid NOT NULL,
    event_type text NOT NULL,
    payload jsonb NOT NULL,
    correlation_id uuid NOT NULL,
    status text NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'publishing', 'published', 'failed')),
    attempts integer NOT NULL DEFAULT 0 CHECK (attempts >= 0),
    available_at timestamptz NOT NULL DEFAULT now(),
    published_at timestamptz,
    last_error_code text,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX outbox_events_dispatch_idx ON outbox_events (status, available_at);

CREATE TABLE exceptions (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id uuid NOT NULL REFERENCES organizations(id),
    actor_id uuid REFERENCES actors(id),
    correlation_id uuid NOT NULL,
    exception_type text NOT NULL,
    severity text NOT NULL CHECK (severity IN ('low', 'medium', 'high', 'critical')),
    title text NOT NULL,
    context jsonb NOT NULL DEFAULT '{}'::jsonb,
    status text NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'in_progress', 'resolved', 'dismissed')),
    resolution text,
    created_at timestamptz NOT NULL DEFAULT now(),
    resolved_at timestamptz
);

CREATE INDEX exceptions_status_idx ON exceptions (status, severity, created_at);
