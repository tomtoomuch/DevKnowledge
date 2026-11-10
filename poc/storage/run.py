#!/usr/bin/env python3
"""Execute real SQL Server/PostgreSQL Docker POC tests on disposable data.

This does not use, inspect, or modify DevKnowledge's main Compose project.
No database ports are exposed, and Compose networks are internal-only.
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
        output = (cp.stdout + "\n" + cp.stderr)
        for secret in (env["POC_MSSQL_PASSWORD"], env["POC_POSTGRES_PASSWORD"]):
            output = output.replace(secret, "[REDACTED]")
        raise RuntimeError(f"Command exited with {cp.returncode}:\n{output[-5000:]}")
    return cp.stdout, elapsed


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--engine", required=True, choices=("sqlserver", "postgres"))
    args = parser.parse_args()
    engine = args.engine
    project = f"dkpoc-{engine}-{os.getpid()}"
    assert project.startswith("dkpoc-")
    env = os.environ.copy()
    env["POC_MSSQL_PASSWORD"] = "Aa1!" + secrets.token_hex(18)
    env["POC_POSTGRES_PASSWORD"] = "Pg1!" + secrets.token_hex(18)
    base = ["docker", "compose", "-p", project, "-f", str(ROOT / "compose.yaml")]
    times = {}
    success = False
    failure = ""
    try:
        _, times["docker_start_seconds"] = execute(
            base + ["up", "-d", "--wait", "--wait-timeout", "210", engine],
            env=env, timeout=320)
        print(f"Started official {engine} image with no host ports and a unique Compose project", flush=True)
        if engine == "sqlserver":
            def sql(file):
                command = ('SQLCMDPASSWORD="$MSSQL_SA_PASSWORD" '
                           '/opt/mssql-tools18/bin/sqlcmd -S localhost -U sa -C -b -l 30 '
                           f'-i /sql/{file}')
                return execute(base + ["exec", "-T", engine, "bash", "-lc", command],
                               env=env, timeout=180)
            output, times["schema_seconds"] = sql("schema.sql")
            if "SCHEMA_PASS sqlserver" not in output:
                raise RuntimeError("No schema success marker")
            output, times["invariants_seconds"] = sql("test.sql")
            if "POC_PASS sqlserver" not in output:
                raise RuntimeError("No invariant success marker")
            output, times["backup_restore_seconds"] = sql("backup_restore.sql")
            if "BACKUP_RESTORE_PASS sqlserver" not in output:
                raise RuntimeError("Backup/restore not verified")
        else:
            def pg(*args):
                command = 'PGPASSWORD="$POSTGRES_PASSWORD" exec ' + " ".join(args)
                return execute(base + ["exec", "-T", engine, "sh", "-lc", command],
                               env=env, timeout=180)
            output, times["schema_seconds"] = pg("psql", "-h", "127.0.0.1", "-U", "postgres", "-d", "devknowledge_poc",
                                                   "-v", "ON_ERROR_STOP=1", "-f", "/sql/schema.sql")
            if "SCHEMA_PASS postgres" not in output:
                raise RuntimeError("No schema success marker")
            output, times["invariants_seconds"] = pg("psql", "-h", "127.0.0.1", "-U", "postgres", "-d", "devknowledge_poc",
                                                       "-v", "ON_ERROR_STOP=1", "-f", "/sql/test.sql")
            if "POC_PASS postgres" not in output:
                raise RuntimeError("No invariant success marker")
            start = time.monotonic()
            pg("pg_dump", "-h", "127.0.0.1", "-U", "postgres", "-Fc", "-d", "devknowledge_poc",
               "-f", "/tmp/dk_sqlpoc.dump")
            pg("createdb", "-h", "127.0.0.1", "-U", "postgres", "devknowledge_poc_restored")
            pg("pg_restore", "-h", "127.0.0.1", "-U", "postgres", "-d", "devknowledge_poc_restored",
               "--exit-on-error", "/tmp/dk_sqlpoc.dump")
            output, _ = pg("psql", "-h", "127.0.0.1", "-U", "postgres", "-d", "devknowledge_poc_restored",
                           "-v", "ON_ERROR_STOP=1", "-t", "-A", "-c",
                           '"SELECT COUNT(*) FROM knowledge_items WHERE revision = 2"')
            if output.strip() != "1":
                raise RuntimeError("Postgres restored fixture mismatch: " + output.strip())
            times["backup_restore_seconds"] = round(time.monotonic()-start, 3)
        success = True
    except Exception as e:
        failure = str(e)
        print(f"POC ERROR ({engine}): {failure}", file=sys.stderr, flush=True)
    finally:
        RESULTS.mkdir(parents=True, exist_ok=True)
        report = {"engine": engine, "passed": success, "measurements": times,
                  "checks": ["FK", "UNIQUE", "JSON", "join RNCP", "ROLLBACK",
                             "optimistic revision", "backup and restored database"],
                  "scope": "fictional data; disposable Compose project; no host ports",
                  "error": failure}
        (RESULTS / (engine + ".json")).write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(report, ensure_ascii=False), flush=True)
        try:
            execute(base + ["down", "--volumes", "--remove-orphans"], env=env, timeout=180)
            print("Removed only temporary POC containers and project-scoped volumes", flush=True)
        except Exception as cleanup_error:
            print("POC cleanup error: " + str(cleanup_error), file=sys.stderr, flush=True)
            success = False
    if not success:
        sys.exit(1)


if __name__ == "__main__":
    main()
