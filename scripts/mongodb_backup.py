"""Local, explicit backups; restoration always allocates a NEW isolated volume.

No production restore target is accepted. Credentials stay in process/container
environments or a mode-0600 temporary configuration file inside MongoDB.
"""
import argparse
from datetime import UTC, datetime
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import time
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
AUTH = """
const connection = new Mongo('mongodb://127.0.0.1:27017');
const admin = connection.getDB('admin');
if (!admin.auth(process.env.MONGO_INITDB_ROOT_USERNAME, process.env.MONGO_INITDB_ROOT_PASSWORD))
    throw new Error('Authentication failed');
const database = connection.getDB(process.env.MONGODB_DATABASE);
"""
SNAPSHOT = AUTH + """
const crypto = require('crypto');
const collections = [];
for (const info of database.getCollectionInfos().sort((a,b) => a.name.localeCompare(b.name))) {
    if (info.name.startsWith('system.')) continue;
    if (info.type !== 'collection') throw new Error('Unsupported collection type');
    const collection = database.getCollection(info.name);
    const hash = crypto.createHash('sha256');
    let count = 0;
    const cursor = collection.find().sort({_id: 1});
    while (cursor.hasNext()) {
        hash.update(EJSON.stringify(cursor.next(), {relaxed: false}) + '\\n');
        count++;
    }
    collections.push({name: info.name, count, sha256: hash.digest('hex'),
        indexes: collection.getIndexes().sort((a,b) => a.name.localeCompare(b.name)),
        options: info.options});
}
print(EJSON.stringify({database: database.getName(), server_version: connection.getDB('admin').version(), collections}, {relaxed: false}));
"""
TOOL = """
const fs = require('fs');
const child = require('child_process');
const dir = fs.mkdtempSync('/tmp/devknowledge-backup-');
const config = dir + '/credentials.json';
let code = 1;
try {
    fs.writeFileSync(config, JSON.stringify({password: process.env.MONGO_INITDB_ROOT_PASSWORD}), {mode: 0o600});
    const mode = MODE;
    const args = ['--host', '127.0.0.1', '--username', process.env.MONGO_INITDB_ROOT_USERNAME,
        '--authenticationDatabase', 'admin', '--config', config, '--archive', '--gzip'];
    if (mode === 'mongodump') args.push('--db', process.env.MONGODB_DATABASE);
    else args.push('--nsInclude', process.env.MONGODB_DATABASE + '.*', '--stopOnError');
    const result = child.spawnSync(mode, args, {stdio: ['inherit', 'inherit', 'pipe']});
    code = result.status === 0 ? 0 : 1;
} finally {
    fs.rmSync(config, {force: true});
    fs.rmdirSync(dir);
}
process.exit(code);
"""


def run(command, *, env=None, stdin=None, stdout=subprocess.PIPE, check=True, timeout=300):
    result = subprocess.run(command, cwd=ROOT, env=env, stdin=stdin, stdout=stdout,
                            stderr=subprocess.PIPE, timeout=timeout)
    if check and result.returncode:
        # Tool/driver errors may contain secrets or document contents.
        raise RuntimeError(f"Backup operation failed (exit {result.returncode}); no credentials logged")
    return result


def digest(path):
    with Path(path).open("rb") as source:
        return hashlib.file_digest(source, "sha256").hexdigest()


def configuration(compose, env):
    config = json.loads(run(compose + ["config", "--format", "json"], env=env).stdout)
    database = config["services"]["mongodb"]["environment"]["MONGODB_DATABASE"]
    if not re.fullmatch(r"[A-Za-z0-9_-]+", database) or database in {"admin", "config", "local"}:
        raise ValueError("Backup requires a non-system database with a simple namespace")
    return config


def shell(prefix, script, **kwargs):
    return run(prefix + ["mongosh", "--quiet", "--nodb", "--eval", script], **kwargs)


def snapshot(prefix, env):
    return json.loads(shell(prefix, SNAPSHOT, env=env).stdout)


