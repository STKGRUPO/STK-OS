create table if not exists fiscal_certificates (
    id uuid primary key default gen_random_uuid(),
    organization_id uuid not null references organizations(id) on delete cascade,
    establishment_id uuid not null references fiscal_establishments(id) on delete cascade,
    environment text not null check (environment in ('homologation','production')),
    holder_name text,
    tax_id text,
    thumbprint text,
    not_before timestamptz,
    not_after timestamptz,
    secret_ref text not null,
    status text not null default 'active',
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    unique (establishment_id, environment)
);

create index if not exists ix_fiscal_certificates_org on fiscal_certificates (organization_id);
