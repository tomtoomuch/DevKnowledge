#!/usr/bin/env python3
"""Run the RNCP PostgreSQL integration on a fresh disposable Docker project."""
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
import time

HERE = Path(__file__).resolve().parent
OUT = HERE.parents[1] / "test-results" / "rncp-postgres"


def run(args, env, timeout=360):
    result = subprocess.run(args, capture_output=True, text=True,
                            timeout=timeout, env=env, check=False)
    if result.returncode:
        message = (result.stdout + "\n" + result.stderr)
        message = message.replace(env["RNCP_PG_PASSWORD"], "[REDACTED]")
        raise RuntimeError(f"Command failed ({result.returncode}):\n{message[-5500:]}")
    return result.stdout


def main():
    project = "dk-rncp-poc-" + secrets.token_hex(5)
    env = os.environ.copy()
    env["RNCP_PG_PASSWORD"] = "Rp1!" + secrets.token_hex(18)
    base = ["docker", "compose", "-p", project, "-f", str(HERE / "compose.yaml")]
    passed, reason, tests, restore = False, "", "", ""
    snapshots = {}
    start = time.monotonic()
    try:
        run(base + ["up", "-d", "--wait", "--wait-timeout", "180", "postgres"],
            env, timeout=240)
        cid = run(base + ["ps", "-q", "postgres"], env).strip()
        if not cid:
            raise RuntimeError("PostgreSQL test container missing")
        if run(["docker", "port", cid], env).strip():
            raise RuntimeError("Unexpected host publication of PostgreSQL port")
        snapshots["before"] = run(
            ["docker", "stats", "--no-stream", "--format", "{{.MemUsage}}", cid], env
        ).strip()
        # Build can use the host's image-pull connectivity; runtime network is internal.
        run(base + ["build", "test"], env, timeout=460)
        tests = run(base + ["run", "--rm", "--no-deps", "test"], env, timeout=240)
        if "passed" not in tests:
            raise RuntimeError("Pytest did not report successful integration tests")
        snapshots["after"] = run(
            ["docker", "stats", "--no-stream", "--format", "{{.MemUsage}}", cid], env
        ).strip()

        def dbcmd(command):
            return run(base + ["exec", "-T", "postgres", "sh", "-lc",
                               'export PGPASSWORD="$POSTGRES_PASSWORD"; ' + command], env)
        dbcmd("pg_dump -h 127.0.0.1 -U rncp_poc -d rncp_poc -Fc -f /tmp/rncp.dump")
        dbcmd("createdb -h 127.0.0.1 -U rncp_poc rncp_restored")
        dbcmd("pg_restore -h 127.0.0.1 -U rncp_poc -d rncp_restored "
              "--exit-on-error /tmp/rncp.dump")
        query = ("SELECT (SELECT count(*) FROM rncp.certification_competencies),"
                 "(SELECT count(*) FROM rncp.competency_evidence),"
                 "(SELECT count(*) FROM rncp.schema_migrations)")
        def counts(name):
            return dbcmd(f'psql -h 127.0.0.1 -U rncp_poc -d {name} '
                         f'-A -t -v ON_ERROR_STOP=1 -c "{query}"').strip()
        source_counts = counts("rncp_poc")
        restored_counts = counts("rncp_restored")
        if source_counts != restored_counts or restored_counts != "2|1|2":
            raise RuntimeError(
                f"Restored RNCP database mismatch source={source_counts} restored={restored_counts}"
            )
        restore = restored_counts
        passed = True
    except Exception as exc:
        reason = str(exc)
        print("RNCP POC FAILURE: " + reason, file=sys.stderr, flush=True)
    finally:
        try:
            # Scoped strictly to this random, disposable project; never touch root Compose.
            run(base + ["down", "--volumes", "--remove-orphans"], env, timeout=120)
        except Exception as exc:
            passed = False
            reason += "\ncleanup: " + str(exc)
        OUT.mkdir(parents=True, exist_ok=True)
        result = {
            "passed": passed,
            "tests": tests.strip().splitlines()[-1] if tests else "not executed",
            "restored_counts_competencies_evidence_migrations": restore,
            "memory": snapshots,
            "seconds_total_including_image_build": round(time.monotonic() - start, 2),
            "scope": "isolated PostgreSQL 17 Docker, fictional RNCP, no MongoDB access",
            "error": reason,
        }
        (OUT / "result.json").write_text(json.dumps(result, indent=2) + "\n",
                                         encoding="utf-8")
        print("RNCP_POC_RESULT=" + json.dumps(result), flush=True)
    if not passed:
        sys.exit(1)


if __name__ == "__main__":
    main()
