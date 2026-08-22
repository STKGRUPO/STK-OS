UPDATE roles
SET name = 'Administrador do Grupo'
WHERE code = 'administrator';

INSERT INTO roles (organization_id, code, name)
SELECT organizations.id, profiles.code, profiles.name
FROM organizations
CROSS JOIN (
    VALUES
        ('unit_manager', 'Gestor de Unidade'),
        ('operational', 'Operacional'),
        ('financial', 'Financeiro')
) AS profiles(code, name)
ON CONFLICT (organization_id, code) DO UPDATE SET name = EXCLUDED.name;

INSERT INTO role_permissions (role_id, permission_id)
SELECT roles.id, permissions.id
FROM roles
JOIN permissions ON (
    roles.code = 'unit_manager'
    AND permissions.code IN (
        'organization:read', 'audit:read', 'crm:read', 'crm:write', 'crm:import',
        'contracts:read', 'contracts:create', 'contracts:update', 'contracts:version',
        'contracts:suspend', 'contracts:resume', 'contracts:terminate',
        'billing:read', 'billing:generate', 'billing:review', 'billing:reprocess',
        'services:read', 'services:write', 'fiscal:read', 'fiscal:issue', 'fiscal:reconcile'
    )
)
OR (
    roles.code = 'operational'
    AND permissions.code IN (
        'organization:read', 'crm:read', 'crm:write', 'contracts:read',
        'services:read', 'services:write'
    )
)
OR (
    roles.code = 'financial'
    AND permissions.code IN (
        'organization:read', 'crm:read', 'contracts:read', 'billing:read',
        'billing:generate', 'billing:review', 'billing:reprocess',
        'fiscal:read', 'fiscal:issue', 'fiscal:reconcile'
    )
)
ON CONFLICT DO NOTHING;
