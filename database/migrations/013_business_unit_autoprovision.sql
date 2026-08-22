INSERT INTO fiscal_establishments (legal_entity_id, code, name, kind, tax_id, status)
SELECT le.id, 'matriz', COALESCE(le.trade_name, le.registered_name), 'headquarters', le.tax_id, le.status
FROM legal_entities le
WHERE NOT EXISTS (SELECT 1 FROM fiscal_establishments fe WHERE fe.legal_entity_id = le.id);

INSERT INTO business_units (organization_id, primary_establishment_id, code, name, status)
SELECT le.organization_id, fe.id, le.code, COALESCE(le.trade_name, le.registered_name), le.status
FROM legal_entities le
JOIN fiscal_establishments fe ON fe.legal_entity_id = le.id AND fe.code = 'matriz'
WHERE NOT EXISTS (
  SELECT 1 FROM business_units bu
  JOIN fiscal_establishments fe2 ON fe2.id = bu.primary_establishment_id
  WHERE fe2.legal_entity_id = le.id
)
ON CONFLICT (organization_id, code) DO NOTHING;

SELECT name, status FROM business_units ORDER BY name;
