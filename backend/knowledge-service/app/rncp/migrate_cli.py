"""Explicit one-time migration job for the opt-in PostgreSQL overlay."""
from pathlib import Path
from app.rncp.migrate import apply_migrations, connection_string

if __name__ == "__main__":
    migration_dir = Path(__file__).resolve().parent / "migrations"
    applied = apply_migrations(connection_string(), migration_dir)
    print("RNCP migrations applied: " + ",".join(str(version) for version in applied))
