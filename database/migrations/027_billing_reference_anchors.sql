ALTER TABLE public.contract_versions
    ADD COLUMN IF NOT EXISTS billing_anchor_competence date,
    ADD COLUMN IF NOT EXISTS billing_anchor_position integer,
    ADD COLUMN IF NOT EXISTS billing_cycle_total integer;

ALTER TABLE public.contract_versions
    ADD CONSTRAINT contract_versions_billing_cycle_consistency CHECK (
        (
            billing_anchor_competence IS NULL
            AND billing_anchor_position IS NULL
            AND billing_cycle_total IS NULL
        )
        OR (
            billing_anchor_competence IS NOT NULL
            AND billing_anchor_position IS NOT NULL
            AND billing_cycle_total IS NOT NULL
            AND billing_anchor_competence = date_trunc('month', billing_anchor_competence)::date
            AND billing_anchor_position >= 1
            AND billing_cycle_total >= 1
            AND billing_anchor_position <= billing_cycle_total
        )
    );

ALTER TABLE public.client_services
    ADD COLUMN IF NOT EXISTS installment_total integer
        CHECK (installment_total IS NULL OR installment_total >= 1);

ALTER TABLE public.client_service_occurrences
    ADD COLUMN IF NOT EXISTS installment_number integer
        CHECK (installment_number IS NULL OR installment_number >= 1);

CREATE UNIQUE INDEX IF NOT EXISTS client_service_occurrences_installment_unique
    ON public.client_service_occurrences (client_service_id, installment_number)
    WHERE installment_number IS NOT NULL;
