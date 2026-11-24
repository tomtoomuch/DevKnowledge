"""Qualify Supervisor identity on disposable volumes, with prepared-image offline replay.

Never reads .env or accepts a project name. Existing application data is not used.
"""
import argparse
import json
import os
from pathlib import Path
import subprocess
import time
from uuid import uuid4

from mongodb_backup import AUTH, backup, restore

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--offline", action="store_true")
    args = parser.parse_args()
    project = "devknowledge-identity-test-" + uuid4().hex[:12]
    settings = dict(line.split("=", 1) for line in (ROOT / "tests/stabilization.env").read_text().splitlines()
                    if line and not line.startswith("#"))
    env = {key: value for key, value in os.environ.items() if not key.startswith(
        ("COMPOSE_", "MONGODB_", "MONGO_INITDB_", "GATEWAY_", "KMS_", "SUPERVISOR_", "AUTH_", "FRONTEND_"))}
    env.update(settings)
    compose = ["docker", "compose", "--env-file", str(ROOT / "tests/stabilization.env"), "-p", project,
               "-f", str(ROOT / "compose.yaml"), "-f", str(ROOT / "tests/compose.identity.yaml")]
    directory = ROOT / "test-results" / project
    directory.mkdir(parents=True)
    report = {"project": project, "offline": args.offline, "checks": [], "success": False}
    restored_volume = None
    recovery = None

    def run(command, *, stdin=None, check=True, timeout=180):
        result = subprocess.run(command, cwd=ROOT, env=env, input=stdin, text=True,
                                encoding="utf-8", errors="replace", capture_output=True, timeout=timeout)
        if check and result.returncode:
            output = result.stdout + result.stderr
            for key, value in settings.items():
                if "PASSWORD" in key or "KEY" in key:
                    output = output.replace(value, "<test-secret>")
            raise RuntimeError(output[-6000:])
        return result

    def passed(label):
        report["checks"].append(label)
        print("PASS " + label, flush=True)

    def healthy(command):
        until = time.monotonic() + 120
        while time.monotonic() < until:
            rows = run(command + ["ps", "--format", "json"], check=False).stdout.strip()
            if rows:
                records = json.loads(rows) if rows.startswith("[") else [json.loads(line) for line in rows.splitlines()]
                if len(records) == 5 and all(row.get("Health") == "healthy" for row in records):
                    return
            time.sleep(2)
        raise RuntimeError("Identity stack did not become healthy")

    def probe(command, phase):
        script = (ROOT / "tests/identity_roundtrip.js").read_text(encoding="utf-8")
        result = run(command + ["exec", "-T", "-e", "IDENTITY_TEST_PHASE=" + phase, "api-gateway", "node", "-"], stdin=script)
        for label in json.loads(result.stdout)["checks"]:
            passed(phase + ": " + label)

    try:
        config = json.loads(run(compose + ["config", "--format", "json"]).stdout)
        assert all(not service.get("ports") for service in config["services"].values())
        assert all(network.get("internal") for network in config["networks"].values())
        assert config["services"]["api-kms"]["environment"]["KMS_SERVICE_TOKEN_MODE"] == "required"
        assert config["services"]["supervisor"]["environment"]["SUPERVISOR_IDENTITY_MODE"] == "active"
        passed("normal identity configuration, no published ports, both networks internal")
        if not args.offline:
            print("Building isolated identity stack", flush=True)
            result = run(compose + ["build"], timeout=900)
            (directory / "build.log").write_text(result.stdout + result.stderr, encoding="utf-8")
        run(compose + ["up", "-d", "--no-build", "--pull", "never"], timeout=180)
        healthy(compose)
        passed("all five services healthy with separate restricted MongoDB accounts")
        for container in run(compose + ["ps", "-q"]).stdout.split():
            actual = json.loads(run(["docker", "inspect", container]).stdout)[0]
            assert not actual["HostConfig"].get("PortBindings")
            for name in actual["NetworkSettings"]["Networks"]:
                network = json.loads(run(["docker", "network", "inspect", name]).stdout)[0]
                assert network["Internal"] is True
        passed("running containers use only internal networks and publish no host ports")
        report["images"] = json.loads(run(compose + ["images", "--format", "json"]).stdout)
        run(compose + ["exec", "-T", "supervisor", "node", "src/bootstrap-admin.js"],
            stdin=json.dumps({"username": "admin", "password": "identity-test-password-only"}))
        second = run(compose + ["exec", "-T", "supervisor", "node", "src/bootstrap-admin.js"],
                     stdin=json.dumps({"username": "second-admin", "password": "identity-test-password-only"}), check=False)
        assert second.returncode != 0
        passed("Supervisor bootstrap succeeds once and refuses overwriting existing accounts")
        # Synthetic legacy KMS account and pre-existing opaque session. No revision
        # or role_codes projection: resolve its original RBAC collections.
        seed = AUTH + """
const crypto = require('crypto');
const user = '59d6ec27-3cd4-4ae5-b60b-9ca0c1326c6a';
const role = database.roles.findOne({code:'READER'})._id;
database.users.insertOne({_id:user, username:'legacy-reader', username_key:'legacy-reader',
    account_status:'ACTIVE', password_hash:'scrypt$32768$8$3$05050505050505050505050505050505$ca11c67192cc87ee6897c100b896b31e3549d6d6080120d66614bcfac0b9fe095cfd50ce4c33c81527256fd44d0387a9187f7f8454b63e044c39310b845da012'});
database.user_roles.insertOne({_id:user+':'+role,user_id:user,role_id:role,assigned_at:new Date()});
database.sessions.insertOne({_id:crypto.createHash('sha256').update('c'.repeat(64)).digest('hex'),
    user_id:user,created_at:new Date(),expires_at:new Date(Date.now()+28800000)});
"""
        run(compose + ["exec", "-T", "mongodb", "mongosh", "--quiet", "--nodb", "--eval", seed])
        probe(compose, "initial")
        # Check real MongoDB authorization from each service's own credentials.
        restricted = """
const {MongoClient}=require('mongodb');
(async()=>{const c=new MongoClient('mongodb://mongodb:27017/', {auth:{username:process.env.MONGODB_USERNAME,password:process.env.MONGODB_PASSWORD},authSource:process.env.MONGODB_AUTH_SOURCE});
try{await c.connect();let refused=false;try{await c.db(process.env.MONGODB_DATABASE).collection('knowledge_items').findOne();}catch(e){refused=e.code===13;}if(!refused)throw Error('overprivileged');}
finally{await c.close();}})().catch(()=>process.exitCode=1);
"""
        run(compose + ["exec", "-T", "supervisor", "node", "-"], stdin=restricted)
        restricted_python = """
import os
from pymongo import MongoClient
from pymongo.errors import OperationFailure
with MongoClient('mongodb://mongodb:27017', username=os.environ['MONGODB_USERNAME'], password=os.environ['MONGODB_PASSWORD'], authSource=os.environ['MONGODB_AUTH_SOURCE']) as c:
    try:
        c[os.environ['MONGODB_DATABASE']]['users'].find_one()
    except OperationFailure as e:
        assert e.code == 13
    else:
        raise AssertionError('KMS can read identity')
"""
        run(compose + ["exec", "-T", "api-kms", "python", "-"], stdin=restricted_python)
        passed("MongoDB denies business reads to Supervisor and identity reads to KMS")
        run(compose + ["stop", "supervisor"])
        probe(compose, "outage")
        run(compose + ["start", "supervisor"])
        healthy(compose)
        run(compose + ["restart", "mongodb", "api-kms", "supervisor", "api-gateway"], timeout=180)
        healthy(compose)
        probe(compose, "recovery")
        passed("restart preserves historical accounts, sessions and knowledge access")
        run(compose + ["exec", "-T", "supervisor", "node", "src/metrics-backup.js",
                       "/var/lib/devknowledge-supervisor/identity-test-backup.sqlite3"])
        passed("SQLite online backup verifies integrity on the isolated metrics volume")
        backup(compose, directory / "backup", env=env)
        restored = restore(compose, directory / "backup", env=env, keep_volume=True)
        restored_volume = restored["volume"]
        assert restored["verified"]
        passed("MongoDB backup/restoration verifies documents, indexes and restricted service grants")
        healthy(compose)
        run(compose + ["stop"])
        overlay = directory / "restore.yaml"
        overlay.write_text("volumes:\n  mongodb:\n    external: true\n    name: " + restored_volume + "\n    driver: !reset null\n", encoding="utf-8")
        recovery = compose.copy()
        recovery[recovery.index("-p") + 1] = project + "-restored"
        recovery += ["-f", str(overlay)]
        run(recovery + ["up", "-d", "--no-build", "--pull", "never"], timeout=180)
        healthy(recovery)
        probe(recovery, "recovery")
        passed("restored application starts offline and accepts the historical session")
        report["success"] = True
    except Exception as exc:
        report["error"] = str(exc)
        raise
    finally:
        for command in [recovery, compose]:
            if command:
                result = run(command + ["logs", "--no-color"], check=False)
                suffix = "restored" if command is recovery else "source"
                (directory / (suffix + ".log")).write_text(result.stdout, encoding="utf-8")
                cleanup = run(command + ["down", "--volumes"], check=False)
                report[suffix + "_cleanup"] = cleanup.returncode == 0
        if restored_volume:
            report["restore_volume_cleanup"] = run(["docker", "volume", "rm", restored_volume], check=False).returncode == 0
        (directory / "summary.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
        print("Report: " + str(directory / "summary.json"), flush=True)


if __name__ == "__main__":
    main()
