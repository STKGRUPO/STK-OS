ALTER TABLE users ALTER COLUMN password_hash DROP NOT NULL;
ALTER TABLE users ADD COLUMN password_set_at timestamptz;

CREATE TABLE user_access_tokens (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id uuid NOT NULL REFERENCES users(id),
    token_hash text NOT NULL UNIQUE CHECK (token_hash ~ '^[a-f0-9]{64}$'),
    purpose text NOT NULL CHECK (purpose IN ('invite', 'password_reset')),
    issued_by_actor_id uuid REFERENCES actors(id),
    expires_at timestamptz NOT NULL,
    consumed_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX user_access_tokens_lookup_idx
    ON user_access_tokens (token_hash, purpose, expires_at) WHERE consumed_at IS NULL;

CREATE TABLE client_services (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id uuid NOT NULL REFERENCES organizations(id),
    business_unit_id uuid NOT NULL REFERENCES business_units(id),
    customer_company_id uuid NOT NULL REFERENCES companies(id),
    product_service_id uuid REFERENCES products_services(id),
    contract_id uuid REFERENCES contracts(id),
    name text NOT NULL,
    description text,
    service_type text NOT NULL CHECK (service_type IN ('recurring', 'one_time')),
    recurrence text CHECK (recurrence IN ('monthly', 'quarterly', 'semiannual', 'annual', 'custom')),
    interval_months integer CHECK (interval_months IS NULL OR interval_months > 0),
    start_date date NOT NULL,
    next_occurrence_on date,
    owner_actor_id uuid NOT NULL REFERENCES actors(id),
    amount numeric(18, 2) NOT NULL CHECK (amount >= 0),
    currency text NOT NULL DEFAULT 'BRL' CHECK (currency ~ '^[A-Z]{3}$'),
    operational_lead_days integer NOT NULL DEFAULT 0 CHECK (operational_lead_days >= 0),
    reminder_lead_days integer NOT NULL DEFAULT 0 CHECK (reminder_lead_days >= 0),
    status text NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'inactive')),
    created_by_actor_id uuid NOT NULL REFERENCES actors(id),
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CHECK (
        (service_type = 'one_time' AND recurrence IS NULL AND interval_months IS NULL)
        OR (service_type = 'recurring' AND recurrence IS NOT NULL)
    ),
    CHECK (
        recurrence <> 'custom' OR interval_months IS NOT NULL
    )
);
CREATE INDEX client_services_customer_idx
    ON client_services (organization_id, customer_company_id, status);
CREATE INDEX client_services_next_occurrence_idx
    ON client_services (organization_id, business_unit_id, next_occurrence_on)
    WHERE status = 'active';

CREATE TABLE client_service_occurrences (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id uuid NOT NULL REFERENCES organizations(id),
    client_service_id uuid NOT NULL REFERENCES client_services(id),
    scheduled_for date NOT NULL,
    due_on date NOT NULL,
    status text NOT NULL DEFAULT 'planned'
        CHECK (status IN ('planned', 'preparing', 'scheduled', 'in_progress', 'completed', 'to_bill', 'billed', 'closed')),
    billing_status text NOT NULL DEFAULT 'to_bill'
        CHECK (billing_status IN ('not_ready', 'to_bill', 'item_created', 'billed')),
    owner_actor_id uuid NOT NULL REFERENCES actors(id),
    created_by_actor_id uuid NOT NULL REFERENCES actors(id),
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (client_service_id, scheduled_for)
);
CREATE INDEX client_service_occurrences_due_idx
    ON client_service_occurrences (organization_id, due_on, status);

ALTER TABLE billing_items ALTER COLUMN created_by_run_id DROP NOT NULL;
ALTER TABLE billing_items ALTER COLUMN contract_id DROP NOT NULL;
ALTER TABLE billing_items ADD COLUMN source_type text NOT NULL DEFAULT 'contract_recurring'
    CHECK (source_type IN ('contract_recurring', 'service_recurring', 'service_one_time'));
ALTER TABLE billing_items ADD COLUMN client_service_id uuid REFERENCES client_services(id);
ALTER TABLE billing_items ADD COLUMN service_occurrence_id uuid REFERENCES client_service_occurrences(id);
CREATE UNIQUE INDEX billing_items_service_occurrence_unique
    ON billing_items (service_occurrence_id) WHERE service_occurrence_id IS NOT NULL;
ALTER TABLE client_service_occurrences ADD COLUMN billing_item_id uuid REFERENCES billing_items(id);

