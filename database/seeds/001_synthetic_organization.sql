INSERT INTO organizations (id, code, name)
VALUES ('10000000-0000-4000-8000-000000000001', 'grupo-stk', 'Grupo STK — dados sintéticos')
ON CONFLICT (code) DO NOTHING;

INSERT INTO legal_entities (id, organization_id, code, registered_name, trade_name)
VALUES
    ('20000000-0000-4000-8000-000000000001', '10000000-0000-4000-8000-000000000001', 'stk-solucoes', 'STK Soluções Empresariais — sintética', 'MR Engenharia e Consultoria'),
    ('20000000-0000-4000-8000-000000000002', '10000000-0000-4000-8000-000000000001', 'st-servicos', 'ST Serviços e Apoio Administrativo — sintética', 'ST Serviços'),
    ('20000000-0000-4000-8000-000000000003', '10000000-0000-4000-8000-000000000001', 'stelli-entidade', 'Stelli — entidade sintética', 'Stelli')
ON CONFLICT (organization_id, code) DO NOTHING;

INSERT INTO fiscal_establishments (id, legal_entity_id, code, name, kind)
VALUES
    ('30000000-0000-4000-8000-000000000001', '20000000-0000-4000-8000-000000000001', 'matriz-mr', 'Matriz MR — sintética', 'headquarters'),
    ('30000000-0000-4000-8000-000000000002', '20000000-0000-4000-8000-000000000001', 'filial-lab', 'Filial STK Lab — sintética', 'branch'),
    ('30000000-0000-4000-8000-000000000003', '20000000-0000-4000-8000-000000000002', 'matriz-st-servicos', 'Matriz ST Serviços — sintética', 'headquarters'),
    ('30000000-0000-4000-8000-000000000004', '20000000-0000-4000-8000-000000000003', 'matriz-stelli', 'Matriz Stelli — sintética', 'headquarters')
ON CONFLICT (legal_entity_id, code) DO NOTHING;

INSERT INTO business_units (id, organization_id, primary_establishment_id, code, name)
VALUES
    ('40000000-0000-4000-8000-000000000001', '10000000-0000-4000-8000-000000000001', '30000000-0000-4000-8000-000000000001', 'mr', 'MR Engenharia e Consultoria'),
    ('40000000-0000-4000-8000-000000000002', '10000000-0000-4000-8000-000000000001', '30000000-0000-4000-8000-000000000002', 'stk-lab', 'STK Lab'),
    ('40000000-0000-4000-8000-000000000003', '10000000-0000-4000-8000-000000000001', '30000000-0000-4000-8000-000000000004', 'stelli', 'Stelli')
ON CONFLICT (organization_id, code) DO NOTHING;

INSERT INTO permissions (code, description)
VALUES
    ('organization:read', 'Consultar a estrutura organizacional'),
    ('organization:write', 'Alterar dados permitidos da estrutura organizacional'),
    ('audit:read', 'Consultar a trilha oficial de auditoria'),
    ('events:ingest', 'Registrar eventos autenticados na inbox'),
    ('exceptions:write', 'Criar e tratar exceções operacionais')
ON CONFLICT (code) DO NOTHING;

INSERT INTO roles (id, organization_id, code, name)
VALUES
    ('50000000-0000-4000-8000-000000000001', '10000000-0000-4000-8000-000000000001', 'administrator', 'Administrador total'),
    ('50000000-0000-4000-8000-000000000002', '10000000-0000-4000-8000-000000000001', 'integration', 'Integração mínima')
ON CONFLICT (organization_id, code) DO NOTHING;

INSERT INTO role_permissions (role_id, permission_id)
SELECT '50000000-0000-4000-8000-000000000001', id FROM permissions
ON CONFLICT DO NOTHING;

INSERT INTO role_permissions (role_id, permission_id)
SELECT '50000000-0000-4000-8000-000000000002', id
FROM permissions
WHERE code IN ('organization:read', 'events:ingest', 'exceptions:write')
ON CONFLICT DO NOTHING;

