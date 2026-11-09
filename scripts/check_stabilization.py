"""Exercise the production Compose configuration without using development data.

Python standard library only. A unique project owns a new volume, removed in
finally. Never accepts a project name or credentials from the caller.
"""

import argparse
import json
import os
from datetime import datetime, UTC
from pathlib import Path
import subprocess
import time
from uuid import uuid4
from mongodb_backup import backup, restore, read_backup


ROOT = Path(__file__).resolve().parents[1]
PROJECT = "devknowledge-stabilization-test-" + uuid4().hex[:12]
SETTINGS = dict(
    line.split("=", 1)
    for line in (ROOT / "tests/stabilization.env").read_text().splitlines()
    if line and not line.startswith("#")
)
# Explicitly suppress inherited configuration and never load the user's .env.
ENV = {key: value for key, value in os.environ.items()
       if not key.startswith(("COMPOSE_", "MONGODB_", "MONGO_INITDB_", "GATEWAY_", "KMS_"))}
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


def gateway_status(path):
    code = f"fetch('http://127.0.0.1:3107{path}', {{signal: AbortSignal.timeout(15000)}}).then(r => console.log(r.status))"
    return int(compose("exec", "-T", "api-gateway", "node", "-e", code).stdout.strip())


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


def local_images(config):
    """Fail before resource creation if any prepared image is absent locally."""
    images = {}
    for service, settings in config["services"].items():
        reference = settings["image"]
        result = run(["docker", "image", "inspect", reference], check=False)
        require(result.returncode == 0,
                f"Missing local image for {service}: {reference}; prepare images before --offline")
        image = json.loads(result.stdout)[0]
        images[service] = {"reference": reference, "id": image["Id"],
                           "platform": image["Os"] + "/" + image["Architecture"]}
    return images


