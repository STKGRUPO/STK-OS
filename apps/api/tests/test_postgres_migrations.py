from __future__ import annotations

import hashlib
import os
import uuid
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from pathlib import Path

import psycopg
import pytest
from psycopg import errors

ROOT = Path(__file__).resolve().parents[3]
MIGRATIONS = ROOT / "database" / "migrations"
SEEDS = ROOT / "database" / "seeds"
EXPECTED_MIGRATIONS = [
    "001_foundation.sql",
    "002_append_only_guards.sql",
    "003_crm_vertical.sql",
    "004_crm_append_only_guards.sql",
    "005_versioned_contracts.sql",
    "006_billing_core.sql",
    "007_client_services_identity.sql",
    "008_fiscal_issuance.sql",
    "009_identity_password_state.sql",
    "010_public_registration_role.sql",
    "011_basic_administration_profiles.sql",
    "012_permission_catalog_and_admin.sql",
    "013_business_unit_autoprovision.sql",
    "014_fiscal_certificates.sql",
    "015_certificate_material.sql",
    "016_billing_item_removals.sql",
    "017_service_code_catalog.sql",
    "018_billing_item_revalidation.sql",
    "019_company_tax_regime.sql",
    "020_legal_entity_tax_regime.sql",
    "021_certificate_material_columns.sql",
    "022_company_structured_address.sql",
    "023_fiscal_document_content.sql",
    "024_fiscal_document_content_hydration.sql",
    "025_fiscal_establishment_contacts.sql",
    "026_legal_entity_contacts.sql",
    "027_billing_reference_anchors.sql",
    "028_fiscal_authorized_net_amount.sql",
]


def postgres_test_url() -> str:
    url = os.getenv("STK_TEST_DATABASE_URL")
    if not url:
        pytest.skip("STK_TEST_DATABASE_URL não configurada")
    if url.startswith("postgresql+psycopg://"):
        url = url.replace("postgresql+psycopg://", "postgresql://", 1)
    parameters = psycopg.conninfo.conninfo_to_dict(url)
    if not parameters.get("dbname", "").endswith("_test"):
        pytest.fail("STK_TEST_DATABASE_URL deve apontar para banco terminado em _test")
    return url


def apply_foundation(connection: psycopg.Connection[tuple[object, ...]]) -> list[str]:
    connection.execute("DROP SCHEMA public CASCADE")
    connection.execute("CREATE SCHEMA public")
    applied: list[str] = []
    for path in sorted(MIGRATIONS.glob("*.sql")):
        content = path.read_bytes()
        connection.execute(content.decode("utf-8"))
        connection.execute(
            "INSERT INTO schema_migrations (version, checksum_sha256) VALUES (%s, %s)",
            (path.name, hashlib.sha256(content).hexdigest()),
        )
        applied.append(path.name)
    for _ in range(2):
        for path in sorted(SEEDS.glob("*.sql")):
            connection.execute(path.read_text(encoding="utf-8"))
    return applied


