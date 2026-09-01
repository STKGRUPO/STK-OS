ALTER TABLE public.fiscal_establishments
    ADD COLUMN IF NOT EXISTS email varchar(320),
    ADD COLUMN IF NOT EXISTS phone varchar(50);
