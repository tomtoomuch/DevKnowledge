"""Versioned, transactional PostgreSQL schema migrations for the RNCP slice."""
import hashlib
import os
from pathlib import Path

import psycopg
from psycopg.conninfo import make_conninfo


def connection_string() -> str:
    password = os.environ["RNCP_PG_PASSWORD"]
    return make_conninfo(
        host=os.environ.get("RNCP_PG_HOST", "postgres"),
        port=int(os.environ.get("RNCP_PG_PORT", "5432")),
        dbname=os.environ.get("RNCP_PG_DATABASE", "rncp_poc"),
        user=os.environ.get("RNCP_PG_USER", "rncp_poc"),
        password=password,
        connect_timeout=10,
    )


def apply_migrations(dsn: str, directory: Path) -> list[int]:
    """Use one transaction/advisory lock; fail closed on checksum drift."""
    files = sorted(directory.glob("[0-9][0-9][0-9]_*.sql"))
    if not files:
        raise RuntimeError("No RNCP migrations found")
    applied = []
    with psycopg.connect(dsn) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT pg_advisory_xact_lock(%s, %s)", (37827, 5))
            cur.execute("CREATE SCHEMA IF NOT EXISTS rncp")
            cur.execute("""
                CREATE TABLE IF NOT EXISTS rncp.schema_migrations (
                    version_number INTEGER PRIMARY KEY,
                    checksum_sha256 CHAR(64) NOT NULL,
                    applied_at TIMESTAMPTZ NOT NULL DEFAULT now()
                )
            """)
            for file in files:
                version = int(file.name[:3])
                content = file.read_text(encoding="utf-8")
                digest = hashlib.sha256(content.encode("utf-8")).hexdigest()
                cur.execute(
                    "SELECT checksum_sha256 FROM rncp.schema_migrations WHERE version_number = %s",
                    (version,),
                )
                existing = cur.fetchone()
                if existing is not None:
                    if existing[0] != digest:
                        raise RuntimeError(
                            f"RNCP migration {version} changed after being applied"
                        )
                    continue
                cur.execute(content)
                cur.execute(
                    """INSERT INTO rncp.schema_migrations
                       (version_number, checksum_sha256) VALUES (%s, %s)""",
                    (version, digest),
                )
                applied.append(version)
    return applied
