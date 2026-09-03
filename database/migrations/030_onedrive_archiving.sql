CREATE TABLE integration_connections (
    id uuid PRIMARY KEY,
    organization_id uuid NOT NULL REFERENCES organizations(id),
    provider varchar(30) NOT NULL,
    account_id varchar(255),
    account_name varchar(255),
    access_token_ciphertext bytea NOT NULL,
    access_token_nonce bytea NOT NULL,
    refresh_token_ciphertext bytea NOT NULL,
    refresh_token_nonce bytea NOT NULL,
    token_expires_at timestamptz NOT NULL,
    scopes text NOT NULL,
    status varchar(20) NOT NULL DEFAULT 'active',
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (organization_id, provider),
    CHECK (provider IN ('onedrive')),
    CHECK (status IN ('active', 'error'))
);

CREATE TABLE integration_oauth_states (
    state_sha256 varchar(64) PRIMARY KEY,
    organization_id uuid NOT NULL REFERENCES organizations(id),
    requested_by_actor_id uuid NOT NULL REFERENCES actors(id),
    expires_at timestamptz NOT NULL,
    consumed_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE fiscal_archive_jobs (
    id uuid PRIMARY KEY,
    organization_id uuid NOT NULL REFERENCES organizations(id),
    issuance_id uuid NOT NULL REFERENCES fiscal_issuances(id),
    provider varchar(30) NOT NULL DEFAULT 'onedrive',
    status varchar(20) NOT NULL DEFAULT 'pending',
    attempts integer NOT NULL DEFAULT 0,
    last_error text,
    remote_path varchar(1000),
    archived_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (issuance_id, provider),
    CHECK (provider IN ('onedrive')),
    CHECK (status IN ('pending', 'completed', 'failed')),
    CHECK (attempts >= 0)
);

CREATE INDEX fiscal_archive_jobs_pending_idx
    ON fiscal_archive_jobs (organization_id, provider, status, updated_at);

CREATE INDEX fiscal_archive_jobs_issuance_idx
    ON fiscal_archive_jobs (issuance_id);
