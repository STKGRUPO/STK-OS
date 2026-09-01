ALTER TABLE public.fiscal_documents
    ADD COLUMN IF NOT EXISTS content_bytes bytea;

COMMENT ON COLUMN public.fiscal_documents.content_bytes IS
    'Conteúdo imutável do documento fiscal; persistido no PostgreSQL para não depender do filesystem efêmero do runtime.';
