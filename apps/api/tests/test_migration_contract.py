from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def test_migrations_define_foundation_and_append_only_guard() -> None:
    foundation = (ROOT / "database/migrations/001_foundation.sql").read_text(encoding="utf-8")
    guards = (ROOT / "database/migrations/002_append_only_guards.sql").read_text(encoding="utf-8")
    for table in (
        "organizations",
        "legal_entities",
        "fiscal_establishments",
        "business_units",
        "users",
        "service_accounts",
        "audit_events",
        "idempotency_keys",
        "inbox_events",
        "outbox_events",
        "exceptions",
    ):
        assert f"CREATE TABLE {table}" in foundation
    assert "audit_events_no_update" in guards
    assert "audit_events_no_delete" in guards


def test_crm_migrations_define_vertical_and_append_only_history() -> None:
    crm = (ROOT / "database/migrations/003_crm_vertical.sql").read_text(encoding="utf-8")
    guards = (ROOT / "database/migrations/004_crm_append_only_guards.sql").read_text(
        encoding="utf-8"
    )
    for table in (
        "people",
        "contact_methods",
        "companies",
        "person_company_relationships",
        "person_business_units",
        "company_business_units",
        "products_services",
        "lead_sources",
        "loss_reasons",
        "pipelines",
        "pipeline_stages",
        "opportunities",
        "opportunity_contacts",
        "opportunity_stage_history",
        "activities",
        "tasks",
        "crm_import_jobs",
        "crm_import_rows",
    ):
        assert f"CREATE TABLE {table}" in crm
    assert "opportunity_stage_history_no_update" in guards
    assert "opportunity_stage_history_no_delete" in guards
    assert "crm_import_rows_no_update" in guards
