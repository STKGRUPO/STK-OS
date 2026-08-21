CREATE TABLE billing_runs (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id uuid NOT NULL REFERENCES organizations(id),
    business_unit_id uuid NOT NULL REFERENCES business_units(id),
    competence_month date NOT NULL CHECK (competence_month = date_trunc('month', competence_month)::date),
    run_type text NOT NULL CHECK (run_type IN ('manual', 'scheduled', 'reprocess')),
    status text NOT NULL DEFAULT 'processing'
        CHECK (status IN ('processing', 'completed', 'completed_with_exceptions')),
    operational_timezone text NOT NULL,
    rule_version text NOT NULL,
    actor_id uuid NOT NULL REFERENCES actors(id),
    correlation_id uuid NOT NULL,
    causation_id uuid,
    metrics jsonb NOT NULL DEFAULT '{}'::jsonb,
    started_at timestamptz NOT NULL DEFAULT now(),
    completed_at timestamptz,
    UNIQUE (organization_id, business_unit_id, competence_month)
);

CREATE INDEX billing_runs_directory_idx
    ON billing_runs (organization_id, competence_month DESC, business_unit_id, status);

CREATE TABLE billing_items (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id uuid NOT NULL REFERENCES organizations(id),
    business_unit_id uuid NOT NULL REFERENCES business_units(id),
    created_by_run_id uuid NOT NULL REFERENCES billing_runs(id),
    contract_id uuid NOT NULL REFERENCES contracts(id),
    contract_version_id uuid REFERENCES contract_versions(id),
    competence_month date NOT NULL CHECK (competence_month = date_trunc('month', competence_month)::date),
    customer_company_id uuid NOT NULL REFERENCES companies(id),
    issuer_establishment_id uuid REFERENCES fiscal_establishments(id),
    currency text CHECK (currency IS NULL OR currency ~ '^[A-Z]{3}$'),
    gross_amount numeric(18, 2) CHECK (gross_amount IS NULL OR gross_amount >= 0),
    snapshot jsonb NOT NULL,
    snapshot_sha256 text NOT NULL CHECK (snapshot_sha256 ~ '^[a-f0-9]{64}$'),
    status text NOT NULL CHECK (status IN ('blocked', 'ready', 'requested', 'completed', 'cancelled')),
    blocking_code text,
    blocking_reason text,
    correlation_id uuid NOT NULL,
    causation_id uuid,
    created_by_actor_id uuid NOT NULL REFERENCES actors(id),
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (contract_id, competence_month),
    CHECK (
        (status = 'blocked' AND blocking_code IS NOT NULL AND blocking_reason IS NOT NULL)
        OR (status <> 'blocked' AND blocking_code IS NULL AND blocking_reason IS NULL)
    ),
    CHECK (status = 'blocked' OR (contract_version_id IS NOT NULL AND issuer_establishment_id IS NOT NULL
        AND currency IS NOT NULL AND gross_amount IS NOT NULL))
);

CREATE INDEX billing_items_directory_idx
    ON billing_items (organization_id, competence_month DESC, status);
CREATE INDEX billing_items_filters_idx
    ON billing_items (organization_id, business_unit_id, customer_company_id, status);

CREATE TABLE billing_run_contracts (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    billing_run_id uuid NOT NULL REFERENCES billing_runs(id),
    contract_id uuid NOT NULL REFERENCES contracts(id),
    billing_item_id uuid REFERENCES billing_items(id),
    outcome text NOT NULL CHECK (outcome IN ('created', 'reused', 'not_eligible')),
    reason_code text,
    reason_detail text,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (billing_run_id, contract_id),
    CHECK ((outcome = 'not_eligible') = (billing_item_id IS NULL)),
    CHECK ((outcome = 'not_eligible') = (reason_code IS NOT NULL))
);

CREATE INDEX billing_run_contracts_item_idx ON billing_run_contracts (billing_item_id);

CREATE OR REPLACE FUNCTION validate_billing_run_scope()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM business_units
        WHERE id = NEW.business_unit_id AND organization_id = NEW.organization_id
    ) THEN
        RAISE EXCEPTION 'billing run business unit belongs to another organization';
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM actors
        WHERE id = NEW.actor_id AND organization_id = NEW.organization_id
    ) THEN
        RAISE EXCEPTION 'billing run actor belongs to another organization';
    END IF;
    RETURN NEW;
