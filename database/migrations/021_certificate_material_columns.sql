ALTER TABLE public.fiscal_certificates
    ADD COLUMN IF NOT EXISTS alias                text,
    ADD COLUMN IF NOT EXISTS certificate_key_id   text,
    ADD COLUMN IF NOT EXISTS material_ciphertext  bytea,
    ADD COLUMN IF NOT EXISTS material_nonce       bytea,
    ADD COLUMN IF NOT EXISTS password_ciphertext  bytea,
    ADD COLUMN IF NOT EXISTS password_nonce       bytea;

ALTER TABLE public.fiscal_certificates
    ALTER COLUMN secret_ref SET DEFAULT 'db://fiscal_certificates';

CREATE INDEX IF NOT EXISTS fiscal_certificates_key_idx
    ON public.fiscal_certificates (certificate_key_id);
