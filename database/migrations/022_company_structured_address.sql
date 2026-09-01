ALTER TABLE companies
    ADD COLUMN IF NOT EXISTS address_number varchar(60),
    ADD COLUMN IF NOT EXISTS address_complement varchar(255),
    ADD COLUMN IF NOT EXISTS district varchar(255);
