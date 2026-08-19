CREATE OR REPLACE FUNCTION reject_audit_mutation()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    RAISE EXCEPTION 'audit_events is append-only';
END;
$$;

DROP TRIGGER IF EXISTS audit_events_no_update ON audit_events;
CREATE TRIGGER audit_events_no_update
BEFORE UPDATE ON audit_events
FOR EACH ROW EXECUTE FUNCTION reject_audit_mutation();

DROP TRIGGER IF EXISTS audit_events_no_delete ON audit_events;
CREATE TRIGGER audit_events_no_delete
BEFORE DELETE ON audit_events
FOR EACH ROW EXECUTE FUNCTION reject_audit_mutation();

COMMENT ON TABLE audit_events IS 'Official append-only business audit trail. Never store secrets or full sensitive payloads.';
COMMENT ON TABLE inbox_events IS 'Durable, deduplicated ingress for future external events.';
COMMENT ON TABLE outbox_events IS 'Transactional event outbox; delivery state is operational, not business truth.';
COMMENT ON TABLE idempotency_keys IS 'Idempotency scope is actor + command + key; request hash prevents key reuse with different intent.';

