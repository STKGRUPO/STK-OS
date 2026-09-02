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


def test_contract_migration_defines_versioned_append_only_domain() -> None:
    contracts = (ROOT / "database/migrations/005_versioned_contracts.sql").read_text(
        encoding="utf-8"
    )
    for table in (
        "contracts",
        "contract_versions",
        "contract_version_services",
        "contract_version_contacts",
        "contract_operational_events",
    ):
        assert f"CREATE TABLE {table}" in contracts
    assert "issuer_establishment_id" in contracts
    assert "validate_contract_version_insert" in contracts
    assert "retroactive contract version" in contracts
    assert "contract_versions_no_update" in contracts
    assert "contract_operational_events_no_delete" in contracts


def test_billing_migration_defines_idempotent_immutable_core() -> None:
    billing = (ROOT / "database/migrations/006_billing_core.sql").read_text(encoding="utf-8")
    for table in ("billing_runs", "billing_items", "billing_run_contracts"):
        assert f"CREATE TABLE {table}" in billing
    assert "UNIQUE (contract_id, competence_month)" in billing
    assert "billing item financial snapshot is immutable" in billing
    assert "billing_items_no_delete" in billing
    assert "date_trunc('month', competence_month)" in billing


def test_client_services_migration_generalizes_origin_without_rewriting_core() -> None:
    delta = (ROOT / "database/migrations/007_client_services_identity.sql").read_text(
        encoding="utf-8"
    )
    for table in ("user_access_tokens", "client_services", "client_service_occurrences"):
        assert f"CREATE TABLE {table}" in delta
    assert "ALTER TABLE billing_items ALTER COLUMN contract_id DROP NOT NULL" in delta
    assert "service_occurrence_id" in delta
    assert "billing_items_service_occurrence_unique" in delta
    assert "source_type" in delta


def test_fiscal_migration_defines_single_idempotent_issuance_and_reconciliation() -> None:
    fiscal = (ROOT / "database/migrations/008_fiscal_issuance.sql").read_text(
        encoding="utf-8"
    )
    for table in (
        "fiscal_establishment_configs",
        "fiscal_issuances",
        "fiscal_attempts",
        "fiscal_documents",
    ):
        assert f"CREATE TABLE {table}" in fiscal
    assert "billing_item_id uuid NOT NULL UNIQUE" in fiscal
    assert "next_dps_number" in fiscal
    assert "fiscal_issuances_reconcile_idx" in fiscal
    assert "fiscal issuance identity is immutable" in fiscal
    assert "certificate_secret_ref" in fiscal


def test_fiscal_document_content_migration_adds_durable_payload_storage() -> None:
    delta = (ROOT / "database/migrations/023_fiscal_document_content.sql").read_text(
        encoding="utf-8"
    )
    normalized = delta.upper()

    assert "ADD COLUMN IF NOT EXISTS CONTENT_BYTES BYTEA" in normalized
    assert "DROP " not in normalized
    assert "ALTER COLUMN" not in normalized


def test_fiscal_document_hydration_migration_keeps_metadata_append_only() -> None:
    hydration = (
        ROOT / "database/migrations/024_fiscal_document_content_hydration.sql"
    ).read_text(encoding="utf-8")
    normalized = hydration.upper()

    assert "OLD.CONTENT_BYTES IS NULL" in normalized
    assert "NEW.CONTENT_BYTES IS NOT NULL" in normalized
    assert "OCTET_LENGTH(NEW.CONTENT_BYTES) = OLD.SIZE_BYTES" in normalized
    for column in (
        "ID",
        "ISSUANCE_ID",
        "DOCUMENT_TYPE",
        "STORAGE_KEY",
        "CONTENT_TYPE",
        "CONTENT_SHA256",
        "SIZE_BYTES",
        "STATUS",
        "ERROR_CODE",
        "CREATED_AT",
    ):
        assert f"NEW.{column} IS NOT DISTINCT FROM OLD.{column}" in normalized
    assert "CREATE EXTENSION" not in normalized
    assert "DROP TRIGGER" not in normalized
    assert "DELETE FROM" not in normalized


def test_fiscal_establishment_contacts_migration_is_additive() -> None:
    delta = (ROOT / "database/migrations/025_fiscal_establishment_contacts.sql").read_text(
        encoding="utf-8"
    )
    normalized = delta.upper()

    assert "ADD COLUMN IF NOT EXISTS EMAIL VARCHAR(320)" in normalized
    assert "ADD COLUMN IF NOT EXISTS PHONE VARCHAR(50)" in normalized
    assert "DROP " not in normalized
    assert "DELETE " not in normalized
    assert "UPDATE " not in normalized


def test_legal_entity_contacts_migration_is_additive() -> None:
    delta = (ROOT / "database/migrations/026_legal_entity_contacts.sql").read_text(
        encoding="utf-8"
    )
    normalized = delta.upper()

    assert "ALTER TABLE PUBLIC.LEGAL_ENTITIES" in normalized
    assert "ADD COLUMN IF NOT EXISTS EMAIL VARCHAR(320)" in normalized
    assert "ADD COLUMN IF NOT EXISTS PHONE VARCHAR(50)" in normalized
    assert "DROP " not in normalized
    assert "DELETE " not in normalized
    assert "UPDATE " not in normalized


def test_billing_reference_anchor_migration_is_additive_and_consistent() -> None:
    delta = (ROOT / "database/migrations/027_billing_reference_anchors.sql").read_text(
        encoding="utf-8"
    )
    normalized = delta.upper()

    for column in (
        "BILLING_ANCHOR_COMPETENCE",
        "BILLING_ANCHOR_POSITION",
        "BILLING_CYCLE_TOTAL",
        "INSTALLMENT_TOTAL",
        "INSTALLMENT_NUMBER",
    ):
        assert column in normalized
    assert "BILLING_ANCHOR_POSITION <= BILLING_CYCLE_TOTAL" in normalized
    assert "CLIENT_SERVICE_OCCURRENCES_INSTALLMENT_UNIQUE" in normalized
    assert "DROP " not in normalized
    assert "DELETE " not in normalized


def test_fiscal_authorized_net_amount_migration_is_additive_and_idempotent() -> None:
    delta = (
        ROOT / "database/migrations/028_fiscal_authorized_net_amount.sql"
    ).read_text(encoding="utf-8")
    normalized = delta.upper()

    assert "ALTER TABLE PUBLIC.FISCAL_ISSUANCES" in normalized
    assert "ADD COLUMN IF NOT EXISTS AUTHORIZED_NET_AMOUNT NUMERIC(18, 2)" in normalized
    assert "FI.AUTHORIZED_NET_AMOUNT IS NULL" in normalized
    assert "FD.DOCUMENT_TYPE = 'NFSE_XML'" in normalized
    assert "FD.CONTENT_BYTES IS NOT NULL" in normalized
    assert "XPATH(" in normalized
    assert "LOCAL-NAME()=\"VLIQ\"" in normalized
    assert "VLIQ" in normalized
    assert "DROP " not in normalized
    assert "DELETE " not in normalized
