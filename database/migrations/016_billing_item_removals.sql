CREATE TABLE IF NOT EXISTS billing_item_removals (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    billing_item_id uuid NOT NULL UNIQUE REFERENCES billing_items(id),
    organization_id uuid NOT NULL REFERENCES organizations(id),
    removed_by_actor_id uuid NOT NULL REFERENCES actors(id),
    reason text NOT NULL DEFAULT 'Removida manualmente no faturamento',
    correlation_id uuid NOT NULL,
    removed_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS billing_item_removals_org_item_idx
    ON billing_item_removals (organization_id, billing_item_id);

CREATE OR REPLACE FUNCTION validate_billing_item_removal_scope()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM billing_items bi
        WHERE bi.id = NEW.billing_item_id
          AND bi.organization_id = NEW.organization_id
    ) THEN
        RAISE EXCEPTION 'billing item removal belongs to another organization';
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM actors a
        WHERE a.id = NEW.removed_by_actor_id
          AND a.organization_id = NEW.organization_id
    ) THEN
        RAISE EXCEPTION 'billing item removal actor belongs to another organization';
    END IF;

    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS billing_item_removals_validate_scope ON billing_item_removals;
CREATE TRIGGER billing_item_removals_validate_scope
BEFORE INSERT ON billing_item_removals
FOR EACH ROW EXECUTE FUNCTION validate_billing_item_removal_scope();

DROP TRIGGER IF EXISTS billing_item_removals_no_update ON billing_item_removals;
CREATE TRIGGER billing_item_removals_no_update
BEFORE UPDATE ON billing_item_removals
FOR EACH ROW EXECUTE FUNCTION reject_append_only_mutation();

DROP TRIGGER IF EXISTS billing_item_removals_no_delete ON billing_item_removals;
CREATE TRIGGER billing_item_removals_no_delete
BEFORE DELETE ON billing_item_removals
FOR EACH ROW EXECUTE FUNCTION reject_append_only_mutation();

COMMENT ON TABLE billing_item_removals IS
    'Append-only record of billing items removed from operational views; the original billing item remains immutable.';
