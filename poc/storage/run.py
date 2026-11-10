#!/usr/bin/env python3
"""Compare official Docker database images in disposable, isolated Compose projects.

No Docker context, mounted volume, network or credentials from the main app
are used. Database image tags are explicit; report actual image IDs in outputs.
"""
import argparse
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parent
RESULTS = ROOT.parent.parent / "test-results" / "storage-poc"


def execute(command, *, env, timeout=400):
    start = time.monotonic()
    try:
        cp = subprocess.run(command, env=env, text=True, capture_output=True,
                            timeout=timeout, check=False)
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError("Command timed out") from exc
    elapsed = round(time.monotonic() - start, 3)
    if cp.returncode:
        output = cp.stdout + "\n" + cp.stderr
        for key in ("POC_MSSQL_PASSWORD", "POC_POSTGRES_PASSWORD", "POC_DB_PASSWORD"):
            output = output.replace(env[key], "[REDACTED]")
        raise RuntimeError(f"Command exited with {cp.returncode}:\n{output[-6000:]}")
    return cp.stdout, elapsed


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--engine", required=True, choices=("sqlserver", "postgres"))
    parser.add_argument("--rows", type=int, default=1500, help="Fictitious records; 100..10000")
    parser.add_argument("--extended", action="store_true", help="FastAPI, size and resource tests")
    args = parser.parse_args()
    if args.rows < 100 or args.rows > 10000:
        parser.error("--rows must be within 100..10000")
    engine = args.engine
    project = f"dkpoc-{engine}-{secrets.token_hex(5)}"
    env = os.environ.copy()
    env["POC_MSSQL_PASSWORD"] = "Aa1!" + secrets.token_hex(18)
    env["POC_POSTGRES_PASSWORD"] = "Pg1!" + secrets.token_hex(18)
    env["POC_DB_PASSWORD"] = env["POC_MSSQL_PASSWORD"] if engine == "sqlserver" else env["POC_POSTGRES_PASSWORD"]
    env["POC_ENGINE"] = engine
    env["POC_ROWS"] = str(args.rows)
    base = ["docker", "compose", "-p", project, "-f", str(ROOT / "compose.yaml")]
    times, extras = {}, {}
    success, failure, started = False, "", False
    try:
        _, times["docker_start_seconds"] = execute(
            base + ["up", "-d", "--wait", "--wait-timeout", "210", engine],
            env=env, timeout=340)
        started = True
        print(f"Started {engine} in an isolated project without host ports", flush=True)

        # Capture exact images because mutable upstream tags are not reproducible.
        image_ids, _ = execute(base + ["images", "-q", engine], env=env)
        extras["image_ids"] = image_ids.strip().splitlines()
        container_id, _ = execute(base + ["ps", "-q", engine], env=env)
        cid = container_id.strip()
        if not cid:
            raise RuntimeError("No running database container found")
        ports, _ = execute(["docker", "port", cid], env=env)
        if ports.strip():
            raise RuntimeError("Database unexpectedly publishes a host port")

        def memory_snapshot():
            output, _ = execute(
                ["docker", "stats", "--no-stream", "--format",
                 "{{.MemUsage}}|{{.CPUPerc}}", cid], env=env, timeout=40)
            return output.strip()

        extras["db_memory_before_bench"] = memory_snapshot()
        if engine == "sqlserver":
            def sql(file):
                cmd = ('SQLCMDPASSWORD="$MSSQL_SA_PASSWORD" '
                       '/opt/mssql-tools18/bin/sqlcmd -S localhost -U sa -C -b -l 30 '
                       f'-i /sql/{file}')
                return execute(base + ["exec", "-T", engine, "bash", "-lc", cmd],
                               env=env, timeout=240)
            output, times["schema_seconds"] = sql("schema.sql")
            if "SCHEMA_PASS sqlserver" not in output:
                raise RuntimeError("SQL Server schema marker absent")
            output, times["migration_v2_first_seconds"] = sql("migration_v2.sql")
            if "MIGRATION_V2_PASS sqlserver" not in output:
                raise RuntimeError("SQL Server migration marker absent")
            output, times["migration_v2_reapply_seconds"] = sql("migration_v2.sql")
            if "MIGRATION_V2_PASS sqlserver" not in output:
                raise RuntimeError("SQL Server migration not repeatable")
            output, times["invariants_seconds"] = sql("test.sql")
            if "POC_PASS sqlserver" not in output:
                raise RuntimeError("SQL Server invariants marker absent")
        else:
            def pg(*args):
                cmd = 'PGPASSWORD="$POSTGRES_PASSWORD" exec ' + " ".join(args)
                return execute(base + ["exec", "-T", engine, "sh", "-lc", cmd],
                               env=env, timeout=240)
            def pg_file(file):
                return pg("psql", "-h", "127.0.0.1", "-U", "postgres",
                          "-d", "devknowledge_poc", "-v", "ON_ERROR_STOP=1",
                          "-f", "/sql/" + file)
            output, times["schema_seconds"] = pg_file("schema.sql")
            if "SCHEMA_PASS postgres" not in output:
                raise RuntimeError("Postgres schema marker absent")
            output, times["migration_v2_first_seconds"] = pg_file("migration_v2.sql")
            if "MIGRATION_V2_PASS postgres" not in output:
                raise RuntimeError("Postgres migration marker absent")
            output, times["migration_v2_reapply_seconds"] = pg_file("migration_v2.sql")
            if "MIGRATION_V2_PASS postgres" not in output:
                raise RuntimeError("Postgres migration not repeatable")
            output, times["invariants_seconds"] = pg_file("test.sql")
            if "POC_PASS postgres" not in output:
                raise RuntimeError("Postgres invariants marker absent")

        if args.extended:
            _, times["api_client_build_seconds"] = execute(
                base + ["build", "api-bench"], env=env, timeout=520)
            bench_out, times["fastapi_bench_seconds"] = execute(
                base + ["run", "--rm", "--no-deps", "api-bench"], env=env,
                timeout=480)
            marker = "BENCH_REPORT_JSON="
            reports = [line.split(marker, 1)[1] for line in bench_out.splitlines()
                       if marker in line]
            if len(reports) != 1:
                raise RuntimeError("Missing FastAPI SQL benchmark report marker")
            extras["api_bench"] = json.loads(reports[0])
            if extras["api_bench"]["fixture_rows"] != args.rows:
                raise RuntimeError("Unexpected FastAPI fixture count")
            extras["db_memory_after_bench"] = memory_snapshot()

        # Restore a different test database, never overwriting source or app DB.
        if engine == "sqlserver":
            output, times["backup_restore_seconds"] = sql("backup_restore.sql")
            if "BACKUP_RESTORE_PASS sqlserver" not in output:
                raise RuntimeError("SQL Server backup/restore marker absent")
        else:
            start = time.monotonic()
            pg("pg_dump", "-h", "127.0.0.1", "-U", "postgres", "-Fc",
               "-d", "devknowledge_poc", "-f", "/tmp/dk_sqlpoc.dump")
            pg("createdb", "-h", "127.0.0.1", "-U", "postgres",
               "devknowledge_poc_restored")
            pg("pg_restore", "-h", "127.0.0.1", "-U", "postgres",
               "-d", "devknowledge_poc_restored", "--exit-on-error",
               "/tmp/dk_sqlpoc.dump")
            query = '"SELECT COUNT(*), COUNT(*) FILTER (WHERE revision = 2) FROM knowledge_items"'
            source, _ = pg("psql", "-h", "127.0.0.1", "-U", "postgres",
                           "-d", "devknowledge_poc", "-v", "ON_ERROR_STOP=1",
                           "-t", "-A", "-c", query)
            restored, _ = pg("psql", "-h", "127.0.0.1", "-U", "postgres",
                             "-d", "devknowledge_poc_restored", "-v", "ON_ERROR_STOP=1",
                             "-t", "-A", "-c", query)
            if source.strip() != restored.strip():
                raise RuntimeError("Postgres restored counts/revisions do not match source")
            extras["restored_counts"] = restored.strip()
            times["backup_restore_seconds"] = round(time.monotonic() - start, 3)
        success = True
    except Exception as exc:
        failure = str(exc)
        print("POC ERROR (" + engine + "): " + failure, file=sys.stderr, flush=True)
    finally:
        RESULTS.mkdir(parents=True, exist_ok=True)
        report = {
            "engine": engine, "passed": success,
            "extended": args.extended, "measurements": times,
            "evidence": extras,
            "checks": ["FK", "UNIQUE", "JSON", "RNCP join", "ROLLBACK",
                       "optimistic revision", "idempotent V2 migration",
                       "backup and restored database"] + (["real FastAPI/TestClient",
                           "SQLAlchemy ODBC/Psycopg", "fixture dataset",
                           "Docker memory snapshots"] if args.extended else []),
            "scope": "fictional data; isolated Compose project; no host ports",
            "error": failure,
        }
        (RESULTS / (engine + ".json")).write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8")
        print("POC_RESULT_JSON=" + json.dumps(report, ensure_ascii=False),
              flush=True)
        if started:
            try:
                execute(base + ["down", "--volumes", "--remove-orphans"],
                        env=env, timeout=180)
                print("Removed temporary POC containers and named volumes",
                      flush=True)
            except Exception as cleanup_error:
                print("Cleanup error: " + str(cleanup_error),
                      file=sys.stderr, flush=True)
                success = False
    if not success:
        sys.exit(1)


if __name__ == "__main__":
    main()
