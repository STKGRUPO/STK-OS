CREATE TABLE people (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id uuid NOT NULL REFERENCES organizations(id),
    full_name text NOT NULL,
    tax_id text,
    city text,
    state_code text,
    notes text,
    status text NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'inactive')),
    created_by_actor_id uuid REFERENCES actors(id),
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (organization_id, tax_id),
    CHECK (tax_id IS NULL OR tax_id ~ '^[0-9]{11}$'),
    CHECK (state_code IS NULL OR state_code ~ '^[A-Z]{2}$')
);
CREATE INDEX people_name_idx ON people (organization_id, lower(full_name));

CREATE TABLE companies (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id uuid NOT NULL REFERENCES organizations(id),
    legal_name text NOT NULL,
    trade_name text,
    tax_id text,
    address_line text,
    city text,
    state_code text,
    site text,
    notes text,
    status text NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'inactive')),
    created_by_actor_id uuid REFERENCES actors(id),
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (organization_id, tax_id),
    CHECK (tax_id IS NULL OR tax_id ~ '^[0-9]{14}$'),
    CHECK (state_code IS NULL OR state_code ~ '^[A-Z]{2}$')
);

CREATE INDEX companies_name_idx ON companies (organization_id, lower(legal_name));

CREATE TABLE contact_methods (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id uuid NOT NULL REFERENCES organizations(id),
    person_id uuid REFERENCES people(id),
    company_id uuid REFERENCES companies(id),
    kind text NOT NULL CHECK (kind IN ('email', 'phone', 'whatsapp')),
    label text,
    value text NOT NULL,
    normalized_value text NOT NULL,
    is_primary boolean NOT NULL DEFAULT false,
    status text NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'inactive')),
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CHECK ((person_id IS NOT NULL)::integer + (company_id IS NOT NULL)::integer = 1)
);

CREATE INDEX contact_methods_lookup_idx
    ON contact_methods (organization_id, kind, normalized_value);
CREATE UNIQUE INDEX contact_methods_person_unique
    ON contact_methods (person_id, kind, normalized_value) WHERE person_id IS NOT NULL;
CREATE UNIQUE INDEX contact_methods_company_unique
    ON contact_methods (company_id, kind, normalized_value) WHERE company_id IS NOT NULL;

CREATE TABLE lead_sources (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id uuid NOT NULL REFERENCES organizations(id),
    code text NOT NULL,
    name text NOT NULL,
    status text NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'inactive')),
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (organization_id, code)
);

CREATE TABLE person_business_units (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id uuid NOT NULL REFERENCES organizations(id),
    person_id uuid NOT NULL REFERENCES people(id),
    business_unit_id uuid NOT NULL REFERENCES business_units(id),
    lead_source_id uuid REFERENCES lead_sources(id),
    owner_actor_id uuid REFERENCES actors(id),
    status text NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'inactive')),
    notes text,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (person_id, business_unit_id)
);

CREATE TABLE company_business_units (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id uuid NOT NULL REFERENCES organizations(id),
    company_id uuid NOT NULL REFERENCES companies(id),
    business_unit_id uuid NOT NULL REFERENCES business_units(id),
    lead_source_id uuid REFERENCES lead_sources(id),
    owner_actor_id uuid REFERENCES actors(id),
    status text NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'inactive')),
    notes text,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (company_id, business_unit_id)
);

CREATE TABLE person_company_relationships (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id uuid NOT NULL REFERENCES organizations(id),
    person_id uuid NOT NULL REFERENCES people(id),
    company_id uuid NOT NULL REFERENCES companies(id),
    role text NOT NULL,
    is_primary boolean NOT NULL DEFAULT false,
    status text NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'inactive')),
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (person_id, company_id, role)
);

CREATE TABLE products_services (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id uuid NOT NULL REFERENCES organizations(id),
    business_unit_id uuid NOT NULL REFERENCES business_units(id),
    code text NOT NULL,
    name text NOT NULL,
    category text,
    status text NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'inactive')),
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (business_unit_id, code)
);

