-- Permite revalidar itens bloqueados: blocked -> ready/cancelled e reescrita do motivo.
-- O snapshot financeiro segue imutável.
CREATE OR REPLACE FUNCTION protect_billing_item_history()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    IF NEW.organization_id IS DISTINCT FROM OLD.organization_id
       OR NEW.business_unit_id IS DISTINCT FROM OLD.business_unit_id
       OR NEW.created_by_run_id IS DISTINCT FROM OLD.created_by_run_id
       OR NEW.contract_id IS DISTINCT FROM OLD.contract_id
       OR NEW.competence_month IS DISTINCT FROM OLD.competence_month
       OR NEW.customer_company_id IS DISTINCT FROM OLD.customer_company_id
       OR NEW.snapshot IS DISTINCT FROM OLD.snapshot
       OR NEW.snapshot_sha256 IS DISTINCT FROM OLD.snapshot_sha256
       OR NEW.correlation_id IS DISTINCT FROM OLD.correlation_id
       OR NEW.causation_id IS DISTINCT FROM OLD.causation_id
       OR NEW.created_by_actor_id IS DISTINCT FROM OLD.created_by_actor_id
       OR NEW.created_at IS DISTINCT FROM OLD.created_at THEN
        RAISE EXCEPTION 'billing item financial snapshot is immutable';
    END IF;

    IF OLD.status <> 'blocked' AND (
           NEW.contract_version_id IS DISTINCT FROM OLD.contract_version_id
        OR NEW.issuer_establishment_id IS DISTINCT FROM OLD.issuer_establishment_id
        OR NEW.currency IS DISTINCT FROM OLD.currency
        OR NEW.gross_amount IS DISTINCT FROM OLD.gross_amount
        OR NEW.blocking_code IS DISTINCT FROM OLD.blocking_code
        OR NEW.blocking_reason IS DISTINCT FROM OLD.blocking_reason
    ) THEN
        RAISE EXCEPTION 'billing item financial snapshot is immutable';
    END IF;

    IF (OLD.status, NEW.status) NOT IN (
        ('ready', 'ready'), ('ready', 'requested'),
        ('requested', 'requested'), ('requested', 'completed'),
        ('blocked', 'blocked'), ('blocked', 'ready'), ('blocked', 'cancelled'),
        ('ready', 'cancelled'), ('requested', 'cancelled'),
        ('cancelled', 'cancelled'), ('completed', 'completed')
    ) THEN
        RAISE EXCEPTION 'invalid billing item state transition';
    END IF;

    NEW.updated_at := now();
    RETURN NEW;
END;
$$;
