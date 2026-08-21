CREATE TABLE contracts (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id uuid NOT NULL REFERENCES organizations(id),
    business_unit_id uuid NOT NULL REFERENCES business_units(id),
    customer_company_id uuid NOT NULL REFERENCES companies(id),
    internal_number text NOT NULL,
    administrative_status text NOT NULL DEFAULT 'draft'
        CHECK (administrative_status IN ('draft', 'active', 'archived')),
    signed_on date,
    start_date date NOT NULL,
    contract_type text NOT NULL
        CHECK (contract_type IN ('recurring_service', 'project', 'retainer', 'other')),
    owner_actor_id uuid NOT NULL REFERENCES actors(id),
    controlled_notes text,
    created_by_actor_id uuid NOT NULL REFERENCES actors(id),
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (organization_id, internal_number)
);

CREATE INDEX contracts_directory_idx
    ON contracts (organization_id, business_unit_id, customer_company_id, administrative_status);

CREATE TABLE contract_versions (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id uuid NOT NULL REFERENCES organizations(id),
    contract_id uuid NOT NULL REFERENCES contracts(id),
    version_number integer NOT NULL CHECK (version_number > 0),
    effective_from date NOT NULL,
    issuer_establishment_id uuid NOT NULL REFERENCES fiscal_establishments(id),
    currency text NOT NULL CHECK (currency ~ '^[A-Z]{3}$'),
    billing_frequency text NOT NULL
        CHECK (billing_frequency IN ('monthly', 'annual', 'one_time', 'other')),
    pricing_model text NOT NULL
        CHECK (pricing_model IN ('monthly', 'annual', 'project', 'per_service', 'other')),
    amount numeric(18, 2) NOT NULL CHECK (amount >= 0),
    billing_installments integer CHECK (billing_installments IS NULL OR billing_installments > 0),
    billing_day integer CHECK (billing_day IS NULL OR billing_day BETWEEN 1 AND 31),
    payment_terms_days integer CHECK (payment_terms_days IS NULL OR payment_terms_days >= 0),
    invoice_description text,
    adjustment_reference text,
    adjustment_frequency text
        CHECK (adjustment_frequency IS NULL OR adjustment_frequency IN ('annual', 'custom', 'none')),
    adjustment_base_date date,
    adjustment_applied_percentage numeric(9, 6),
    adjustment_source text
        CHECK (adjustment_source IS NULL OR adjustment_source IN ('manual', 'index', 'not_applied')),
    change_type text NOT NULL CHECK (
        change_type IN (
            'initial', 'service_change', 'value_change', 'issuer_change',
            'conditions_change', 'adjustment', 'renewal'
        )
    ),
    change_reason text NOT NULL,
    source text NOT NULL CHECK (source IN ('ui', 'api', 'import', 'system')),
    configuration_sha256 text NOT NULL CHECK (configuration_sha256 ~ '^[a-f0-9]{64}$'),
    created_by_actor_id uuid NOT NULL REFERENCES actors(id),
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (contract_id, version_number),
    UNIQUE (contract_id, effective_from),
    UNIQUE (id, contract_id)
);

CREATE INDEX contract_versions_timeline_idx
    ON contract_versions (contract_id, effective_from, version_number);
CREATE INDEX contract_versions_issuer_idx
    ON contract_versions (organization_id, issuer_establishment_id, effective_from);