DO $$
DECLARE constraint_name text;
BEGIN
    SELECT conname INTO constraint_name
    FROM pg_constraint
    WHERE conrelid = 'billing_items'::regclass
      AND contype = 'c'
      AND pg_get_constraintdef(oid) LIKE '%contract_version_id IS NOT NULL%';
    IF constraint_name IS NOT NULL THEN
        EXECUTE format('ALTER TABLE billing_items DROP CONSTRAINT %I', constraint_name);
    END IF;
END;
$$;
ALTER TABLE billing_items ADD CONSTRAINT billing_items_ready_fields CHECK (
    status = 'blocked'
    OR (issuer_establishment_id IS NOT NULL AND currency IS NOT NULL AND gross_amount IS NOT NULL
        AND (source_type <> 'contract_recurring' OR contract_version_id IS NOT NULL))
);

ALTER TABLE billing_items ADD CONSTRAINT billing_items_source_consistency CHECK (
    (source_type = 'contract_recurring' AND contract_id IS NOT NULL)
    OR (source_type = 'service_recurring' AND contract_id IS NULL AND client_service_id IS NOT NULL AND service_occurrence_id IS NOT NULL)
    OR (source_type = 'service_one_time' AND contract_id IS NULL AND client_service_id IS NOT NULL AND service_occurrence_id IS NOT NULL)
);

CREATE OR REPLACE FUNCTION validate_client_service_scope()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM business_units
        WHERE id = NEW.business_unit_id AND organization_id = NEW.organization_id
    ) OR NOT EXISTS (
        SELECT 1 FROM companies
        WHERE id = NEW.customer_company_id AND organization_id = NEW.organization_id
    ) OR NOT EXISTS (
        SELECT 1 FROM actors
        WHERE id = NEW.owner_actor_id AND organization_id = NEW.organization_id
    ) OR NOT EXISTS (
        SELECT 1 FROM actors
        WHERE id = NEW.created_by_actor_id AND organization_id = NEW.organization_id
    ) THEN
        RAISE EXCEPTION 'client service scope is inconsistent';
    END IF;
    IF NEW.contract_id IS NOT NULL AND NOT EXISTS (
        SELECT 1 FROM contracts
        WHERE id = NEW.contract_id
          AND organization_id = NEW.organization_id
          AND business_unit_id = NEW.business_unit_id
          AND customer_company_id = NEW.customer_company_id
    ) THEN
        RAISE EXCEPTION 'client service contract scope is inconsistent';
    END IF;
    RETURN NEW;
END;
$$;
CREATE TRIGGER client_services_validate_scope
BEFORE INSERT OR UPDATE ON client_services
FOR EACH ROW EXECUTE FUNCTION validate_client_service_scope();

CREATE OR REPLACE FUNCTION validate_billing_item_scope()
RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE
    run_row billing_runs%ROWTYPE;
    contract_row contracts%ROWTYPE;
    service_row client_services%ROWTYPE;
BEGIN
    IF NEW.created_by_run_id IS NOT NULL THEN
        SELECT * INTO run_row FROM billing_runs WHERE id = NEW.created_by_run_id;
        IF run_row.id IS NULL
           OR run_row.organization_id <> NEW.organization_id
           OR run_row.business_unit_id <> NEW.business_unit_id
           OR run_row.competence_month <> NEW.competence_month THEN
            RAISE EXCEPTION 'billing item scope is inconsistent with run';
        END IF;
    END IF;
    IF NEW.contract_id IS NOT NULL THEN
        SELECT * INTO contract_row FROM contracts WHERE id = NEW.contract_id;
        IF contract_row.id IS NULL
           OR contract_row.organization_id <> NEW.organization_id
           OR contract_row.business_unit_id <> NEW.business_unit_id
           OR contract_row.customer_company_id <> NEW.customer_company_id THEN
            RAISE EXCEPTION 'billing item scope is inconsistent with contract';
        END IF;
    END IF;
    IF NEW.client_service_id IS NOT NULL THEN
        SELECT * INTO service_row FROM client_services WHERE id = NEW.client_service_id;
        IF service_row.id IS NULL
           OR service_row.organization_id <> NEW.organization_id
           OR service_row.business_unit_id <> NEW.business_unit_id
           OR service_row.customer_company_id <> NEW.customer_company_id
           OR service_row.contract_id IS DISTINCT FROM NEW.contract_id THEN
            RAISE EXCEPTION 'billing item scope is inconsistent with client service';
        END IF;
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM actors
        WHERE id = NEW.created_by_actor_id AND organization_id = NEW.organization_id
    ) THEN RAISE EXCEPTION 'billing item actor belongs to another organization'; END IF;
    IF NEW.contract_version_id IS NOT NULL AND NOT EXISTS (
        SELECT 1 FROM contract_versions
        WHERE id = NEW.contract_version_id AND contract_id = NEW.contract_id
          AND organization_id = NEW.organization_id
    ) THEN RAISE EXCEPTION 'billing item contract version is inconsistent'; END IF;
    IF NEW.issuer_establishment_id IS NOT NULL AND NOT EXISTS (
        SELECT 1 FROM fiscal_establishments fe
        JOIN legal_entities le ON le.id = fe.legal_entity_id
        WHERE fe.id = NEW.issuer_establishment_id AND le.organization_id = NEW.organization_id
    ) THEN RAISE EXCEPTION 'billing item issuer belongs to another organization'; END IF;
    RETURN NEW;
