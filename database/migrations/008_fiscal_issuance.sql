ALTER TABLE companies ADD COLUMN municipality_code text
    CHECK (municipality_code IS NULL OR municipality_code ~ '^\d{7}$');
ALTER TABLE companies ADD COLUMN postal_code text
    CHECK (postal_code IS NULL OR postal_code ~ '^\d{8}$');

CREATE TABLE fiscal_establishment_configs (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id uuid NOT NULL REFERENCES organizations(id),
    establishment_id uuid NOT NULL REFERENCES fiscal_establishments(id),
    environment text NOT NULL CHECK (environment IN ('homologation', 'production')),
    provider text NOT NULL DEFAULT 'sefin_nacional',
    emission_method text NOT NULL CHECK (emission_method IN ('api_a1', 'blocked')),
    endpoint text NOT NULL CHECK (endpoint ~ '^https://'),
    query_base_url text NOT NULL CHECK (query_base_url ~ '^https://'),
    certificate_secret_ref text NOT NULL,
    certificate_key_id text NOT NULL,
    municipality_code text NOT NULL CHECK (municipality_code ~ '^\d{7}$'),
    series integer NOT NULL DEFAULT 1 CHECK (series > 0 AND series <= 99999),
    next_dps_number bigint NOT NULL DEFAULT 1 CHECK (next_dps_number > 0),
    service_code text NOT NULL,
    nbs_code text NOT NULL,
    fiscal_rules jsonb NOT NULL DEFAULT '{}'::jsonb,
    status text NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'inactive')),
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (establishment_id, environment)
);

CREATE TABLE fiscal_issuances (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id uuid NOT NULL REFERENCES organizations(id),
    billing_item_id uuid NOT NULL UNIQUE REFERENCES billing_items(id),
    establishment_config_id uuid NOT NULL REFERENCES fiscal_establishment_configs(id),
    environment text NOT NULL CHECK (environment IN ('homologation', 'production')),
    status text NOT NULL CHECK (status IN (
        'validating', 'processing', 'uncertain', 'completed', 'rejected',
        'external_unavailable', 'configuration_error', 'document_error'
    )),
    series integer NOT NULL,
    dps_number bigint NOT NULL,
    dps_id text NOT NULL UNIQUE,
    snapshot jsonb NOT NULL,
    snapshot_sha256 text NOT NULL CHECK (snapshot_sha256 ~ '^[a-f0-9]{64}$'),
    signed_dps_sha256 text CHECK (signed_dps_sha256 IS NULL OR signed_dps_sha256 ~ '^[a-f0-9]{64}$'),
    nfse_number text,
    access_key text UNIQUE,
    provider_reference text,
    error_category text,
    error_code text,
    error_message text,
    lease_owner text,
    lease_expires_at timestamptz,
    requested_by_actor_id uuid NOT NULL REFERENCES actors(id),
    correlation_id uuid NOT NULL,
    requested_at timestamptz NOT NULL DEFAULT now(),
    last_reconciled_at timestamptz,
    completed_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (establishment_config_id, environment, series, dps_number),
    CHECK (
        (status IN ('completed', 'document_error'))
        = (nfse_number IS NOT NULL AND access_key IS NOT NULL)
    )
);
CREATE INDEX fiscal_issuances_reconcile_idx
    ON fiscal_issuances (organization_id, status, updated_at)
    WHERE status IN ('uncertain', 'processing', 'document_error');

CREATE TABLE fiscal_attempts (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    issuance_id uuid NOT NULL REFERENCES fiscal_issuances(id),
    attempt_number integer NOT NULL CHECK (attempt_number > 0),
    operation text NOT NULL CHECK (operation IN ('issue', 'reconcile')),
    request_sha256 text CHECK (request_sha256 IS NULL OR request_sha256 ~ '^[a-f0-9]{64}$'),
    external_status integer,
    outcome text NOT NULL,
    provider_reference text,
    error_category text,
    error_code text,
    sanitized_detail text,
    started_at timestamptz NOT NULL DEFAULT now(),
    completed_at timestamptz,
    UNIQUE (issuance_id, attempt_number)
);