CREATE TABLE contract_version_services (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    contract_version_id uuid NOT NULL REFERENCES contract_versions(id),
    product_service_id uuid REFERENCES products_services(id),
    contractual_description text NOT NULL,
    quantity numeric(14, 3) NOT NULL DEFAULT 1 CHECK (quantity > 0),
    unit_amount numeric(18, 2) CHECK (unit_amount IS NULL OR unit_amount >= 0),
    is_active boolean NOT NULL DEFAULT true,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX contract_version_services_catalog_unique
    ON contract_version_services (contract_version_id, product_service_id)
    WHERE product_service_id IS NOT NULL;

CREATE TABLE contract_version_contacts (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    contract_version_id uuid NOT NULL REFERENCES contract_versions(id),
    contact_method_id uuid NOT NULL REFERENCES contact_methods(id),
    recipient_role text NOT NULL CHECK (recipient_role IN ('primary', 'cc')),
    purpose text NOT NULL DEFAULT 'billing',
    preferred_channel text NOT NULL CHECK (preferred_channel IN ('email', 'phone', 'whatsapp')),
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (contract_version_id, contact_method_id, recipient_role, purpose)
);

CREATE UNIQUE INDEX contract_version_one_primary_billing_contact
    ON contract_version_contacts (contract_version_id, purpose)
    WHERE recipient_role = 'primary';

CREATE TABLE contract_operational_events (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id uuid NOT NULL REFERENCES organizations(id),
    contract_id uuid NOT NULL REFERENCES contracts(id),
    event_type text NOT NULL CHECK (event_type IN ('suspended', 'resumed', 'renewed', 'terminated')),
    effective_on date NOT NULL,
    reason text NOT NULL,
    source text NOT NULL CHECK (source IN ('ui', 'api', 'import', 'system')),
    related_version_id uuid,
    actor_id uuid NOT NULL REFERENCES actors(id),
    correlation_id uuid NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    FOREIGN KEY (related_version_id, contract_id)
        REFERENCES contract_versions(id, contract_id)
);

CREATE INDEX contract_operational_events_timeline_idx
    ON contract_operational_events (contract_id, effective_on, created_at);

CREATE OR REPLACE FUNCTION validate_contract_scope()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM business_units
        WHERE id = NEW.business_unit_id AND organization_id = NEW.organization_id
    ) THEN
        RAISE EXCEPTION 'contract business unit belongs to another organization';
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM companies
        WHERE id = NEW.customer_company_id AND organization_id = NEW.organization_id
    ) THEN
        RAISE EXCEPTION 'contract customer belongs to another organization';
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM company_business_units
        WHERE company_id = NEW.customer_company_id
          AND business_unit_id = NEW.business_unit_id
          AND organization_id = NEW.organization_id
          AND status = 'active'
    ) THEN
        RAISE EXCEPTION 'contract customer is not linked to the business unit';
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM actors
        WHERE id = NEW.owner_actor_id AND organization_id = NEW.organization_id
    ) OR NOT EXISTS (
        SELECT 1 FROM actors
        WHERE id = NEW.created_by_actor_id AND organization_id = NEW.organization_id
    ) THEN
        RAISE EXCEPTION 'contract actors belong to another organization';
    END IF;
    RETURN NEW;
END;
$$;

CREATE TRIGGER contracts_validate_scope
BEFORE INSERT OR UPDATE ON contracts
FOR EACH ROW EXECUTE FUNCTION validate_contract_scope();

CREATE OR REPLACE FUNCTION validate_contract_version_insert()
RETURNS trigger
LANGUAGE plpgsql
AS $$
DECLARE
    contract_row contracts%ROWTYPE;
    latest_number integer;
    latest_date date;
