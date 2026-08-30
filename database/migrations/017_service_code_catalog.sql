CREATE TABLE IF NOT EXISTS service_code_catalog (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    service_code TEXT NOT NULL,
    nbs_code TEXT,
    description TEXT,
    default_iss_percent NUMERIC(6,3),
    status TEXT NOT NULL DEFAULT 'active',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS service_code_catalog_code_key
    ON service_code_catalog (service_code);

CREATE TABLE IF NOT EXISTS service_code_municipal_rates (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    service_code_id UUID NOT NULL
        REFERENCES service_code_catalog(id) ON DELETE CASCADE,
    municipality_code TEXT NOT NULL,
    iss_percent NUMERIC(6,3),
    iss_retained_by_taker BOOLEAN NOT NULL DEFAULT FALSE,
    source TEXT,
    legal_basis TEXT,
    confirmed_by TEXT,
    confirmed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS service_code_rates_pair_key
    ON service_code_municipal_rates (service_code_id, municipality_code);