CREATE TABLE fiscal_documents (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    issuance_id uuid NOT NULL REFERENCES fiscal_issuances(id),
    document_type text NOT NULL CHECK (
        document_type IN ('nfse_xml', 'danfse_pdf', 'provider_receipt')
    ),
    storage_key text,
    content_type text NOT NULL,
    content_sha256 text CHECK (content_sha256 IS NULL OR content_sha256 ~ '^[a-f0-9]{64}$'),
    size_bytes bigint CHECK (size_bytes IS NULL OR size_bytes >= 0),
    status text NOT NULL CHECK (status IN ('available', 'failed')),
    error_code text,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (issuance_id, document_type),
    CHECK (
        (status = 'available' AND storage_key IS NOT NULL AND content_sha256 IS NOT NULL)
        OR (status = 'failed' AND error_code IS NOT NULL)
    )
);

CREATE OR REPLACE FUNCTION validate_fiscal_config_scope()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM fiscal_establishments fe
        JOIN legal_entities le ON le.id = fe.legal_entity_id
        WHERE fe.id = NEW.establishment_id
          AND le.organization_id = NEW.organization_id
    ) THEN RAISE EXCEPTION 'fiscal config establishment belongs to another organization'; END IF;
    RETURN NEW;
END;
$$;
CREATE TRIGGER fiscal_configs_validate_scope
BEFORE INSERT OR UPDATE ON fiscal_establishment_configs
FOR EACH ROW EXECUTE FUNCTION validate_fiscal_config_scope();

CREATE OR REPLACE FUNCTION protect_fiscal_issuance_identity()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF NEW.organization_id IS DISTINCT FROM OLD.organization_id
       OR NEW.billing_item_id IS DISTINCT FROM OLD.billing_item_id
       OR NEW.establishment_config_id IS DISTINCT FROM OLD.establishment_config_id
       OR NEW.environment IS DISTINCT FROM OLD.environment
       OR NEW.series IS DISTINCT FROM OLD.series
       OR NEW.dps_number IS DISTINCT FROM OLD.dps_number
       OR NEW.dps_id IS DISTINCT FROM OLD.dps_id
       OR NEW.snapshot IS DISTINCT FROM OLD.snapshot
       OR NEW.snapshot_sha256 IS DISTINCT FROM OLD.snapshot_sha256
       OR NEW.requested_by_actor_id IS DISTINCT FROM OLD.requested_by_actor_id
       OR NEW.correlation_id IS DISTINCT FROM OLD.correlation_id
       OR NEW.requested_at IS DISTINCT FROM OLD.requested_at
       OR NEW.created_at IS DISTINCT FROM OLD.created_at THEN
        RAISE EXCEPTION 'fiscal issuance identity is immutable';
    END IF;
    NEW.updated_at := now();
    RETURN NEW;
END;
$$;
CREATE TRIGGER fiscal_issuances_protect_identity
BEFORE UPDATE ON fiscal_issuances
FOR EACH ROW EXECUTE FUNCTION protect_fiscal_issuance_identity();
CREATE TRIGGER fiscal_issuances_no_delete
BEFORE DELETE ON fiscal_issuances
FOR EACH ROW EXECUTE FUNCTION reject_append_only_mutation();
CREATE TRIGGER fiscal_attempts_no_delete
BEFORE DELETE ON fiscal_attempts
FOR EACH ROW EXECUTE FUNCTION reject_append_only_mutation();
CREATE TRIGGER fiscal_documents_no_update
BEFORE UPDATE ON fiscal_documents
FOR EACH ROW EXECUTE FUNCTION reject_append_only_mutation();
CREATE TRIGGER fiscal_documents_no_delete
BEFORE DELETE ON fiscal_documents
FOR EACH ROW EXECUTE FUNCTION reject_append_only_mutation();

INSERT INTO permissions (code, description) VALUES
    ('fiscal:issue', 'Solicitar emissão fiscal de item elegível'),
    ('fiscal:read', 'Consultar emissão e documentos fiscais'),
    ('fiscal:reconcile', 'Reconciliar resultado fiscal incerto')
ON CONFLICT (code) DO NOTHING;
INSERT INTO role_permissions (role_id, permission_id)
SELECT roles.id, permissions.id
FROM roles CROSS JOIN permissions
WHERE roles.code = 'administrator'
  AND permissions.code IN ('fiscal:issue', 'fiscal:read', 'fiscal:reconcile')
ON CONFLICT DO NOTHING;

COMMENT ON TABLE fiscal_issuances IS
    'Uma única intenção fiscal durável por billing item; timeout exige reconciliação, nunca retry cego.';
COMMENT ON COLUMN fiscal_establishment_configs.certificate_secret_ref IS
    'Referência opaca ao secret manager; nunca contém certificado ou senha.';