def backup(compose, directory, *, env=None):
    config = configuration(compose, env)
    directory = Path(directory).resolve()
    directory.mkdir(mode=0o700, parents=True, exist_ok=False)  # Never overwrite any backup.
    archive = directory / "database.archive.gz"
    partial = directory / "database.archive.gz.partial"
    running = run(compose + ["ps", "--status", "running", "--services"], env=env).stdout.decode().split()
    if "mongodb" not in running:
        raise RuntimeError("MongoDB must already be running")
    writers = [name for name in ("api-gateway", "api-kms") if name in running]
    prefix = compose + ["exec", "-T", "mongodb"]
    try:
        if writers:
            print("Backup: stopping application writers temporarily", flush=True)
            run(compose + ["stop", *writers], env=env)
        before = snapshot(prefix, env)
        if before["database"] != config["services"]["mongodb"]["environment"]["MONGODB_DATABASE"]:
            raise RuntimeError("Running database differs from the selected configuration")
        with partial.open("xb") as output:
            shell(prefix, TOOL.replace("MODE", json.dumps("mongodump")), env=env, stdout=output)
            output.flush()
            os.fsync(output.fileno())
        after = snapshot(prefix, env)
        if before != after:
            raise RuntimeError("Database changed during backup; archive is not certified")
        partial.rename(archive)  # Destination belongs to this newly created directory.
        manifest = {"format": 1, "created_at": datetime.now(UTC).isoformat(),
                    "archive_sha256": digest(archive), "snapshot": before,
                    "image": config["services"]["mongodb"]["image"]}
        (directory / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        return manifest
    finally:
        # Preserve initially stopped services; never start the whole application.
        if writers:
            run(compose + ["start", *writers], env=env)


def read_backup(directory):
    directory = Path(directory).resolve()
    manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
    if manifest.get("format") != 1 or not isinstance(manifest.get("snapshot"), dict):
        raise ValueError("Unsupported backup manifest")
    archive = directory / "database.archive.gz"
    if digest(archive) != manifest.get("archive_sha256"):
        raise ValueError("Backup checksum mismatch; restoration refused")
    return archive, manifest


def restore(compose, directory, *, env=None, keep_volume=False):
    archive, manifest = read_backup(directory)  # Verify before allocating anything.
    config = configuration(compose, env)
    settings = config["services"]["mongodb"]["environment"]
    database = settings["MONGODB_DATABASE"]
    if manifest["snapshot"]["database"] != database:
        raise ValueError("Backup database differs from the configured database")
    # Recovery must also work offline; never download an image implicitly.
    run(["docker", "image", "inspect", config["services"]["mongodb"]["image"]], env=env)
    token = uuid4().hex
    container = "devknowledge-restore-" + token
    volume = "devknowledge-restored-" + token
    target_env = dict(os.environ if env is None else env)
    for key in ("MONGO_INITDB_ROOT_USERNAME", "MONGO_INITDB_ROOT_PASSWORD",
                "MONGODB_DATABASE", "MONGODB_APP_USERNAME", "MONGODB_APP_PASSWORD"):
        target_env[key] = str(settings[key])
    target_env["DK_APP_AUTH_SOURCE"] = config["services"]["api-kms"]["environment"]["MONGODB_AUTH_SOURCE"]
    prefix = ["docker", "exec", "-i", container]
    verified = False
    container_created = False
    run(["docker", "volume", "create", "--label", f"devknowledge.restore={token}", volume], env=target_env)
    try:
        command = ["docker", "run", "--pull", "never", "-d", "--name", container, "--network", "none",
                   "--label", f"devknowledge.restore={token}",
                   "--mount", f"type=volume,source={volume},target=/data/db", "--tmpfs", "/data/configdb"]
        for key in ("MONGO_INITDB_ROOT_USERNAME", "MONGO_INITDB_ROOT_PASSWORD", "MONGODB_DATABASE",
                    "MONGODB_APP_USERNAME", "MONGODB_APP_PASSWORD", "DK_APP_AUTH_SOURCE"):
            command += ["-e", key]
        command += [config["services"]["mongodb"]["image"]]
        run(command, env=target_env)
        container_created = True
        deadline = time.monotonic() + 90
        while True:
            final_server = run(["docker", "exec", container, "sh", "-c",
                                'test "$(cat /proc/1/comm)" = mongod'], env=target_env, check=False)
            ready = shell(prefix, AUTH + "print(admin.runCommand({ping:1}).ok)",
                          env=target_env, check=False, timeout=15)
            if final_server.returncode == 0 and ready.returncode == 0:
                break
            if time.monotonic() >= deadline:
                raise RuntimeError("Isolated restore MongoDB did not become ready")
            time.sleep(1)
        empty = snapshot(prefix, target_env)
        if empty["collections"]:
            raise RuntimeError("Restore target is not empty")
        if empty["server_version"].split(".")[0] != manifest["snapshot"]["server_version"].split(".")[0]:
            raise ValueError("Restore requires the same MongoDB major version")
        with archive.open("rb") as source:
            shell(prefix, TOOL.replace("MODE", json.dumps("mongorestore")), env=target_env, stdin=source)
        restored = snapshot(prefix, target_env)
        if restored["collections"] != manifest["snapshot"]["collections"]:
            raise RuntimeError("Restored documents, indexes or collection options differ")
        # Re-provision users from current local config; database dumps exclude users/secrets.
        shell(prefix, AUTH + """
const authDb = connection.getDB(process.env.DK_APP_AUTH_SOURCE);
authDb.createUser({user: process.env.MONGODB_APP_USERNAME, pwd: process.env.MONGODB_APP_PASSWORD,
    roles: [{role: 'readWrite', db: database.getName()}]});
const appConnection = new Mongo('mongodb://127.0.0.1:27017');
if (!appConnection.getDB(process.env.DK_APP_AUTH_SOURCE).auth(process.env.MONGODB_APP_USERNAME, process.env.MONGODB_APP_PASSWORD))
    throw new Error('Restored application account failed');
appConnection.getDB(database.getName()).getCollectionNames();
""", env=target_env)
        verified = True
        return {"verified": True, "database": database,
                "volume": volume if keep_volume else None,
                "collections": len(restored["collections"])}
    finally:
        if container_created:
            run(["docker", "stop", container], env=target_env)
            run(["docker", "rm", container], env=target_env)
        if not (verified and keep_volume):
            run(["docker", "volume", "rm", volume], env=target_env)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=["backup", "restore-check", "restore"])
    parser.add_argument("directory", type=Path, help="New backup directory, or existing backup to restore")
    parser.add_argument("--project", default="devknowledge")
    parser.add_argument("--env-file", default=str(ROOT / ".env"))
    args = parser.parse_args()
    compose = ["docker", "compose", "--env-file", str(Path(args.env_file).resolve()),
               "-p", args.project, "-f", str(ROOT / "compose.yaml")]
    if args.operation == "backup":
        backup(compose, args.directory)
        print(f"Backup complete: {args.directory.resolve()}")
    else:
        print(json.dumps(restore(compose, args.directory, keep_volume=args.operation == "restore")))


if __name__ == "__main__":
    main()
