ALTER TABLE core.companies
  ADD COLUMN IF NOT EXISTS tax_regime text
  CHECK (tax_regime IN ('simples_nacional','lucro_presumido','lucro_real','mei'));
