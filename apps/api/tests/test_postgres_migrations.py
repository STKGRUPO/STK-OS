from __future__ import annotations

import os
from pathlib import Path

import psycopg
import pytest

ROOT = Path(__file__).resolve().parents[3]


@pytest.mark.postgres
def test_migrations_apply_to_disposable_postgres() -> None:
    url = os.getenv("STK_TEST_DATABASE_URL")
    if not url:
        pytest.skip("STK_TEST_DATABASE_URL não configurada")
    if url.startswith("postgresql+psycopg://"):
        url = url.replace("postgresql+psycopg://", "postgresql://", 1)
    with psycopg.connect(url) as connection:
        for path in sorted((ROOT / "database/migrations").glob("*.sql")):
            connection.execute(path.read_text(encoding="utf-8"))
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT tablename FROM pg_tables WHERE schemaname = 'public'"
            )
        }
    assert {"organizations", "audit_events", "inbox_events", "outbox_events"} <= tables
