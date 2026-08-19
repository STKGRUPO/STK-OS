from __future__ import annotations

import argparse
import hashlib
import os
from pathlib import Path

import psycopg
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
MIGRATIONS = ROOT / "database" / "migrations"
SEEDS = ROOT / "database" / "seeds"


def database_url() -> str:
    load_dotenv(ROOT / ".env")
    value = os.getenv("STK_DATABASE_URL", "")
    if value.startswith("postgresql+psycopg://"):
        value = value.replace("postgresql+psycopg://", "postgresql://", 1)
    if not value.startswith(("postgresql://", "postgres://")):
        raise SystemExit("STK_DATABASE_URL deve apontar explicitamente para PostgreSQL")
    return value


def checksum(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def migrate() -> None:
    with psycopg.connect(database_url()) as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS schema_migrations (
                version text PRIMARY KEY,
                checksum_sha256 text NOT NULL,
                applied_at timestamptz NOT NULL DEFAULT now()
            )
            """
        )
        for path in sorted(MIGRATIONS.glob("*.sql")):
            content = path.read_bytes()
            digest = checksum(content)
            row = connection.execute(
                "SELECT checksum_sha256 FROM schema_migrations WHERE version = %s",
                (path.name,),
            ).fetchone()
            if row:
                if row[0] != digest:
                    raise SystemExit(f"Migration aplicada foi alterada: {path.name}")
                print(f"ok      {path.name}")
                continue
            with connection.transaction():
                connection.execute(content.decode("utf-8"))
                connection.execute(
                    "INSERT INTO schema_migrations (version, checksum_sha256) VALUES (%s, %s)",
                    (path.name, digest),
                )
            print(f"applied {path.name}")


def seed() -> None:
    with psycopg.connect(database_url()) as connection:
        for path in sorted(SEEDS.glob("*.sql")):
            with connection.transaction():
                connection.execute(path.read_text(encoding="utf-8"))
            print(f"seeded  {path.name}")


def verify() -> None:
    with psycopg.connect(database_url()) as connection:
        rows = dict(
            connection.execute("SELECT version, checksum_sha256 FROM schema_migrations")
        )
    expected = {
        path.name: checksum(path.read_bytes()) for path in MIGRATIONS.glob("*.sql")
    }
    if rows != expected:
        raise SystemExit(
            f"Migrations divergentes. banco={rows!r} repositorio={expected!r}"
        )
    print(f"verified {len(expected)} migrations")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Gerencia o schema PostgreSQL do STK OS"
    )
    parser.add_argument("command", choices=("migrate", "seed", "verify"))
    args = parser.parse_args()
    {"migrate": migrate, "seed": seed, "verify": verify}[args.command]()


if __name__ == "__main__":
    main()