END;
$$;

CREATE TRIGGER billing_runs_validate_scope
BEFORE INSERT OR UPDATE ON billing_runs
FOR EACH ROW EXECUTE FUNCTION validate_billing_run_scope();

CREATE OR REPLACE FUNCTION validate_billing_item_scope()
RETURNS trigger
LANGUAGE plpgsql
AS $$
DECLARE
    run_row billing_runs%ROWTYPE;
    contract_row contracts%ROWTYPE;
BEGIN
    SELECT * INTO run_row FROM billing_runs WHERE id = NEW.created_by_run_id;
    SELECT * INTO contract_row FROM contracts WHERE id = NEW.contract_id;
    IF run_row.id IS NULL OR contract_row.id IS NULL
       OR run_row.organization_id <> NEW.organization_id
       OR run_row.business_unit_id <> NEW.business_unit_id
       OR run_row.competence_month <> NEW.competence_month
       OR contract_row.organization_id <> NEW.organization_id
       OR contract_row.business_unit_id <> NEW.business_unit_id
       OR contract_row.customer_company_id <> NEW.customer_company_id THEN
        RAISE EXCEPTION 'billing item scope is inconsistent with run or contract';
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM actors
        WHERE id = NEW.created_by_actor_id AND organization_id = NEW.organization_id
    ) THEN
        RAISE EXCEPTION 'billing item actor belongs to another organization';
    END IF;
    IF NEW.contract_version_id IS NOT NULL AND NOT EXISTS (
        SELECT 1 FROM contract_versions
        WHERE id = NEW.contract_version_id
          AND contract_id = NEW.contract_id
          AND organization_id = NEW.organization_id
    ) THEN
        RAISE EXCEPTION 'billing item contract version is inconsistent';
    END IF;
    IF NEW.issuer_establishment_id IS NOT NULL AND NOT EXISTS (
        SELECT 1
        FROM fiscal_establishments fe
        JOIN legal_entities le ON le.id = fe.legal_entity_id
        WHERE fe.id = NEW.issuer_establishment_id
          AND le.organization_id = NEW.organization_id
    ) THEN
        RAISE EXCEPTION 'billing item issuer belongs to another organization';
    END IF;
    RETURN NEW;
END;
$$;

CREATE TRIGGER billing_items_validate_scope
BEFORE INSERT ON billing_items
FOR EACH ROW EXECUTE FUNCTION validate_billing_item_scope();

CREATE OR REPLACE FUNCTION protect_billing_item_history()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    IF NEW.organization_id IS DISTINCT FROM OLD.organization_id
       OR NEW.business_unit_id IS DISTINCT FROM OLD.business_unit_id
       OR NEW.created_by_run_id IS DISTINCT FROM OLD.created_by_run_id
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
    ) THEN
        RAISE EXCEPTION 'invalid billing item state transition';
    END IF;
    NEW.updated_at := now();
    RETURN NEW;
END;
$$;

CREATE TRIGGER billing_items_protect_history
BEFORE UPDATE ON billing_items
FOR EACH ROW EXECUTE FUNCTION protect_billing_item_history();
CREATE TRIGGER billing_items_no_delete
BEFORE DELETE ON billing_items
FOR EACH ROW EXECUTE FUNCTION reject_append_only_mutation();
CREATE TRIGGER billing_run_contracts_no_update
BEFORE UPDATE ON billing_run_contracts
FOR EACH ROW EXECUTE FUNCTION reject_append_only_mutation();
CREATE TRIGGER billing_run_contracts_no_delete
BEFORE DELETE ON billing_run_contracts
FOR EACH ROW EXECUTE FUNCTION reject_append_only_mutation();

COMMENT ON COLUMN billing_runs.competence_month IS
    'Civil month represented by its first date; API format is YYYY-MM.';
COMMENT ON TABLE billing_items IS
    'Immutable financial obligation snapshot. Fiscal issuance is outside this module.';
COMMENT ON TABLE billing_run_contracts IS
    'Frozen explanation of each contract considered by a billing run.';