END;
$$;

CREATE OR REPLACE FUNCTION protect_billing_item_history()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF NEW.organization_id IS DISTINCT FROM OLD.organization_id
       OR NEW.business_unit_id IS DISTINCT FROM OLD.business_unit_id
       OR NEW.created_by_run_id IS DISTINCT FROM OLD.created_by_run_id
       OR NEW.source_type IS DISTINCT FROM OLD.source_type
       OR NEW.client_service_id IS DISTINCT FROM OLD.client_service_id
       OR NEW.service_occurrence_id IS DISTINCT FROM OLD.service_occurrence_id
       OR NEW.contract_id IS DISTINCT FROM OLD.contract_id
       OR NEW.contract_version_id IS DISTINCT FROM OLD.contract_version_id
       OR NEW.competence_month IS DISTINCT FROM OLD.competence_month
       OR NEW.customer_company_id IS DISTINCT FROM OLD.customer_company_id
       OR NEW.issuer_establishment_id IS DISTINCT FROM OLD.issuer_establishment_id
       OR NEW.currency IS DISTINCT FROM OLD.currency
       OR NEW.gross_amount IS DISTINCT FROM OLD.gross_amount
       OR NEW.snapshot IS DISTINCT FROM OLD.snapshot
       OR NEW.snapshot_sha256 IS DISTINCT FROM OLD.snapshot_sha256
       OR NEW.blocking_code IS DISTINCT FROM OLD.blocking_code
       OR NEW.blocking_reason IS DISTINCT FROM OLD.blocking_reason
       OR NEW.correlation_id IS DISTINCT FROM OLD.correlation_id
       OR NEW.causation_id IS DISTINCT FROM OLD.causation_id
       OR NEW.created_by_actor_id IS DISTINCT FROM OLD.created_by_actor_id
       OR NEW.created_at IS DISTINCT FROM OLD.created_at THEN
        RAISE EXCEPTION 'billing item financial snapshot is immutable';
    END IF;
    IF (OLD.status, NEW.status) NOT IN (
        ('ready', 'ready'), ('ready', 'requested'),
        ('requested', 'requested'), ('requested', 'completed'),
        ('blocked', 'blocked'), ('ready', 'cancelled'),
        ('requested', 'cancelled'), ('cancelled', 'cancelled'),
        ('completed', 'completed')
    ) THEN RAISE EXCEPTION 'invalid billing item state transition'; END IF;
    NEW.updated_at := now();
    RETURN NEW;
END;
$$;

INSERT INTO permissions (code, description) VALUES
    ('identity:manage', 'Convidar, associar e desativar usuários'),
    ('services:read', 'Consultar serviços e ocorrências de clientes'),
    ('services:write', 'Criar e alterar serviços e ocorrências de clientes')
ON CONFLICT (code) DO NOTHING;
INSERT INTO role_permissions (role_id, permission_id)
SELECT roles.id, permissions.id
FROM roles CROSS JOIN permissions
WHERE roles.code = 'administrator'
  AND permissions.code IN ('identity:manage', 'services:read', 'services:write')
ON CONFLICT DO NOTHING;

COMMENT ON TABLE client_services IS
    'Serviço prestado ao cliente CRM, recorrente ou pontual, com contrato opcional.';
COMMENT ON TABLE client_service_occurrences IS
    'Execução individual do serviço com prazo, estado e situação de faturamento próprios.';
COMMENT ON COLUMN billing_items.source_type IS
    'Origem comercial da obrigação, independente de contrato obrigatório.';