CREATE TABLE pipelines (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id uuid NOT NULL REFERENCES organizations(id),
    business_unit_id uuid NOT NULL REFERENCES business_units(id),
    code text NOT NULL,
    name text NOT NULL,
    kind text NOT NULL DEFAULT 'sales' CHECK (kind IN ('sales', 'operations')),
    status text NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'inactive')),
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (business_unit_id, code),
    UNIQUE (id, business_unit_id)
);

CREATE TABLE pipeline_stages (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    pipeline_id uuid NOT NULL REFERENCES pipelines(id),
    code text NOT NULL,
    name text NOT NULL,
    position integer NOT NULL CHECK (position > 0),
    sla_days integer CHECK (sla_days IS NULL OR sla_days > 0),
    status text NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'inactive')),
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (pipeline_id, code),
    UNIQUE (pipeline_id, position),
    UNIQUE (id, pipeline_id)
);

CREATE TABLE loss_reasons (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id uuid NOT NULL REFERENCES organizations(id),
    business_unit_id uuid NOT NULL REFERENCES business_units(id),
    code text NOT NULL,
    name text NOT NULL,
    status text NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'inactive')),
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (business_unit_id, code)
);

CREATE TABLE opportunities (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id uuid NOT NULL REFERENCES organizations(id),
    business_unit_id uuid NOT NULL REFERENCES business_units(id),
    pipeline_id uuid NOT NULL,
    stage_id uuid NOT NULL,
    company_id uuid REFERENCES companies(id),
    title text NOT NULL,
    status text NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'won', 'lost')),
    value numeric(14, 2) CHECK (value IS NULL OR value >= 0),
    currency text NOT NULL DEFAULT 'BRL' CHECK (currency ~ '^[A-Z]{3}$'),
    lead_source_id uuid NOT NULL REFERENCES lead_sources(id),
    loss_reason_id uuid REFERENCES loss_reasons(id),
    owner_actor_id uuid NOT NULL REFERENCES actors(id),
    expected_close_date date,
    notes text,
    entered_at timestamptz NOT NULL DEFAULT now(),
    closed_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    FOREIGN KEY (pipeline_id, business_unit_id)
        REFERENCES pipelines(id, business_unit_id),
    FOREIGN KEY (stage_id, pipeline_id)
        REFERENCES pipeline_stages(id, pipeline_id),
    CHECK (
        (status = 'lost' AND loss_reason_id IS NOT NULL AND closed_at IS NOT NULL)
        OR (status = 'won' AND loss_reason_id IS NULL AND closed_at IS NOT NULL)
        OR (status = 'open' AND loss_reason_id IS NULL AND closed_at IS NULL)
    )
);

CREATE INDEX opportunities_kanban_idx
    ON opportunities (organization_id, business_unit_id, pipeline_id, status, stage_id);

CREATE TABLE opportunity_contacts (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    opportunity_id uuid NOT NULL REFERENCES opportunities(id),
    person_id uuid NOT NULL REFERENCES people(id),
    role text NOT NULL DEFAULT 'contact',
    is_primary boolean NOT NULL DEFAULT false,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (opportunity_id, person_id, role)
);

CREATE TABLE opportunity_products (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    opportunity_id uuid NOT NULL REFERENCES opportunities(id),
    product_service_id uuid NOT NULL REFERENCES products_services(id),
    quantity numeric(12, 3) NOT NULL DEFAULT 1 CHECK (quantity > 0),
    unit_value numeric(14, 2) CHECK (unit_value IS NULL OR unit_value >= 0),
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (opportunity_id, product_service_id)
);

