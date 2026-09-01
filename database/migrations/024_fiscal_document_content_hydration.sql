CREATE OR REPLACE FUNCTION protect_fiscal_document_update()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    IF OLD.content_bytes IS NULL
       AND NEW.content_bytes IS NOT NULL
       AND NEW.id IS NOT DISTINCT FROM OLD.id
       AND NEW.issuance_id IS NOT DISTINCT FROM OLD.issuance_id
       AND NEW.document_type IS NOT DISTINCT FROM OLD.document_type
       AND NEW.storage_key IS NOT DISTINCT FROM OLD.storage_key
       AND NEW.content_type IS NOT DISTINCT FROM OLD.content_type
       AND NEW.content_sha256 IS NOT DISTINCT FROM OLD.content_sha256
       AND NEW.size_bytes IS NOT DISTINCT FROM OLD.size_bytes
       AND NEW.status IS NOT DISTINCT FROM OLD.status
       AND NEW.error_code IS NOT DISTINCT FROM OLD.error_code
       AND NEW.created_at IS NOT DISTINCT FROM OLD.created_at
       AND OLD.size_bytes IS NOT NULL
       AND octet_length(NEW.content_bytes) = OLD.size_bytes THEN
        RETURN NEW;
    END IF;

    RAISE EXCEPTION
        'fiscal document is immutable except for initial verified content hydration';
END;
$$;

CREATE OR REPLACE TRIGGER fiscal_documents_no_update
BEFORE UPDATE ON public.fiscal_documents
FOR EACH ROW EXECUTE FUNCTION protect_fiscal_document_update();
