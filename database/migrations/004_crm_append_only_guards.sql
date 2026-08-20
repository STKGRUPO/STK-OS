CREATE OR REPLACE FUNCTION reject_append_only_mutation()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    RAISE EXCEPTION '% is append-only', TG_TABLE_NAME;
END;
$$;

CREATE TRIGGER opportunity_stage_history_no_update
BEFORE UPDATE ON opportunity_stage_history
FOR EACH ROW EXECUTE FUNCTION reject_append_only_mutation();

CREATE TRIGGER opportunity_stage_history_no_delete
BEFORE DELETE ON opportunity_stage_history
FOR EACH ROW EXECUTE FUNCTION reject_append_only_mutation();

CREATE TRIGGER crm_import_rows_no_update
BEFORE UPDATE ON crm_import_rows
FOR EACH ROW EXECUTE FUNCTION reject_append_only_mutation();

CREATE TRIGGER crm_import_rows_no_delete
BEFORE DELETE ON crm_import_rows
FOR EACH ROW EXECUTE FUNCTION reject_append_only_mutation();

COMMENT ON TABLE people IS 'Canonical people for the organization; business-unit relationships are separate.';
COMMENT ON TABLE companies IS 'Canonical companies for the organization; business-unit relationships are separate.';
COMMENT ON TABLE opportunity_stage_history IS 'Append-only stage transitions; won/lost remain opportunity statuses.';
COMMENT ON TABLE tasks IS 'The earliest future open task is the derived next action for an opportunity.';
COMMENT ON TABLE crm_import_rows IS 'Append-only per-row import evidence; source payload is represented only by SHA-256.';