@pytest.mark.postgres
def test_postgres_foundation_invariants() -> None:
    with psycopg.connect(postgres_test_url(), autocommit=True) as connection:
        applied = apply_foundation(connection)
        assert applied == EXPECTED_MIGRATIONS

        expected_checksums = [
            (path.name, hashlib.sha256(path.read_bytes()).hexdigest())
            for path in sorted(MIGRATIONS.glob("*.sql"))
        ]
        stored_checksums = connection.execute(
            "SELECT version, checksum_sha256 FROM schema_migrations ORDER BY applied_at, version"
        ).fetchall()
        assert stored_checksums == expected_checksums

        tables = {
            row[0]
            for row in connection.execute(
                "SELECT tablename FROM pg_tables WHERE schemaname = 'public'"
            )
        }
        assert {
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
            "contracts",
            "contract_versions",
            "contract_version_services",
            "contract_version_contacts",
            "contract_operational_events",
            "billing_runs",
            "billing_items",
            "billing_run_contracts",
            "user_access_tokens",
            "client_services",
            "client_service_occurrences",
            "fiscal_establishment_configs",
            "fiscal_issuances",
            "fiscal_attempts",
            "fiscal_documents",
        } <= tables

        billing_reference_columns = set(
            connection.execute(
                """
                SELECT table_name, column_name, data_type, is_nullable
                FROM information_schema.columns
                WHERE table_schema = 'public'
                  AND (table_name, column_name) IN (
                      ('contract_versions', 'billing_anchor_competence'),
                      ('contract_versions', 'billing_anchor_position'),
                      ('contract_versions', 'billing_cycle_total'),
                      ('client_services', 'installment_total'),
                      ('client_service_occurrences', 'installment_number')
                  )
                """
            ).fetchall()
        )
        assert billing_reference_columns == {
            ("contract_versions", "billing_anchor_competence", "date", "YES"),
            ("contract_versions", "billing_anchor_position", "integer", "YES"),
            ("contract_versions", "billing_cycle_total", "integer", "YES"),
            ("client_services", "installment_total", "integer", "YES"),
            ("client_service_occurrences", "installment_number", "integer", "YES"),
        }
        reference_constraints = {
            row[0]: row[1]
            for row in connection.execute(
                """
                SELECT conname, pg_get_constraintdef(oid)
                FROM pg_constraint
                WHERE conrelid IN (
                    'contract_versions'::regclass,
                    'client_services'::regclass,
                    'client_service_occurrences'::regclass
                )
                  AND contype = 'c'
                """
            )
        }
        cycle_check = reference_constraints["contract_versions_billing_cycle_consistency"]
        assert "billing_anchor_competence IS NULL" in cycle_check
        assert "billing_anchor_position IS NOT NULL" in cycle_check
        assert "billing_cycle_total IS NOT NULL" in cycle_check
        assert "billing_anchor_position <= billing_cycle_total" in cycle_check
        assert any(
            "installment_total" in definition and ">= 1" in definition
            for definition in reference_constraints.values()
        )
        assert any(
            "installment_number" in definition and ">= 1" in definition
            for definition in reference_constraints.values()
        )
        installment_index = connection.execute(
            """
            SELECT indexdef
            FROM pg_indexes
            WHERE schemaname = 'public'
              AND indexname = 'client_service_occurrences_installment_unique'
            """
        ).fetchone()
        assert installment_index is not None
        assert "UNIQUE" in installment_index[0]
        assert "client_service_id, installment_number" in installment_index[0]

        seed_counts = connection.execute(
            """
            SELECT
                (SELECT count(*) FROM organizations),
                (SELECT count(*) FROM legal_entities),
                (SELECT count(*) FROM fiscal_establishments),
                (SELECT count(*) FROM business_units),
                (SELECT count(*) FROM lead_sources),
                (SELECT count(*) FROM products_services),
                (SELECT count(*) FROM pipelines),
                (SELECT count(*) FROM pipeline_stages),
                (SELECT count(*) FROM loss_reasons)
            """
        ).fetchone()
        assert seed_counts == (1, 3, 4, 3, 5, 5, 4, 22, 27)

        organization_id = uuid.UUID("10000000-0000-4000-8000-000000000001")
        unit_id = uuid.UUID("40000000-0000-4000-8000-000000000001")
        actor_id = uuid.uuid4()
        correlation_id = uuid.uuid4()
        connection.execute(
            """
            INSERT INTO actors (id, organization_id, kind, display_name)
            VALUES (%s, %s, 'service_account', 'Integração PostgreSQL sintética')
            """,
            (actor_id, organization_id),
        )

        audit_id = uuid.uuid4()
        connection.execute(
            """
            INSERT INTO audit_events (
                id, organization_id, actor_id, correlation_id, action,
                resource_type, resource_id, after_state
            ) VALUES (%s, %s, %s, %s, 'foundation.checked', 'business_unit', %s, %s)
            """,
            (audit_id, organization_id, actor_id, correlation_id, unit_id, '{"ok": true}'),
        )
        with pytest.raises(errors.RaiseException, match="append-only"):
            connection.execute(
                "UPDATE audit_events SET action = 'changed' WHERE id = %s", (audit_id,)
            )
        with pytest.raises(errors.RaiseException, match="append-only"):
            connection.execute("DELETE FROM audit_events WHERE id = %s", (audit_id,))

        with pytest.raises(errors.UniqueViolation):
            connection.execute(
                "INSERT INTO organizations (code, name) VALUES ('grupo-stk', 'Duplicado')"
            )

        inbox_id = uuid.uuid4()
        connection.execute(
            """
            INSERT INTO inbox_events (
                id, organization_id, source, external_event_id, event_type,
                payload, payload_sha256, correlation_id
            ) VALUES (%s, %s, 'postgres-test', 'event-1', 'foundation.test.v1', %s, %s, %s)
            """,
            (inbox_id, organization_id, '{"synthetic": true}', "0" * 64, correlation_id),
        )
        with pytest.raises(errors.UniqueViolation):
            connection.execute(
                """
                INSERT INTO inbox_events (
                    organization_id, source, external_event_id, event_type,
                    payload, payload_sha256, correlation_id
                ) VALUES (%s, 'postgres-test', 'event-1', 'foundation.test.v1', %s, %s, %s)
                """,
                (organization_id, "{}", "1" * 64, correlation_id),
            )

        connection.execute(
            """
            INSERT INTO outbox_events (
                organization_id, aggregate_type, aggregate_id,
                event_type, payload, correlation_id
            ) VALUES (%s, 'business_unit', %s, 'foundation.checked.v1', %s, %s)
            """,
            (organization_id, unit_id, '{"synthetic": true}', correlation_id),
        )

        idempotency_id = uuid.uuid4()
        idempotency_values = (
            idempotency_id,
            actor_id,
            "foundation.check",
            "synthetic-key",
            "2" * 64,
            correlation_id,
        )
        connection.execute(
            """
            INSERT INTO idempotency_keys (
                id, actor_id, command_name, idempotency_key,
                request_hash, correlation_id, expires_at
            ) VALUES (%s, %s, %s, %s, %s, %s, now() + interval '1 hour')
            """,
            idempotency_values,
        )
        with pytest.raises(errors.UniqueViolation):
            connection.execute(
                """
                INSERT INTO idempotency_keys (
                    actor_id, command_name, idempotency_key,
                    request_hash, correlation_id, expires_at
                ) VALUES (%s, %s, %s, %s, %s, now() + interval '1 hour')
                """,
                idempotency_values[1:],
            )

        exception_id = uuid.uuid4()
        connection.execute(
            """
            INSERT INTO exceptions (
                id, organization_id, actor_id, correlation_id,
                exception_type, severity, title, context
            ) VALUES (%s, %s, %s, %s, 'foundation.test', 'medium', 'Sintética', %s)
            """,
            (exception_id, organization_id, actor_id, correlation_id, '{"code": "E_TEST"}'),
        )
        with pytest.raises(errors.CheckViolation):
            connection.execute(
                """
                INSERT INTO exceptions (
                    organization_id, correlation_id, exception_type, severity, title
                ) VALUES (%s, %s, 'foundation.invalid', 'invalid', 'Inválida')
                """,
                (organization_id, correlation_id),
            )

        control_counts = connection.execute(
            """
            SELECT
                (SELECT count(*) FROM audit_events),
                (SELECT count(*) FROM inbox_events),
                (SELECT count(*) FROM outbox_events),
                (SELECT count(*) FROM idempotency_keys),
                (SELECT count(*) FROM exceptions)
            """
        ).fetchone()
        assert control_counts == (1, 1, 1, 1, 1)

        person_id = uuid.uuid4()
        company_id = uuid.uuid4()
        opportunity_id = uuid.uuid4()
        stage_history_id = uuid.uuid4()
        import_job_id = uuid.uuid4()
        import_row_id = uuid.uuid4()
        mr_pipeline_id = uuid.UUID("73000000-0000-4000-8000-000000000001")
        mr_stage_id = uuid.UUID("74000000-0000-4000-8000-000000000001")
        lab_stage_id = uuid.UUID("74000000-0000-4000-8000-000000000011")
        source_id = uuid.UUID("71000000-0000-4000-8000-000000000001")

        connection.execute(
            """
            INSERT INTO people (
                id, organization_id, full_name, tax_id, created_by_actor_id
            ) VALUES (%s, %s, 'Pessoa PostgreSQL sintética', '12345678901', %s)
            """,
            (person_id, organization_id, actor_id),
        )
        with pytest.raises(errors.UniqueViolation):
            connection.execute(
                """
                INSERT INTO people (organization_id, full_name, tax_id)
                VALUES (%s, 'Pessoa duplicada', '12345678901')
                """,
                (organization_id,),
            )
        connection.execute(
            """
            INSERT INTO companies (
                id, organization_id, legal_name, tax_id, created_by_actor_id
            ) VALUES (%s, %s, 'Empresa PostgreSQL sintética', '12345678000199', %s)
            """,
            (company_id, organization_id, actor_id),
        )
        for linked_unit_id in (
            unit_id,
            uuid.UUID("40000000-0000-4000-8000-000000000002"),
            uuid.UUID("40000000-0000-4000-8000-000000000003"),
        ):
            connection.execute(
                """
                INSERT INTO person_business_units (
                    organization_id, person_id, business_unit_id, lead_source_id, owner_actor_id
                ) VALUES (%s, %s, %s, %s, %s)
                """,
                (organization_id, person_id, linked_unit_id, source_id, actor_id),
            )
        with pytest.raises(errors.UniqueViolation):
            connection.execute(
                """
                INSERT INTO person_business_units (
                    organization_id, person_id, business_unit_id, owner_actor_id
                ) VALUES (%s, %s, %s, %s)
                """,
                (organization_id, person_id, unit_id, actor_id),
            )
        connection.execute(
            """
            INSERT INTO company_business_units (
                organization_id, company_id, business_unit_id, lead_source_id, owner_actor_id
            ) VALUES (%s, %s, %s, %s, %s)
            """,
            (organization_id, company_id, unit_id, source_id, actor_id),
        )
        connection.execute(
            """
            INSERT INTO person_company_relationships (
                organization_id, person_id, company_id, role, is_primary
            ) VALUES (%s, %s, %s, 'responsável sintético', true)
            """,
            (organization_id, person_id, company_id),
        )
        connection.execute(
            """
            INSERT INTO opportunities (
                id, organization_id, business_unit_id, pipeline_id, stage_id,
                company_id, title, lead_source_id, owner_actor_id
            ) VALUES (%s, %s, %s, %s, %s, %s, 'Negócio PostgreSQL sintético', %s, %s)
            """,
            (
                opportunity_id,
                organization_id,
                unit_id,
                mr_pipeline_id,
                mr_stage_id,
                company_id,
                source_id,
                actor_id,
            ),
        )
        connection.execute(
            """
            INSERT INTO opportunity_contacts (opportunity_id, person_id, is_primary)
            VALUES (%s, %s, true)
            """,
            (opportunity_id, person_id),
        )
        connection.execute(
            """
            INSERT INTO opportunity_stage_history (
                id, organization_id, opportunity_id, to_stage_id, actor_id, source
            ) VALUES (%s, %s, %s, %s, %s, 'api')
            """,
            (stage_history_id, organization_id, opportunity_id, mr_stage_id, actor_id),
        )
        connection.execute(
            """
            INSERT INTO tasks (
                organization_id, business_unit_id, opportunity_id, title,
                due_at, owner_actor_id
            ) VALUES (%s, %s, %s, 'Próxima ação sintética', now() + interval '1 day', %s)
            """,
            (organization_id, unit_id, opportunity_id, actor_id),
        )
        connection.execute(
            """
            INSERT INTO activities (
                organization_id, business_unit_id, opportunity_id, activity_type,
                occurred_at, responsible_actor_id, summary, origin, performed_by
            ) VALUES (
                %s, %s, %s, 'meeting', now(), %s,
                'Interação sintética', 'postgres-test', 'human'
            )
            """,
            (organization_id, unit_id, opportunity_id, actor_id),
        )
        with pytest.raises(errors.ForeignKeyViolation):
            connection.execute(
                "UPDATE opportunities SET stage_id = %s WHERE id = %s",
                (lab_stage_id, opportunity_id),
            )
        with pytest.raises(errors.CheckViolation):
            connection.execute(
                "UPDATE opportunities SET status = 'lost', closed_at = now() WHERE id = %s",
                (opportunity_id,),
            )
        with pytest.raises(errors.RaiseException, match="append-only"):
            connection.execute(
                "UPDATE opportunity_stage_history SET note = 'alterado' WHERE id = %s",
                (stage_history_id,),
            )

        connection.execute(
            """
            INSERT INTO crm_import_jobs (
                id, organization_id, actor_id, correlation_id,
                source_label, status, total_rows, completed_at
            ) VALUES (%s, %s, %s, %s, 'Importação sintética', 'completed', 1, now())
            """,
            (import_job_id, organization_id, actor_id, correlation_id),
        )
        connection.execute(
            """
            INSERT INTO crm_import_rows (
                id, import_job_id, row_number, entity_type,
                input_sha256, result, resource_id
            ) VALUES (%s, %s, 1, 'person', %s, 'created', %s)
            """,
            (import_row_id, import_job_id, "a" * 64, person_id),
        )
        with pytest.raises(errors.RaiseException, match="append-only"):
            connection.execute("DELETE FROM crm_import_rows WHERE id = %s", (import_row_id,))

        crm_counts = connection.execute(
            """
            SELECT
                (SELECT count(*) FROM people),
                (SELECT count(*) FROM companies),
                (SELECT count(*) FROM person_business_units),
                (SELECT count(*) FROM opportunities),
                (SELECT count(*) FROM opportunity_stage_history),
                (SELECT count(*) FROM activities),
                (SELECT count(*) FROM tasks),
                (SELECT count(*) FROM crm_import_rows)
            """
        ).fetchone()
        assert crm_counts == (1, 1, 3, 1, 1, 1, 1, 1)

        contact_id = uuid.uuid4()
        contract_id = uuid.uuid4()
        version_1_id = uuid.uuid4()
        version_2_id = uuid.uuid4()
        service_id = uuid.UUID("72000000-0000-4000-8000-000000000001")
        issuer_1_id = uuid.UUID("30000000-0000-4000-8000-000000000001")
        issuer_2_id = uuid.UUID("30000000-0000-4000-8000-000000000003")
        connection.execute(
            """
            INSERT INTO contact_methods (
                id, organization_id, company_id, kind, value, normalized_value, is_primary
            ) VALUES (%s, %s, %s, 'email', 'contracts@example.test',
                      'contracts@example.test', true)
            """,
            (contact_id, organization_id, company_id),
        )
        connection.execute(
            """
            INSERT INTO contracts (
                id, organization_id, business_unit_id, customer_company_id,
                internal_number, start_date, contract_type, owner_actor_id, created_by_actor_id
            ) VALUES (%s, %s, %s, %s, 'CT-PG-001', current_date,
                      'recurring_service', %s, %s)
            """,
            (contract_id, organization_id, unit_id, company_id, actor_id, actor_id),
        )
        with pytest.raises(errors.RaiseException, match="not linked"):
            connection.execute(
                """
                INSERT INTO contracts (
                    organization_id, business_unit_id, customer_company_id,
                    internal_number, start_date, contract_type, owner_actor_id,
                    created_by_actor_id
                ) VALUES (%s, %s, %s, 'CT-CROSS-UNIT', current_date,
                          'other', %s, %s)
                """,
                (
                    organization_id,
                    uuid.UUID("40000000-0000-4000-8000-000000000002"),
                    company_id,
                    actor_id,
                    actor_id,
                ),
            )
        version_values = (
            version_1_id,
            organization_id,
            contract_id,
            issuer_1_id,
            actor_id,
        )
        connection.execute(
            """
            INSERT INTO contract_versions (
                id, organization_id, contract_id, version_number, effective_from,
                issuer_establishment_id, currency, billing_frequency, pricing_model,
                amount, billing_installments, change_type, change_reason, source,
                configuration_sha256, created_by_actor_id
            ) VALUES (%s, %s, %s, 1, current_date, %s, 'BRL', 'monthly',
                      'annual', 12000.00, 12, 'initial', 'Baseline sintética', 'api',
                      %s, %s)
            """,
            (*version_values[:4], "a" * 64, version_values[4]),
        )
        connection.execute(
            """
            INSERT INTO contract_version_services (
                contract_version_id, product_service_id, contractual_description,
                quantity, unit_amount, is_active
            ) VALUES (%s, %s, 'Serviço contratual sintético', 1.000, 12000.00, true)
            """,
            (version_1_id, service_id),
        )
        connection.execute(
            """
            INSERT INTO contract_version_contacts (
                contract_version_id, contact_method_id, recipient_role,
                purpose, preferred_channel
            ) VALUES (%s, %s, 'primary', 'billing', 'email')
            """,
            (version_1_id, contact_id),
        )
        connection.execute(
            """
            INSERT INTO contract_versions (
                id, organization_id, contract_id, version_number, effective_from,
                issuer_establishment_id, currency, billing_frequency, pricing_model,
                amount, billing_installments, change_type, change_reason, source,
                configuration_sha256, created_by_actor_id
            ) VALUES (%s, %s, %s, 2, current_date + 1, %s, 'BRL', 'monthly',
                      'annual', 13200.00, 12, 'issuer_change', 'Novo emissor sintético',
                      'api', %s, %s)
            """,
            (
                version_2_id,
                organization_id,
                contract_id,
                issuer_2_id,
                "b" * 64,
                actor_id,
            ),
        )
        with pytest.raises(errors.RaiseException, match="sequential and non-overlapping"):
            connection.execute(
                """
                INSERT INTO contract_versions (
                    organization_id, contract_id, version_number, effective_from,
                    issuer_establishment_id, currency, billing_frequency, pricing_model,
                    amount, change_type, change_reason, source,
                    configuration_sha256, created_by_actor_id
                ) VALUES (%s, %s, 3, current_date + 1, %s, 'BRL', 'monthly',
                          'annual', 1.00, 'conditions_change', 'Sobreposição sintética',
                          'api', %s, %s)
                """,
                (organization_id, contract_id, issuer_1_id, "c" * 64, actor_id),
            )
        with pytest.raises(errors.RaiseException, match="append-only"):
            connection.execute(
                "UPDATE contract_versions SET amount = 1.00 WHERE id = %s", (version_1_id,)
            )

        event_ids = [uuid.uuid4(), uuid.uuid4(), uuid.uuid4()]
        for index, event_type in enumerate(("suspended", "resumed", "terminated"), start=2):
            connection.execute(
                """
                INSERT INTO contract_operational_events (
                    id, organization_id, contract_id, event_type, effective_on,
                    reason, source, actor_id, correlation_id
                ) VALUES (%s, %s, %s, %s, current_date + %s,
                          'Evento operacional sintético', 'api', %s, %s)
                """,
                (
                    event_ids[index - 2],
                    organization_id,
                    contract_id,
                    event_type,
                    index,
                    actor_id,
                    correlation_id,
                ),
            )
        with pytest.raises(errors.RaiseException, match="append-only"):
            connection.execute(
                "DELETE FROM contract_operational_events WHERE id = %s", (event_ids[0],)
            )
        contract_values = connection.execute(
            """
            SELECT
                (SELECT count(*) FROM contracts),
                (SELECT count(*) FROM contract_versions),
                (SELECT amount::text FROM contract_versions WHERE id = %s),
                (SELECT count(*) FROM contract_operational_events)
            """,
            (version_1_id,),
        ).fetchone()
        assert contract_values == (1, 2, "12000.00", 3)

        billing_run_id = uuid.uuid4()
        connection.execute(
            """
            INSERT INTO billing_runs (
                id, organization_id, business_unit_id, competence_month, run_type,
                status, operational_timezone, rule_version, actor_id, correlation_id,
                completed_at
            ) VALUES (%s, %s, %s, date_trunc('month', current_date)::date, 'manual',
                      'completed', 'America/Sao_Paulo', 'billing-competence-v1',
                      %s, %s, now())
            """,
            (billing_run_id, organization_id, unit_id, actor_id, correlation_id),
        )
        with pytest.raises(errors.UniqueViolation):
            connection.execute(
                """
                INSERT INTO billing_runs (
                    organization_id, business_unit_id, competence_month, run_type,
                    operational_timezone, rule_version, actor_id, correlation_id
                ) VALUES (%s, %s, date_trunc('month', current_date)::date, 'scheduled',
                          'America/Sao_Paulo', 'billing-competence-v1', %s, %s)
                """,
                (organization_id, unit_id, actor_id, correlation_id),
            )
        with pytest.raises(errors.CheckViolation):
            connection.execute(
                """
                INSERT INTO billing_runs (
                    organization_id, business_unit_id, competence_month, run_type,
                    operational_timezone, rule_version, actor_id, correlation_id
                ) VALUES (%s, %s, date_trunc('month', current_date)::date + 1, 'manual',
                          'America/Sao_Paulo', 'billing-competence-v1', %s, %s)
                """,
                (organization_id, unit_id, actor_id, correlation_id),
            )

        insert_item = """
            INSERT INTO billing_items (
                id, organization_id, business_unit_id, created_by_run_id, contract_id,
                contract_version_id, competence_month, customer_company_id,
                issuer_establishment_id, currency, gross_amount, snapshot,
                snapshot_sha256, status, correlation_id, created_by_actor_id
            ) VALUES (%s, %s, %s, %s, %s, %s,
                      date_trunc('month', current_date)::date, %s, %s, 'BRL', 1000.00,
                      %s, %s, 'ready', %s, %s)
        """

        def concurrent_insert(item_id: uuid.UUID) -> str:
            try:
                with psycopg.connect(postgres_test_url(), autocommit=True) as worker:
                    worker.execute(
                        insert_item,
                        (
                            item_id,
                            organization_id,
                            unit_id,
                            billing_run_id,
                            contract_id,
                            version_1_id,
                            company_id,
                            issuer_1_id,
                            "{}",
                            "d" * 64,
                            correlation_id,
                            actor_id,
                        ),
                    )
                return "created"
            except errors.UniqueViolation:
                return "duplicate"

        item_ids = (uuid.uuid4(), uuid.uuid4())
        with ThreadPoolExecutor(max_workers=2) as pool:
            outcomes = list(pool.map(concurrent_insert, item_ids))
        assert sorted(outcomes) == ["created", "duplicate"]
        assert connection.execute(
            "SELECT count(*) FROM billing_items WHERE contract_id = %s", (contract_id,)
        ).fetchone() == (1,)
        stored_item_id = connection.execute(
            "SELECT id FROM billing_items WHERE contract_id = %s", (contract_id,)
        ).fetchone()[0]
        with pytest.raises(errors.RaiseException, match="snapshot is immutable"):
            connection.execute(
                "UPDATE billing_items SET gross_amount = 999.00 WHERE id = %s",
                (stored_item_id,),
            )


