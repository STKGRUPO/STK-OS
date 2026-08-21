INSERT INTO permissions (code, description)
VALUES
    ('crm:read', 'Consultar dados canônicos e operação do CRM'),
    ('crm:write', 'Criar e alterar registros permitidos do CRM'),
    ('crm:import', 'Executar importação pequena e auditável no CRM')
ON CONFLICT (code) DO NOTHING;

INSERT INTO role_permissions (role_id, permission_id)
SELECT '50000000-0000-4000-8000-000000000001', id
FROM permissions
WHERE code IN ('crm:read', 'crm:write', 'crm:import')
ON CONFLICT DO NOTHING;

INSERT INTO role_permissions (role_id, permission_id)
SELECT '50000000-0000-4000-8000-000000000002', id
FROM permissions
WHERE code IN ('crm:read', 'crm:write')
ON CONFLICT DO NOTHING;

INSERT INTO lead_sources (id, organization_id, code, name)
VALUES
    ('71000000-0000-4000-8000-000000000001', '10000000-0000-4000-8000-000000000001', 'indicacao', 'Indicação'),
    ('71000000-0000-4000-8000-000000000002', '10000000-0000-4000-8000-000000000001', 'whatsapp', 'WhatsApp'),
    ('71000000-0000-4000-8000-000000000003', '10000000-0000-4000-8000-000000000001', 'site', 'Site'),
    ('71000000-0000-4000-8000-000000000004', '10000000-0000-4000-8000-000000000001', 'base-sintetica', 'Base sintética'),
    ('71000000-0000-4000-8000-000000000005', '10000000-0000-4000-8000-000000000001', 'outro', 'Outro')
ON CONFLICT (organization_id, code) DO NOTHING;

INSERT INTO products_services (id, organization_id, business_unit_id, code, name, category)
VALUES
    ('72000000-0000-4000-8000-000000000001', '10000000-0000-4000-8000-000000000001', '40000000-0000-4000-8000-000000000001', 'ambiental', 'Consultoria Ambiental', 'Ambiental'),
    ('72000000-0000-4000-8000-000000000002', '10000000-0000-4000-8000-000000000001', '40000000-0000-4000-8000-000000000001', 'regulatorio', 'Assuntos Regulatórios', 'Regulatório'),
    ('72000000-0000-4000-8000-000000000003', '10000000-0000-4000-8000-000000000001', '40000000-0000-4000-8000-000000000002', 'orcamento-comercial', 'Orçamento comercial', 'Comercial'),
    ('72000000-0000-4000-8000-000000000004', '10000000-0000-4000-8000-000000000001', '40000000-0000-4000-8000-000000000003', 'b2c', 'Consultoria Stelli B2C', 'B2C'),
    ('72000000-0000-4000-8000-000000000005', '10000000-0000-4000-8000-000000000001', '40000000-0000-4000-8000-000000000003', 'b2b', 'Solução Stelli B2B', 'B2B')
ON CONFLICT (business_unit_id, code) DO NOTHING;

INSERT INTO loss_reasons (id, organization_id, business_unit_id, code, name)
SELECT gen_random_uuid(), '10000000-0000-4000-8000-000000000001', unit.id, reason.code, reason.name
FROM business_units AS unit
CROSS JOIN (
    VALUES
        ('preco', 'Preço'),
        ('sem-retorno', 'Sem retorno'),
        ('nao-contratou', 'Decidiu não contratar'),
        ('concorrente', 'Concorrente'),
        ('prazo', 'Prazo'),
        ('solucao-inadequada', 'Solução não adequada'),
        ('adiamento', 'Adiamento'),
        ('orcamento-nao-aprovado', 'Orçamento não aprovado'),
        ('outro', 'Outro')
) AS reason(code, name)
WHERE unit.organization_id = '10000000-0000-4000-8000-000000000001'
ON CONFLICT (business_unit_id, code) DO NOTHING;

INSERT INTO pipelines (id, organization_id, business_unit_id, code, name)
VALUES
    ('73000000-0000-4000-8000-000000000001', '10000000-0000-4000-8000-000000000001', '40000000-0000-4000-8000-000000000001', 'comercial', 'Pipeline comercial MR'),
    ('73000000-0000-4000-8000-000000000002', '10000000-0000-4000-8000-000000000001', '40000000-0000-4000-8000-000000000002', 'comercial', 'Pipeline comercial STK Lab'),
    ('73000000-0000-4000-8000-000000000003', '10000000-0000-4000-8000-000000000001', '40000000-0000-4000-8000-000000000003', 'b2c', 'Pipeline Stelli B2C'),
    ('73000000-0000-4000-8000-000000000004', '10000000-0000-4000-8000-000000000001', '40000000-0000-4000-8000-000000000003', 'b2b', 'Pipeline Stelli B2B')
ON CONFLICT (business_unit_id, code) DO NOTHING;