def verify_offline_network(images):
    """Inspect actual runtime attachments and routes, not only Compose intent."""
    network_name = PROJECT + "_default"
    network = json.loads(run(["docker", "network", "inspect", network_name]).stdout)[0]
    require(network["Internal"] and not network["EnableIPv6"],
            "Offline test requires an internal IPv4-only network")
    for service, image in images.items():
        container_id = compose("ps", "-q", service).stdout.strip()
        container = json.loads(run(["docker", "inspect", container_id]).stdout)[0]
        require(container["Image"] == image["id"], "Running image differs from preflight")
        attachments = container["NetworkSettings"]["Networks"]
        require(set(attachments) == {network_name}, "Service has an unexpected network attachment")
        require(not attachments[network_name].get("GlobalIPv6Address"), "Unexpected IPv6 address")
        routes = compose("exec", "-T", service, "cat", "/proc/net/route").stdout.splitlines()[1:]
        require(not any(line.split()[1] == "00000000" for line in routes if line.strip()),
                f"{service} has an external default route")
    # TEST-NET address; expect a routing refusal, not an arbitrary unavailable server.
    kms_python("""
import errno, socket
try:
    connection = socket.create_connection(('198.51.100.1', 443), timeout=3)
except OSError as error:
    assert error.errno == errno.ENETUNREACH, type(error).__name__
else:
    connection.close()
    raise AssertionError('External connection unexpectedly succeeded')
""")
    return {"network": network_name, "internal": True, "ipv6": False,
            "services_without_default_route": sorted(images), "external_probe": "ENETUNREACH"}


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
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--offline", action="store_true",
                        help="Use prepared local images; forbid builds/pulls and verify runtime isolation")
    args = parser.parse_args()
    RESULTS.mkdir(exist_ok=True)
    report_name = "stabilization-offline" if args.offline else "stabilization"
    report = {"project": PROJECT, "started_at": datetime.now(UTC).isoformat(),
              "offline": args.offline, "checks": [], "success": False}

    def passed(label):
        report["checks"].append(label)
        print("PASS: " + label, flush=True)

    config = json.loads(compose("config", "--format", "json").stdout)
    base_config = json.loads(run(COMPOSE[:-2] + ["config", "--format", "json"]).stdout)
    require(not base_config["services"]["api-kms"].get("ports"), "KMS must remain internal by default")
    require(not base_config["services"]["mongodb"].get("ports"), "MongoDB must remain internal")
    require(all(port.get("host_ip") == "127.0.0.1"
                for port in base_config["services"]["api-gateway"]["ports"]),
            "Gateway must only bind to localhost")
    require(all(not service.get("ports") for service in config["services"].values()),
            "Test ports must not be published")
    require(all(not volume.get("external") and volume["name"].startswith(PROJECT + "_")
                for volume in config["volumes"].values()), "Volumes must belong to the test project")
    require(config["services"]["mongodb"]["volumes"][0]["type"] == "volume",
            "MongoDB data must use a disposable named volume")
    passed("isolated Compose configuration; no published ports or development volumes")
    try:
        if args.offline:
            report["images"] = local_images(config)
            passed("all prepared images available locally; builds and pulls forbidden")
        print("Starting prepared services..." if args.offline else "Building and starting isolated services...", flush=True)
        startup = ["--no-build", "--pull", "never"] if args.offline else ["--build"]
        compose("up", "-d", *startup, "--wait", "--wait-timeout", "120", timeout=900)
        if args.offline:
            report["network"] = verify_offline_network(report["images"])
            passed("runtime network isolated; no external default route; outbound connection refused")
        require(http_status("/health/ready") == 200, "KMS not ready")
        require(http_status("/health", "api-gateway", 3107) == 200, "Custom Gateway port failed")
        database_check(insert=True)
        passed("fresh bootstrap, least privileges, indexes, custom Gateway port 3107")
        print(kms_python((ROOT / "tests/gateway_contract.py").read_text(encoding="utf-8")), flush=True)
        passed("Gateway end-to-end CRUD and validation errors")
        # Keep one active knowledge alongside the soft-deleted CRUD fixture.
        active_id = kms_python("""
import json, urllib.request
payload = json.dumps({'knowledge_type': 'COURSE_NOTE', 'title': 'Backup active fixture',
                      'content': 'Preserve active knowledge and its revision'}).encode()
request = urllib.request.Request('http://api-gateway:3107/api/v1/knowledges', data=payload,
                                 headers={'Content-Type': 'application/json'}, method='POST')
with urllib.request.urlopen(request) as response:
    assert response.status == 201
    print(json.load(response)['knowledge_id'])
""")
        backup_dir = RESULTS / ("backup-fixture-" + uuid4().hex)
        manifest = backup(COMPOSE, backup_dir, env=ENV)
        restored = restore(COMPOSE, backup_dir, env=ENV, keep_volume=True)
        volume = restored["volume"]
        require(volume.startswith("devknowledge-restored-"), "Unexpected recovery volume name")
        try:
            require(restored["verified"], "Restore verification failed")
            run(["docker", "volume", "inspect", volume])
            require(manifest["snapshot"]["collections"], "Backup fixture was empty")
            items = next(item for item in manifest["snapshot"]["collections"] if item["name"] == "knowledge_items")
            require(items["count"] == {"$numberInt": "2"},
                    "Backup must include active and soft-deleted knowledge")
        finally:
            run(["docker", "volume", "rm", volume])
        # Verify corruption is detected before any restoration resources are created.
        archive = backup_dir / "database.archive.gz"
        original = archive.read_bytes()
        archive.write_bytes(original + b"corrupt")
        try:
            try:
                read_backup(backup_dir)
            except ValueError:
                pass
            else:
                raise AssertionError("Corrupted backup accepted")
        finally:
            archive.write_bytes(original)
        eventually(lambda: gateway_status("/health/ready") == 200, "Writers resume after backup")
        require(gateway_status("/api/v1/knowledges/" + active_id) == 200, "Source knowledge must remain readable")
        database_check()
        passed("BSON backup/restore: documents, revisions, soft deletions, indexes, checksum and isolated recovery volume")

        compose("stop")
        compose("up", "-d", "--no-build", "--pull", "never", "--wait", "--wait-timeout", "120", timeout=180)
        if args.offline:
            verify_offline_network(report["images"])
        database_check()
        passed("second startup preserves data and application account")

        compose("stop", "mongodb")
        require(http_status("/health") == 200, "Liveness must remain available")
        require(http_status("/health/ready") == 503, "Readiness must report MongoDB outage")
        require(http_status("/api/v1/knowledges") == 503, "CRUD must report MongoDB outage")
        require(gateway_status("/health") == 200, "Gateway liveness must remain available")
        require(gateway_status("/health/ready") == 503, "Gateway readiness must report MongoDB outage")
        require(gateway_status("/api/v1/knowledges") == 503, "Gateway must preserve KMS 503")
        eventually(lambda: health("api-kms") == "unhealthy", "Docker detects unavailable KMS")
        eventually(lambda: health("api-gateway") == "unhealthy", "Docker detects unavailable Gateway dependency")
        passed("MongoDB outage: liveness 200, readiness/CRUD 503, Docker unhealthy")

        compose("start", "mongodb")
        eventually(lambda: health("mongodb") == "healthy", "MongoDB recovers")
        eventually(lambda: http_status("/health/ready") == 200, "KMS recovers")
        eventually(lambda: health("api-kms") == "healthy", "Docker sees KMS recovery")
        eventually(lambda: health("api-gateway") == "healthy", "Docker sees Gateway recovery")
        database_check()
        passed("MongoDB recovery without KMS restart or data loss")

        compose("stop", "api-kms")
        require(gateway_status("/health") == 200, "Gateway liveness must survive KMS outage")
        require(gateway_status("/health/ready") == 502, "Gateway readiness must detect KMS outage")
        require(gateway_status("/api/v1/knowledges") == 502, "Gateway must report unreachable KMS")
        compose("start", "api-kms")
        eventually(lambda: gateway_status("/health/ready") == 200, "Gateway recovers after KMS restart")
        eventually(lambda: health("api-gateway") == "healthy", "Gateway healthy after KMS restart")
        passed("KMS outage: Gateway liveness 200, readiness/CRUD 502, automatic recovery")

        bad = compose("run", "--rm", "--no-deps", "--pull", "never", "-e",
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
        (RESULTS / (report_name + "-failure.log")).write_text(
            redact(logs.stdout + logs.stderr), encoding="utf-8")
        raise
    finally:
        # PROJECT is generated here, never accepted from the environment or CLI.
        cleanup = compose("down", "--volumes", "--remove-orphans", check=False)
        report["cleanup_success"] = cleanup.returncode == 0
        report["success"] = report["success"] and report["cleanup_success"]
        (RESULTS / (report_name + ".json")).write_text(json.dumps(report, indent=2), encoding="utf-8")
        require(report["cleanup_success"], "Disposable project cleanup failed")


if __name__ == "__main__":
    main()