@pytest.mark.postgres
def test_postgres_migration_007_client_services_and_billing_origins() -> None:
    with psycopg.connect(postgres_test_url(), autocommit=True) as connection:
        applied = apply_foundation(connection)
        assert "007_client_services_identity.sql" in applied

        nullable = connection.execute(
            """
            SELECT is_nullable
            FROM information_schema.columns
            WHERE table_schema = 'public'
              AND table_name = 'client_services'
              AND column_name = 'contract_id'
            """
        ).fetchone()
        assert nullable == ("YES",)

        foreign_keys = {
            row[0]
            for row in connection.execute(
                """
                SELECT pg_get_constraintdef(oid)
                FROM pg_constraint
                WHERE contype = 'f'
                  AND conrelid IN (
                      'client_services'::regclass,
                      'client_service_occurrences'::regclass
                  )
                """
            )
        }
        assert any(
            "contract_id" in definition and "contracts" in definition for definition in foreign_keys
        )
        assert any(
            "client_service_id" in definition and "client_services" in definition
            for definition in foreign_keys
        )
        assert any(
            "billing_item_id" in definition and "billing_items" in definition
            for definition in foreign_keys
        )

        organization_id = uuid.UUID("10000000-0000-4000-8000-000000000001")
        unit_id = uuid.UUID("40000000-0000-4000-8000-000000000001")
        issuer_id = uuid.UUID("30000000-0000-4000-8000-000000000001")
        actor_id = uuid.uuid4()
        company_id = uuid.uuid4()
        contract_id = uuid.uuid4()
        version_id = uuid.uuid4()
        correlation_id = uuid.uuid4()

        connection.execute(
            """
            INSERT INTO actors (id, organization_id, kind, display_name)
            VALUES (%s, %s, 'user', 'Gate 007 PostgreSQL')
            """,
            (actor_id, organization_id),
        )
        connection.execute(
            """
            INSERT INTO companies (id, organization_id, legal_name, created_by_actor_id)
            VALUES (%s, %s, 'Cliente Gate 007', %s)
            """,
            (company_id, organization_id, actor_id),
        )
        connection.execute(
            """
            INSERT INTO company_business_units (
                organization_id, company_id, business_unit_id, owner_actor_id
            ) VALUES (%s, %s, %s, %s)
            """,
            (organization_id, company_id, unit_id, actor_id),
        )
        connection.execute(
            """
            INSERT INTO contracts (
                id, organization_id, business_unit_id, customer_company_id,
                internal_number, administrative_status, start_date, contract_type,
                owner_actor_id, created_by_actor_id
            ) VALUES (%s, %s, %s, %s, 'GATE-007', 'active', current_date,
                      'recurring_service', %s, %s)
            """,
            (contract_id, organization_id, unit_id, company_id, actor_id, actor_id),
        )
        connection.execute(
            """
            INSERT INTO contract_versions (
                id, organization_id, contract_id, version_number, effective_from,
                issuer_establishment_id, currency, billing_frequency, pricing_model,
                amount, change_type, change_reason, source, configuration_sha256,
                created_by_actor_id
            ) VALUES (%s, %s, %s, 1, current_date, %s, 'BRL', 'monthly',
                      'monthly', 900.00, 'initial', 'Gate migration 007', 'system',
                      %s, %s)
            """,
            (version_id, organization_id, contract_id, issuer_id, "a" * 64, actor_id),
        )

        services = {
            "contract_recurring": (uuid.uuid4(), "recurring", "monthly", contract_id),
            "service_recurring": (uuid.uuid4(), "recurring", "quarterly", None),
            "service_one_time": (uuid.uuid4(), "one_time", None, None),
        }
        occurrences: dict[str, uuid.UUID] = {}
        for source_type, (
            service_id,
            service_type,
            recurrence,
            service_contract_id,
        ) in services.items():
            connection.execute(
                """
                INSERT INTO client_services (
                    id, organization_id, business_unit_id, customer_company_id,
                    contract_id, name, service_type, recurrence, start_date,
                    next_occurrence_on, owner_actor_id, amount, currency,
                    operational_lead_days, reminder_lead_days, created_by_actor_id
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, current_date,
                          current_date, %s, 900.00, 'BRL', 5, 2, %s)
                """,
                (
                    service_id,
                    organization_id,
                    unit_id,
                    company_id,
                    service_contract_id,
                    source_type,
                    service_type,
                    recurrence,
                    actor_id,
                    actor_id,
                ),
            )
            occurrence_id = uuid.uuid4()
            occurrences[source_type] = occurrence_id
            connection.execute(
                """
                INSERT INTO client_service_occurrences (
                    id, organization_id, client_service_id, scheduled_for, due_on,
                    status, billing_status, owner_actor_id, created_by_actor_id
                ) VALUES (%s, %s, %s, current_date, current_date, 'planned',
                          'to_bill', %s, %s)
                """,
                (occurrence_id, organization_id, service_id, actor_id, actor_id),
            )

        with pytest.raises(errors.CheckViolation):
            connection.execute(
                """
                INSERT INTO client_services (
                    organization_id, business_unit_id, customer_company_id, name,
                    service_type, recurrence, start_date, owner_actor_id, amount,
                    created_by_actor_id
                ) VALUES (%s, %s, %s, 'Pontual inválido', 'one_time', 'monthly',
                          current_date, %s, 1.00, %s)
                """,
                (organization_id, unit_id, company_id, actor_id, actor_id),
            )
        with pytest.raises(errors.ForeignKeyViolation):
            connection.execute(
                """
                INSERT INTO client_service_occurrences (
                    organization_id, client_service_id, scheduled_for, due_on,
                    owner_actor_id, created_by_actor_id
                ) VALUES (%s, %s, current_date + 1, current_date + 1, %s, %s)
                """,
                (organization_id, uuid.uuid4(), actor_id, actor_id),
            )
        with pytest.raises(errors.UniqueViolation):
            connection.execute(
                """
                INSERT INTO client_service_occurrences (
                    organization_id, client_service_id, scheduled_for, due_on,
                    owner_actor_id, created_by_actor_id
                ) VALUES (%s, %s, current_date, current_date, %s, %s)
                """,
                (
                    organization_id,
                    services["service_recurring"][0],
                    actor_id,
                    actor_id,
                ),
            )

        for source_type, (service_id, _, _, service_contract_id) in services.items():
            item_id = uuid.uuid4()
            version = version_id if source_type == "contract_recurring" else None
            connection.execute(
                """
                INSERT INTO billing_items (
                    id, organization_id, business_unit_id, created_by_run_id,
                    source_type, client_service_id, service_occurrence_id,
                    contract_id, contract_version_id, competence_month,
                    customer_company_id, issuer_establishment_id, currency,
                    gross_amount, snapshot, snapshot_sha256, status,
                    correlation_id, created_by_actor_id
                ) VALUES (%s, %s, %s, NULL, %s, %s, %s, %s, %s,
                          date_trunc('month', current_date)::date, %s, %s, 'BRL',
                          900.00, '{}'::jsonb, %s, 'ready', %s, %s)
                """,
                (
                    item_id,
                    organization_id,
                    unit_id,
                    source_type,
                    service_id,
                    occurrences[source_type],
                    service_contract_id,
                    version,
                    company_id,
                    issuer_id,
                    "b" * 64,
                    correlation_id,
                    actor_id,
                ),
            )
            connection.execute(
                """
                UPDATE client_service_occurrences
                SET billing_item_id = %s, billing_status = 'item_created'
                WHERE id = %s
                """,
                (item_id, occurrences[source_type]),
            )

        assert connection.execute(
            """
            SELECT source_type, count(*)
            FROM billing_items
            GROUP BY source_type
            ORDER BY source_type
            """
        ).fetchall() == [
            ("contract_recurring", 1),
            ("service_one_time", 1),
            ("service_recurring", 1),
        ]


