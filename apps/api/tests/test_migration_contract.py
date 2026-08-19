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
