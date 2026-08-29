ALTER TABLE legal_entities
  ADD COLUMN IF NOT EXISTS tax_regime text;

ALTER TABLE legal_entities
  DROP CONSTRAINT IF EXISTS legal_entities_tax_regime_check;

ALTER TABLE legal_entities
  ADD CONSTRAINT legal_entities_tax_regime_check
  CHECK (tax_regime IS NULL OR tax_regime IN ('simples_nacional', 'lucro_presumido'));
