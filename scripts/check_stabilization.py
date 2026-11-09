"""Exercise the production Compose configuration without using development data.

Python standard library only. A unique project owns a new volume, removed in
finally. Never accepts a project name or credentials from the caller.
"""

import json
import os
from datetime import datetime, UTC
from pathlib import Path
import subprocess
import time
from uuid import uuid4


ROOT = Path(__file__).resolve().parents[1]
PROJECT = "devknowledge-stabilization-test-" + uuid4().hex[:12]
SETTINGS = dict(
    line.split("=", 1)
    for line in (ROOT / "tests/stabilization.env").read_text().splitlines()
    if line and not line.startswith("#")
)
# Explicitly suppress inherited configuration and never load the user's .env.
ENV = {key: value for key, value in os.environ.items()
       if not key.startswith(("COMPOSE_", "MONGODB_", "MONGO_INITDB_", "GATEWAY_"))}
ENV.update(SETTINGS)
COMPOSE = ["docker", "compose", "--env-file", str(ROOT / "tests/stabilization.env"),
           "-p", PROJECT, "-f", str(ROOT / "compose.yaml"),
           "-f", str(ROOT / "tests/compose.stabilization.yaml")]
RESULTS = ROOT / "test-results"


def run(args, *, check=True, timeout=120):
    result = subprocess.run(args, cwd=ROOT, env=ENV, text=True,
                            encoding="utf-8", errors="replace",
                            capture_output=True, timeout=timeout)
    if check and result.returncode:
        raise RuntimeError(f"Command failed ({result.returncode}):\n" +
                           redact(result.stdout + result.stderr))
    return result


def redact(text):
    for key, value in SETTINGS.items():
        if "PASSWORD" in key:
            text = text.replace(value, "[redacted]")
    return text.replace("deliberately_wrong_test_password", "[redacted]")


def compose(*args, **kwargs):
    return run(COMPOSE + list(args), **kwargs)


def kms_python(code):
    return compose("exec", "-T", "api-kms", "python", "-c", code).stdout.strip()


def http_status(path, service="api-kms", port=8000):
    return int(kms_python(
        "import urllib.request, urllib.error\n"
        f"try:\n    print(urllib.request.urlopen('http://{service}:{port}{path}', timeout=8).status)\n"
        "except urllib.error.HTTPError as exc:\n    print(exc.code)\n"
    ))


def health(service):
    container = compose("ps", "-q", service).stdout.strip()
    return run(["docker", "inspect", "--format", "{{.State.Health.Status}}", container]).stdout.strip()


def eventually(predicate, label, timeout=90):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(2)
    raise AssertionError(f"Timed out: {label}")


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def database_check(insert=False):
    kms_python("""
import os
from pymongo import MongoClient
from pymongo.errors import OperationFailure
with MongoClient(host='mongodb', username=os.environ['MONGODB_USERNAME'],
                 password=os.environ['MONGODB_PASSWORD'],
                 authSource=os.environ['MONGODB_AUTH_SOURCE'],
                 serverSelectionTimeoutMS=3000) as client:
    database = client[os.environ['MONGODB_DATABASE']]
    roles = database.command('connectionStatus')['authInfo']['authenticatedUserRoles']
    assert roles == [{'role': 'readWrite', 'db': database.name}], roles
    assert 'active_chronological' in database.knowledge_items.index_information()
    if INSERT:
        database.stabilization_marker.insert_one({'_id': 'survives-restart'})
    assert database.stabilization_marker.count_documents({'_id': 'survives-restart'}) == 1
    try:
        client.forbidden_stabilization_test.marker.insert_one({'test': True})
    except OperationFailure as exc:
        assert exc.code == 13
    else:
        raise AssertionError('Application account can write outside its database')
""".replace("INSERT", repr(insert)))


def main():
    RESULTS.mkdir(exist_ok=True)
    report = {"project": PROJECT, "started_at": datetime.now(UTC).isoformat(),
              "checks": [], "success": False}

    def passed(label):
        report["checks"].append(label)
        print("PASS: " + label, flush=True)

    config = json.loads(compose("config", "--format", "json").stdout)
    require(all(not service.get("ports") for service in config["services"].values()),
            "Test ports must not be published")
    require(all(not volume.get("external") and volume["name"].startswith(PROJECT + "_")
                for volume in config["volumes"].values()), "Volumes must belong to the test project")
    require(config["services"]["mongodb"]["volumes"][0]["type"] == "volume",
            "MongoDB data must use a disposable named volume")
    passed("isolated Compose configuration; no published ports or development volumes")
    try:
        print("Building and starting isolated services...", flush=True)
        compose("up", "-d", "--build", "--wait", "--wait-timeout", "120", timeout=900)
        require(http_status("/health/ready") == 200, "KMS not ready")
        require(http_status("/health", "api-gateway", 3107) == 200, "Custom Gateway port failed")
        database_check(insert=True)
        passed("fresh bootstrap, least privileges, indexes, custom Gateway port 3107")

        compose("stop")
        compose("up", "-d", "--wait", "--wait-timeout", "120", timeout=180)
        database_check()
        passed("second startup preserves data and application account")

        compose("stop", "mongodb")
        require(http_status("/health") == 200, "Liveness must remain available")
        require(http_status("/health/ready") == 503, "Readiness must report MongoDB outage")
        require(http_status("/api/v1/knowledges") == 503, "CRUD must report MongoDB outage")
        eventually(lambda: health("api-kms") == "unhealthy", "Docker detects unavailable KMS")
        passed("MongoDB outage: liveness 200, readiness/CRUD 503, Docker unhealthy")

        compose("start", "mongodb")
        eventually(lambda: health("mongodb") == "healthy", "MongoDB recovers")
        eventually(lambda: http_status("/health/ready") == 200, "KMS recovers")
        eventually(lambda: health("api-kms") == "healthy", "Docker sees KMS recovery")
        database_check()
        passed("MongoDB recovery without KMS restart or data loss")

        bad = compose("run", "--rm", "--no-deps", "-e",
                      "MONGODB_PASSWORD=deliberately_wrong_test_password", "api-kms",
                      check=False, timeout=90)
        output = bad.stdout + bad.stderr
        require(bad.returncode != 0 and "MongoDB reste inaccessible" in output,
                "Bad credentials must fail application startup")
        require("deliberately_wrong_test_password" not in output,
                "Bad credentials leaked into logs")
        logs = compose("logs", "--no-color", "api-kms").stdout
        require(all(value not in logs for key, value in SETTINGS.items() if "PASSWORD" in key),
                "Credentials leaked into KMS logs")
        passed("incorrect credentials fail startup without disclosing passwords")
        report["success"] = True
    except BaseException:
        logs = compose("logs", "--no-color", check=False)
        (RESULTS / "stabilization-failure.log").write_text(
            redact(logs.stdout + logs.stderr), encoding="utf-8")
        raise
    finally:
        # PROJECT is generated here, never accepted from the environment or CLI.
        cleanup = compose("down", "--volumes", "--remove-orphans", check=False)
        report["cleanup_success"] = cleanup.returncode == 0
        report["success"] = report["success"] and report["cleanup_success"]
        (RESULTS / "stabilization.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
        require(report["cleanup_success"], "Disposable project cleanup failed")


if __name__ == "__main__":
    main()
