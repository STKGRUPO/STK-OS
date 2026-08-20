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
        assert applied == ["001_foundation.sql", "002_append_only_guards.sql"]

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
        } <= tables

        seed_counts = connection.execute(
            """
            SELECT
                (SELECT count(*) FROM organizations),
                (SELECT count(*) FROM legal_entities),
                (SELECT count(*) FROM fiscal_establishments),
                (SELECT count(*) FROM business_units)
            """
        ).fetchone()
        assert seed_counts == (1, 3, 4, 3)

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