INSERT INTO pipeline_stages (id, pipeline_id, code, name, position, sla_days)
VALUES
    ('74000000-0000-4000-8000-000000000001', '73000000-0000-4000-8000-000000000001', 'lead', 'Lead', 1, 2),
    ('74000000-0000-4000-8000-000000000002', '73000000-0000-4000-8000-000000000001', 'qualificacao', 'Qualificação', 2, 3),
    ('74000000-0000-4000-8000-000000000003', '73000000-0000-4000-8000-000000000001', 'demanda', 'Demanda identificada', 3, 4),
    ('74000000-0000-4000-8000-000000000004', '73000000-0000-4000-8000-000000000001', 'proposta', 'Proposta', 4, 5),
    ('74000000-0000-4000-8000-000000000005', '73000000-0000-4000-8000-000000000001', 'follow-up', 'Follow-up', 5, 4),
    ('74000000-0000-4000-8000-000000000006', '73000000-0000-4000-8000-000000000001', 'negociacao', 'Negociação', 6, 5),
    ('74000000-0000-4000-8000-000000000011', '73000000-0000-4000-8000-000000000002', 'novo-contato', 'Novo contato', 1, 1),
    ('74000000-0000-4000-8000-000000000012', '73000000-0000-4000-8000-000000000002', 'necessidade', 'Necessidade identificada', 2, 1),
    ('74000000-0000-4000-8000-000000000013', '73000000-0000-4000-8000-000000000002', 'orcamento', 'Orçamento', 3, 2),
    ('74000000-0000-4000-8000-000000000014', '73000000-0000-4000-8000-000000000002', 'aguardando', 'Aguardando cliente', 4, 3),
    ('74000000-0000-4000-8000-000000000015', '73000000-0000-4000-8000-000000000002', 'agendamento', 'Agendamento', 5, 2),
    ('74000000-0000-4000-8000-000000000021', '73000000-0000-4000-8000-000000000003', 'lead', 'Lead', 1, 2),
    ('74000000-0000-4000-8000-000000000022', '73000000-0000-4000-8000-000000000003', 'necessidade', 'Necessidade identificada', 2, 3),
    ('74000000-0000-4000-8000-000000000023', '73000000-0000-4000-8000-000000000003', 'recomendacao', 'Produto recomendado', 3, 3),
    ('74000000-0000-4000-8000-000000000024', '73000000-0000-4000-8000-000000000003', 'oferta', 'Lista de espera / oferta', 4, 5),
    ('74000000-0000-4000-8000-000000000025', '73000000-0000-4000-8000-000000000003', 'follow-up', 'Follow-up', 5, 4),
    ('74000000-0000-4000-8000-000000000031', '73000000-0000-4000-8000-000000000004', 'lead-empresa', 'Lead empresa', 1, 3),
    ('74000000-0000-4000-8000-000000000032', '73000000-0000-4000-8000-000000000004', 'qualificacao', 'Qualificação', 2, 3),
    ('74000000-0000-4000-8000-000000000033', '73000000-0000-4000-8000-000000000004', 'diagnostico', 'Diagnóstico', 3, 5),
    ('74000000-0000-4000-8000-000000000034', '73000000-0000-4000-8000-000000000004', 'proposta', 'Proposta', 4, 5),
    ('74000000-0000-4000-8000-000000000035', '73000000-0000-4000-8000-000000000004', 'follow-up', 'Follow-up', 5, 4),
    ('74000000-0000-4000-8000-000000000036', '73000000-0000-4000-8000-000000000004', 'negociacao', 'Negociação', 6, 5)
ON CONFLICT (pipeline_id, code) DO NOTHING;

INSERT INTO permissions (code, description)
VALUES
    ('contracts:read', 'Consultar contratos, versões e configuração histórica'),
    ('contracts:create', 'Criar a identidade administrativa de contratos'),
    ('contracts:update', 'Alterar somente metadados administrativos permitidos'),
    ('contracts:version', 'Publicar e programar versões contratuais imutáveis'),
    ('contracts:suspend', 'Suspender contrato por evento operacional'),
    ('contracts:resume', 'Retomar contrato por evento operacional'),
    ('contracts:terminate', 'Encerrar contrato por evento operacional')
ON CONFLICT (code) DO NOTHING;

INSERT INTO role_permissions (role_id, permission_id)
SELECT '50000000-0000-4000-8000-000000000001', id
FROM permissions
WHERE code LIKE 'contracts:%'
ON CONFLICT DO NOTHING;

INSERT INTO role_permissions (role_id, permission_id)
SELECT '50000000-0000-4000-8000-000000000002', id
FROM permissions
WHERE code = 'contracts:read'
ON CONFLICT DO NOTHING;

INSERT INTO permissions (code, description)
VALUES
    ('billing:read', 'Consultar execuções e obrigações de faturamento'),
    ('billing:generate', 'Gerar competência de faturamento de forma idempotente'),
    ('billing:review', 'Revisar bloqueios e exceções de faturamento'),
    ('billing:reprocess', 'Reexecutar somente operação de faturamento tecnicamente segura')
ON CONFLICT (code) DO NOTHING;

INSERT INTO role_permissions (role_id, permission_id)
SELECT '50000000-0000-4000-8000-000000000001', id
FROM permissions
WHERE code LIKE 'billing:%'
ON CONFLICT DO NOTHING;

INSERT INTO role_permissions (role_id, permission_id)
SELECT '50000000-0000-4000-8000-000000000002', id
FROM permissions
WHERE code IN ('billing:read', 'billing:generate')
ON CONFLICT DO NOTHING;
