INSERT INTO roles (organization_id, code, name)
SELECT organizations.id, 'user', 'Usuário padrão'
FROM organizations
ON CONFLICT (organization_id, code) DO NOTHING;