@pytest.mark.postgres
def test_postgres_fiscal_document_allows_only_initial_content_hydration() -> None:
    with psycopg.connect(postgres_test_url(), autocommit=True) as connection:
        applied = apply_foundation(connection)
        assert applied.index("023_fiscal_document_content.sql") < applied.index(
            "024_fiscal_document_content_hydration.sql"
        )

        organization_id = uuid.UUID("10000000-0000-4000-8000-000000000001")
        establishment_id = uuid.UUID("30000000-0000-4000-8000-000000000001")
        unit_id = uuid.UUID("40000000-0000-4000-8000-000000000001")
        actor_id = uuid.uuid4()
        company_id = uuid.uuid4()
        contract_id = uuid.uuid4()
        version_id = uuid.uuid4()
        run_id = uuid.uuid4()
        item_id = uuid.uuid4()
        config_id = uuid.uuid4()
        issuance_id = uuid.uuid4()
        xml_document_id = uuid.uuid4()
        receipt_document_id = uuid.uuid4()

        connection.execute(
            "INSERT INTO actors (id, organization_id, kind, display_name) "
            "VALUES (%s, %s, 'user', 'Hydration PostgreSQL')",
            (actor_id, organization_id),
        )
        connection.execute(
            "INSERT INTO companies (id, organization_id, legal_name, created_by_actor_id) "
            "VALUES (%s, %s, 'Cliente Hydration', %s)",
            (company_id, organization_id, actor_id),
        )
        connection.execute(
            """
            INSERT INTO company_business_units (
                organization_id, company_id, business_unit_id, owner_actor_id
            ) VALUES (%s, %s, %s, %s)
            """,
            (organization_id, company_id, unit_id, actor_id),
        )
        connection.execute(
            """
            INSERT INTO contracts (
                id, organization_id, business_unit_id, customer_company_id,
                internal_number, administrative_status, start_date, contract_type,
                owner_actor_id, created_by_actor_id
            ) VALUES (%s, %s, %s, %s, 'HYDRATION-024', 'active', current_date,
                      'recurring_service', %s, %s)
            """,
            (contract_id, organization_id, unit_id, company_id, actor_id, actor_id),
        )
        connection.execute(
            """
            INSERT INTO contract_versions (
                id, organization_id, contract_id, version_number, effective_from,
                issuer_establishment_id, currency, billing_frequency, pricing_model,
                amount, change_type, change_reason, source, configuration_sha256,
                created_by_actor_id
            ) VALUES (%s, %s, %s, 1, current_date, %s, 'BRL', 'monthly',
                      'monthly', 100.00, 'initial', 'Hydration 024', 'system', %s, %s)
            """,
            (
                version_id,
                organization_id,
                contract_id,
                establishment_id,
                "a" * 64,
                actor_id,
            ),
        )
        connection.execute(
            """
            INSERT INTO billing_runs (
                id, organization_id, business_unit_id, competence_month, run_type,
                status, operational_timezone, rule_version, actor_id, correlation_id
            ) VALUES (%s, %s, %s, date_trunc('month', current_date)::date, 'manual',
                      'completed', 'America/Sao_Paulo', 'test', %s, %s)
            """,
            (run_id, organization_id, unit_id, actor_id, uuid.uuid4()),
        )
        connection.execute(
            """
            INSERT INTO billing_items (
                id, organization_id, business_unit_id, created_by_run_id, source_type,
                contract_id, contract_version_id, competence_month, customer_company_id,
                issuer_establishment_id, currency, gross_amount, snapshot, snapshot_sha256,
                status, correlation_id, created_by_actor_id
            ) VALUES (%s, %s, %s, %s, 'contract_recurring', %s, %s,
                      date_trunc('month', current_date)::date, %s, %s, 'BRL', 100.00,
                      '{}'::jsonb, %s, 'completed', %s, %s)
            """,
            (
                item_id,
                organization_id,
                unit_id,
                run_id,
                contract_id,
                version_id,
                company_id,
                establishment_id,
                "b" * 64,
                uuid.uuid4(),
                actor_id,
            ),
        )
        connection.execute(
            """
            INSERT INTO fiscal_establishment_configs (
                id, organization_id, establishment_id, environment, emission_method,
                endpoint, query_base_url, certificate_secret_ref, certificate_key_id,
                municipality_code, service_code, nbs_code
            ) VALUES (%s, %s, %s, 'production', 'api_a1',
                      'https://sefin.nfse.gov.br/api/v1/dps',
                      'https://sefin.nfse.gov.br/api/v1', 'vault://test', 'test',
                      '4209102', '020101', '114031000')
            """,
            (config_id, organization_id, establishment_id),
        )
        connection.execute(
            """
            INSERT INTO fiscal_issuances (
                id, organization_id, billing_item_id, establishment_config_id,
                environment, status, series, dps_number, dps_id, snapshot,
                snapshot_sha256, nfse_number, access_key, requested_by_actor_id,
                correlation_id
            ) VALUES (%s, %s, %s, %s, 'production', 'completed', 1, 13,
                      'DPS-HYDRATION-13', '{}'::jsonb, %s, '13', %s, %s, %s)
            """,
            (
                issuance_id,
                organization_id,
                item_id,
                config_id,
                "c" * 64,
                "42091022239813375000106000000000001326090584825643",
                actor_id,
                uuid.uuid4(),
            ),
        )
        xml = b"xml"
        connection.execute(
            """
            INSERT INTO fiscal_documents (
                id, issuance_id, document_type, storage_key, content_type,
                content_sha256, size_bytes, status, content_bytes
            ) VALUES (%s, %s, 'nfse_xml', 'legacy/nfse.xml', 'application/xml',
                      %s, %s, 'available', NULL)
            """,
            (xml_document_id, issuance_id, hashlib.sha256(xml).hexdigest(), len(xml)),
        )
        connection.execute(
            "UPDATE fiscal_documents SET content_bytes = %s WHERE id = %s",
            (xml, xml_document_id),
        )
        assert connection.execute(
            "SELECT content_bytes FROM fiscal_documents WHERE id = %s", (xml_document_id,)
        ).fetchone() == (xml,)

        forbidden_updates = (
            (
                "UPDATE fiscal_documents SET content_bytes = %s WHERE id = %s",
                (b"new", xml_document_id),
            ),
            ("UPDATE fiscal_documents SET content_bytes = NULL WHERE id = %s", (xml_document_id,)),
            (
                "UPDATE fiscal_documents SET storage_key = 'changed' WHERE id = %s",
                (xml_document_id,),
            ),
        )
        for statement, parameters in forbidden_updates:
            with pytest.raises(errors.RaiseException):
                connection.execute(statement, parameters)

        connection.execute(
            """
            INSERT INTO fiscal_documents (
                id, issuance_id, document_type, storage_key, content_type,
                content_sha256, size_bytes, status, content_bytes
            ) VALUES (%s, %s, 'provider_receipt', 'legacy/receipt.json',
                      'application/json', %s, 4, 'available', NULL)
            """,
            (receipt_document_id, issuance_id, "d" * 64),
        )
        with pytest.raises(errors.RaiseException):
            connection.execute(
                "UPDATE fiscal_documents SET content_bytes = %s WHERE id = %s",
                (b"bad", receipt_document_id),
            )


