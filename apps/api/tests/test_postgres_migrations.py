from __future__ import annotations

import hashlib
import os
import uuid
from pathlib import Path

import psycopg
import pytest
from psycopg import errors

ROOT = Path(__file__).resolve().parents[3]
MIGRATIONS = ROOT / "database" / "migrations"
SEEDS = ROOT / "database" / "seeds"


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
        assert applied == [
            "001_foundation.sql",
            "002_append_only_guards.sql",
            "003_crm_vertical.sql",
            "004_crm_append_only_guards.sql",
        ]

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
        } <= tables

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
