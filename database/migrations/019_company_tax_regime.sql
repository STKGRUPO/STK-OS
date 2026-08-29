ALTER TABLE companies
  ADD COLUMN IF NOT EXISTS tax_regime text;

ALTER TABLE companies
  DROP CONSTRAINT IF EXISTS companies_tax_regime_check;

ALTER TABLE companies
  ADD CONSTRAINT companies_tax_regime_check
  CHECK (tax_regime IS NULL OR tax_regime IN ('simples_nacional', 'lucro_presumido'));