CREATE TABLE opportunity_stage_history (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id uuid NOT NULL REFERENCES organizations(id),
    opportunity_id uuid NOT NULL REFERENCES opportunities(id),
    from_stage_id uuid REFERENCES pipeline_stages(id),
    to_stage_id uuid NOT NULL REFERENCES pipeline_stages(id),
    actor_id uuid NOT NULL REFERENCES actors(id),
    source text NOT NULL CHECK (source IN ('api', 'ui', 'import', 'system')),
    note text,
    changed_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX opportunity_stage_history_opportunity_idx
    ON opportunity_stage_history (opportunity_id, changed_at);

CREATE TABLE activities (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id uuid NOT NULL REFERENCES organizations(id),
    business_unit_id uuid NOT NULL REFERENCES business_units(id),
    opportunity_id uuid REFERENCES opportunities(id),
    person_id uuid REFERENCES people(id),
    company_id uuid REFERENCES companies(id),
    activity_type text NOT NULL CHECK (
        activity_type IN (
            'whatsapp', 'email', 'call', 'meeting', 'proposal', 'follow_up',
            'service', 'note', 'automatic_interaction', 'ai_action'
        )
    ),
    occurred_at timestamptz NOT NULL,
    responsible_actor_id uuid NOT NULL REFERENCES actors(id),
    summary text NOT NULL,
    origin text NOT NULL,
    next_step text,
    performed_by text NOT NULL CHECK (performed_by IN ('human', 'agent', 'system')),
    workflow_reference text,
    status text NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'voided')),
    created_at timestamptz NOT NULL DEFAULT now(),
    CHECK (opportunity_id IS NOT NULL OR person_id IS NOT NULL OR company_id IS NOT NULL)
);

CREATE INDEX activities_timeline_idx
    ON activities (organization_id, occurred_at DESC);

CREATE TABLE tasks (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id uuid NOT NULL REFERENCES organizations(id),
    business_unit_id uuid NOT NULL REFERENCES business_units(id),
    opportunity_id uuid REFERENCES opportunities(id),
    person_id uuid REFERENCES people(id),
    company_id uuid REFERENCES companies(id),
    title text NOT NULL,
    due_at timestamptz NOT NULL,
    owner_actor_id uuid NOT NULL REFERENCES actors(id),
    priority text NOT NULL DEFAULT 'medium' CHECK (priority IN ('low', 'medium', 'high')),
    status text NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'completed', 'cancelled')),
    notes text,
    completed_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CHECK (opportunity_id IS NOT NULL OR person_id IS NOT NULL OR company_id IS NOT NULL),
    CHECK (
        (status = 'completed' AND completed_at IS NOT NULL)
        OR (status <> 'completed' AND completed_at IS NULL)
    )
);

CREATE INDEX tasks_next_action_idx
    ON tasks (opportunity_id, status, due_at);

CREATE TABLE crm_import_jobs (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id uuid NOT NULL REFERENCES organizations(id),
    actor_id uuid NOT NULL REFERENCES actors(id),
    correlation_id uuid NOT NULL,
    source_label text NOT NULL,
    status text NOT NULL CHECK (status IN ('processing', 'completed', 'completed_with_errors')),
    total_rows integer NOT NULL CHECK (total_rows > 0 AND total_rows <= 100),
    created_rows integer NOT NULL DEFAULT 0 CHECK (created_rows >= 0),
    matched_rows integer NOT NULL DEFAULT 0 CHECK (matched_rows >= 0),
    failed_rows integer NOT NULL DEFAULT 0 CHECK (failed_rows >= 0),
    created_at timestamptz NOT NULL DEFAULT now(),
    completed_at timestamptz
);

CREATE TABLE crm_import_rows (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    import_job_id uuid NOT NULL REFERENCES crm_import_jobs(id),
    row_number integer NOT NULL CHECK (row_number > 0),
    entity_type text NOT NULL CHECK (entity_type IN ('person', 'company')),
    input_sha256 text NOT NULL CHECK (input_sha256 ~ '^[a-f0-9]{64}$'),
    result text NOT NULL CHECK (result IN ('created', 'matched', 'failed')),
    resource_id uuid,
    error_code text,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (import_job_id, row_number)
);
