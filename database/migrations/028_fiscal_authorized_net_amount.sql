ALTER TABLE public.fiscal_issuances
    ADD COLUMN IF NOT EXISTS authorized_net_amount numeric(18, 2)
    CHECK (authorized_net_amount IS NULL OR authorized_net_amount >= 0);

COMMENT ON COLUMN public.fiscal_issuances.authorized_net_amount IS
    'Valor líquido autoritativo extraído de vLiq do XML NFS-e autorizado.';

DO $$
DECLARE
    document_record record;
    net_amount_nodes xml[];
    net_amount_text text;
BEGIN
    FOR document_record IN
        SELECT fi.id AS issuance_id, fd.content_bytes
        FROM public.fiscal_issuances AS fi
        JOIN public.fiscal_documents AS fd ON fd.issuance_id = fi.id
        WHERE fi.authorized_net_amount IS NULL
          AND fd.document_type = 'nfse_xml'
          AND fd.content_bytes IS NOT NULL
    LOOP
        BEGIN
            net_amount_nodes := xpath(
                '/*[local-name()="NFSe"]/*[local-name()="infNFSe"]/*[local-name()="valores"]/*[local-name()="vLiq"]/text()',
                xmlparse(document convert_from(document_record.content_bytes, 'UTF8'))
            );
            IF cardinality(net_amount_nodes) = 1 THEN
                net_amount_text := btrim(net_amount_nodes[1]::text);
            ELSE
                net_amount_text := NULL;
            END IF;
            IF net_amount_text ~ '^[0-9]+(\.[0-9]{1,2})?$' THEN
                UPDATE public.fiscal_issuances
                SET authorized_net_amount = net_amount_text::numeric(18, 2)
                WHERE id = document_record.issuance_id
                  AND authorized_net_amount IS NULL;
            END IF;
        EXCEPTION
            WHEN OTHERS THEN
                NULL;
        END;
    END LOOP;
END;
$$;