BEGIN
    SELECT * INTO contract_row FROM contracts WHERE id = NEW.contract_id FOR UPDATE;
    IF contract_row.id IS NULL OR contract_row.organization_id <> NEW.organization_id THEN
        RAISE EXCEPTION 'contract version belongs to another organization';
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM actors
        WHERE id = NEW.created_by_actor_id AND organization_id = NEW.organization_id
    ) THEN
        RAISE EXCEPTION 'contract version actor belongs to another organization';
    END IF;
    IF NOT EXISTS (
        SELECT 1
        FROM fiscal_establishments fe
        JOIN legal_entities le ON le.id = fe.legal_entity_id
        WHERE fe.id = NEW.issuer_establishment_id
          AND le.organization_id = NEW.organization_id
          AND fe.status = 'active'
    ) THEN
        RAISE EXCEPTION 'issuer establishment is invalid for this organization';
    END IF;
    SELECT max(version_number), max(effective_from)
      INTO latest_number, latest_date
      FROM contract_versions WHERE contract_id = NEW.contract_id;
    IF latest_number IS NULL THEN
        IF NEW.version_number <> 1 OR NEW.effective_from <> contract_row.start_date
           OR NEW.change_type <> 'initial' THEN
            RAISE EXCEPTION 'first contract version must be initial and start with the contract';
        END IF;
    ELSE
        IF NEW.version_number <> latest_number + 1 OR NEW.effective_from <= latest_date
           OR NEW.change_type = 'initial' THEN
            RAISE EXCEPTION 'contract versions must be sequential and non-overlapping';
        END IF;
        IF NEW.effective_from < current_date THEN
            RAISE EXCEPTION 'retroactive contract version requires a future authorized correction workflow';
        END IF;
    END IF;
    RETURN NEW;
END;
$$;

CREATE TRIGGER contract_versions_validate_insert
BEFORE INSERT ON contract_versions
FOR EACH ROW EXECUTE FUNCTION validate_contract_version_insert();

CREATE OR REPLACE FUNCTION validate_contract_version_service()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    IF NEW.product_service_id IS NOT NULL AND NOT EXISTS (
        SELECT 1
        FROM contract_versions cv
        JOIN contracts c ON c.id = cv.contract_id
        JOIN products_services ps ON ps.id = NEW.product_service_id
        WHERE cv.id = NEW.contract_version_id
          AND ps.organization_id = c.organization_id
          AND ps.business_unit_id = c.business_unit_id
    ) THEN
        RAISE EXCEPTION 'catalog service is outside the contract organization or business unit';
    END IF;
    RETURN NEW;
END;
$$;

CREATE TRIGGER contract_version_services_validate
BEFORE INSERT ON contract_version_services
FOR EACH ROW EXECUTE FUNCTION validate_contract_version_service();

CREATE OR REPLACE FUNCTION validate_contract_version_contact()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM contract_versions cv
        JOIN contracts c ON c.id = cv.contract_id
        JOIN contact_methods cm ON cm.id = NEW.contact_method_id
        LEFT JOIN person_company_relationships pcr
          ON pcr.person_id = cm.person_id
         AND pcr.company_id = c.customer_company_id
         AND pcr.status = 'active'
        WHERE cv.id = NEW.contract_version_id
          AND cm.organization_id = c.organization_id
          AND cm.status = 'active'
          AND (cm.company_id = c.customer_company_id OR pcr.id IS NOT NULL)
    ) THEN
        RAISE EXCEPTION 'financial contact is not canonical for the contract customer';
    END IF;
    RETURN NEW;
END;
$$;

CREATE TRIGGER contract_version_contacts_validate
BEFORE INSERT ON contract_version_contacts
FOR EACH ROW EXECUTE FUNCTION validate_contract_version_contact();

CREATE OR REPLACE FUNCTION validate_contract_operational_event()
RETURNS trigger
LANGUAGE plpgsql
AS $$
DECLARE
    contract_row contracts%ROWTYPE;
    last_event contract_operational_events%ROWTYPE;