@pytest.mark.postgres
def test_postgres_authorized_net_amount_backfill_is_safe_and_idempotent() -> None:
    migration = (MIGRATIONS / "028_fiscal_authorized_net_amount.sql").read_text(
        encoding="utf-8"
    )
    with psycopg.connect(postgres_test_url(), autocommit=True) as connection:
        connection.execute("DROP SCHEMA public CASCADE")
        connection.execute("CREATE SCHEMA public")
        connection.execute("CREATE TABLE fiscal_issuances (id uuid PRIMARY KEY)")
        connection.execute(
            """
            CREATE TABLE fiscal_documents (
                issuance_id uuid NOT NULL,
                document_type text NOT NULL,
                content_bytes bytea
            )
            """
        )
        valid_id, preserved_id, invalid_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
        connection.execute(
            "INSERT INTO fiscal_issuances (id) VALUES (%s), (%s), (%s)",
            (valid_id, preserved_id, invalid_id),
        )
        connection.execute(migration)
        connection.execute(
            "UPDATE fiscal_issuances SET authorized_net_amount = 999.99 WHERE id = %s",
            (preserved_id,),
        )
        for issuance_id, payload in (
            (valid_id, b"<NFSe><infNFSe><valores><vLiq>750.80</vLiq></valores></infNFSe></NFSe>"),
            (
                preserved_id,
                b"<NFSe><infNFSe><valores><vLiq>1.00</vLiq></valores></infNFSe></NFSe>",
            ),
            (
                invalid_id,
                b"<NFSe><infNFSe><valores><vLiq>invalid</vLiq></valores></infNFSe></NFSe>",
            ),
        ):
            connection.execute(
                """
                INSERT INTO fiscal_documents (issuance_id, document_type, content_bytes)
                VALUES (%s, 'nfse_xml', %s)
                """,
                (issuance_id, payload),
            )

        connection.execute(migration)
        connection.execute(migration)
        values = dict(
            connection.execute(
                "SELECT id, authorized_net_amount FROM fiscal_issuances"
            ).fetchall()
        )
        assert values[valid_id] == Decimal("750.80")
        assert values[preserved_id] == Decimal("999.99")
        assert values[invalid_id] is None
