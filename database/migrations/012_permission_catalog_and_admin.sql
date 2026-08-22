-- 012_permission_catalog_and_admin.sql
-- Causa raiz: os códigos de permissão de CRM, contratos e faturamento nunca foram
-- criados por nenhuma migração (só existiam no seed sintético). Sem a linha em
-- `permissions`, nenhum papel pode receber a capacidade e toda rota devolve 403.

INSERT INTO permissions (code, description) VALUES
    ('organization:read',   'Consultar a estrutura organizacional'),
    ('organization:write',  'Alterar dados permitidos da estrutura organizacional'),
    ('audit:read',          'Consultar a trilha oficial de auditoria'),
    ('events:ingest',       'Registrar eventos autenticados na inbox'),
    ('exceptions:write',    'Criar e tratar exceções operacionais'),
    ('crm:read',            'Consultar clientes e empresas'),
    ('crm:write',           'Criar e alterar clientes e empresas'),
    ('crm:import',          'Importar carteira de clientes'),
    ('contracts:read',      'Consultar contratos'),
    ('contracts:create',    'Criar contratos'),
    ('contracts:update',    'Alterar contratos'),
    ('contracts:version',   'Versionar contratos'),
    ('contracts:suspend',   'Suspender contratos'),
    ('contracts:resume',    'Retomar contratos'),
    ('contracts:terminate', 'Encerrar contratos'),
    ('billing:read',        'Consultar faturamento'),
    ('billing:generate',    'Gerar faturamento'),
    ('billing:review',      'Revisar faturamento'),
    ('billing:reprocess',   'Reprocessar faturamento'),
    ('identity:manage',     'Convidar, associar e desativar usuários'),
    ('services:read',       'Consultar serviços e ocorrências'),
    ('services:write',      'Criar e alterar serviços e ocorrências'),
    ('fiscal:read',         'Consultar emissão e documentos fiscais'),
    ('fiscal:issue',        'Solicitar emissão fiscal'),
    ('fiscal:reconcile',    'Reconciliar resultado fiscal incerto')
ON CONFLICT (code) DO NOTHING;

-- Administrador de cada organização recebe o catálogo completo.
INSERT INTO role_permissions (role_id, permission_id)
SELECT roles.id, permissions.id
FROM roles
CROSS JOIN permissions
WHERE roles.code = 'administrator'
ON CONFLICT DO NOTHING;

-- Papel padrão de auto-cadastro fica somente-leitura (em vez de sem nenhuma permissão).
INSERT INTO role_permissions (role_id, permission_id)
SELECT roles.id, permissions.id
FROM roles
JOIN permissions ON permissions.code IN (
    'organization:read', 'crm:read', 'contracts:read',
    'billing:read', 'services:read', 'fiscal:read'
)
WHERE roles.code = 'user'
ON CONFLICT DO NOTHING;

-- Organização sem administrador ativo promove o primeiro usuário criado.
WITH orgs_without_admin AS (
    SELECT o.id AS organization_id
    FROM organizations o
    WHERE NOT EXISTS (
        SELECT 1
        FROM actor_roles ar
        JOIN roles r ON r.id = ar.role_id AND r.code = 'administrator'
        JOIN actors a ON a.id = ar.actor_id
        WHERE a.organization_id = o.id AND a.status = 'active' AND a.kind = 'user'
    )
), first_user AS (
    SELECT DISTINCT ON (a.organization_id) a.organization_id, a.id AS actor_id
    FROM actors a
    JOIN users u ON u.actor_id = a.id
    JOIN orgs_without_admin ow ON ow.organization_id = a.organization_id
    WHERE a.kind = 'user' AND a.status = 'active'
    ORDER BY a.organization_id, u.created_at, u.id
)
INSERT INTO actor_roles (actor_id, role_id)
SELECT fu.actor_id, r.id
FROM first_user fu
JOIN roles r ON r.organization_id = fu.organization_id AND r.code = 'administrator'
ON CONFLICT DO NOTHING;