BEGIN
    SELECT * INTO contract_row FROM contracts WHERE id = NEW.contract_id FOR UPDATE;
    IF contract_row.id IS NULL OR contract_row.organization_id <> NEW.organization_id THEN
        RAISE EXCEPTION 'contract event belongs to another organization';
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM actors
        WHERE id = NEW.actor_id AND organization_id = NEW.organization_id
    ) THEN
        RAISE EXCEPTION 'contract event actor belongs to another organization';
    END IF;
    IF NEW.effective_on < contract_row.start_date OR NEW.effective_on < current_date THEN
        RAISE EXCEPTION 'retroactive operational event requires an authorized correction workflow';
    END IF;
    SELECT * INTO last_event
      FROM contract_operational_events
     WHERE contract_id = NEW.contract_id
       AND event_type IN ('suspended', 'resumed', 'terminated')
     ORDER BY effective_on DESC, created_at DESC
     LIMIT 1;
    IF last_event.id IS NOT NULL AND NEW.event_type <> 'renewed'
       AND NEW.effective_on <= last_event.effective_on THEN
        RAISE EXCEPTION 'operational events must have an unambiguous chronological order';
    END IF;
    IF NEW.event_type = 'suspended'
       AND last_event.id IS NOT NULL AND last_event.event_type NOT IN ('resumed') THEN
        RAISE EXCEPTION 'only an operating contract can be suspended';
    ELSIF NEW.event_type = 'resumed'
       AND (last_event.id IS NULL OR last_event.event_type <> 'suspended') THEN
        RAISE EXCEPTION 'only a suspended contract can be resumed';
    ELSIF NEW.event_type = 'terminated'
       AND last_event.id IS NOT NULL AND last_event.event_type = 'terminated' THEN
        RAISE EXCEPTION 'contract is already terminated';
    ELSIF NEW.event_type = 'renewed' AND NOT EXISTS (
        SELECT 1 FROM contract_versions
        WHERE id = NEW.related_version_id
          AND contract_id = NEW.contract_id
          AND change_type = 'renewal'
          AND effective_from = NEW.effective_on
    ) THEN
        RAISE EXCEPTION 'renewal event must reference its renewal version';
    END IF;
    RETURN NEW;
END;
$$;

CREATE TRIGGER contract_operational_events_validate
BEFORE INSERT ON contract_operational_events
FOR EACH ROW EXECUTE FUNCTION validate_contract_operational_event();

CREATE TRIGGER contract_versions_no_update
BEFORE UPDATE ON contract_versions
FOR EACH ROW EXECUTE FUNCTION reject_append_only_mutation();
CREATE TRIGGER contract_versions_no_delete
BEFORE DELETE ON contract_versions
FOR EACH ROW EXECUTE FUNCTION reject_append_only_mutation();
CREATE TRIGGER contract_version_services_no_update
BEFORE UPDATE ON contract_version_services
FOR EACH ROW EXECUTE FUNCTION reject_append_only_mutation();
CREATE TRIGGER contract_version_services_no_delete
BEFORE DELETE ON contract_version_services
FOR EACH ROW EXECUTE FUNCTION reject_append_only_mutation();
CREATE TRIGGER contract_version_contacts_no_update
BEFORE UPDATE ON contract_version_contacts
FOR EACH ROW EXECUTE FUNCTION reject_append_only_mutation();
CREATE TRIGGER contract_version_contacts_no_delete
BEFORE DELETE ON contract_version_contacts
FOR EACH ROW EXECUTE FUNCTION reject_append_only_mutation();
CREATE TRIGGER contract_operational_events_no_update
BEFORE UPDATE ON contract_operational_events
FOR EACH ROW EXECUTE FUNCTION reject_append_only_mutation();
CREATE TRIGGER contract_operational_events_no_delete
BEFORE DELETE ON contract_operational_events
FOR EACH ROW EXECUTE FUNCTION reject_append_only_mutation();

COMMENT ON TABLE contracts IS 'Administrative identity of a commercial contract; operational suspension is separate.';
COMMENT ON TABLE contract_versions IS 'Immutable published contract configurations. Valid-to is derived from the next effective-from.';
COMMENT ON TABLE contract_version_services IS 'Immutable service snapshot for one contract version.';
COMMENT ON TABLE contract_version_contacts IS 'Canonical financial-recipient snapshot for one contract version.';
COMMENT ON TABLE contract_operational_events IS 'Append-only suspension, resumption, renewal and termination history.';
