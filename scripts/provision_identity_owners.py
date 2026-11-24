"""Provision new restricted MongoDB owners after verifying an isolated restore.

Explicit operator command for an existing installation; never invoked at startup.
The selected backup must match the stopped source before grants are created.
"""
import argparse
import json
import os
from pathlib import Path

from mongodb_backup import AUTH, ROOT, configuration, read_backup, restore, run, shell, snapshot


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", required=True)
    parser.add_argument("--env-file", type=Path, required=True)
    parser.add_argument("--backup", type=Path, required=True)
    args = parser.parse_args()
    compose = ["docker", "compose", "--env-file", str(args.env_file.resolve()), "-p", args.project,
               "-f", str(ROOT / "compose.yaml")]
    config = configuration(compose, None)
    settings = config["services"]["mongodb"]["environment"]
    _, manifest = read_backup(args.backup)
    if manifest["snapshot"]["database"] != settings["MONGODB_DATABASE"]:
        raise SystemExit("Backup does not match the selected database")
    # Stop all potential application writers; leave them stopped for cutover.
    run(compose + ["stop", "api-gateway", "api-kms", "supervisor"])
    prefix = compose + ["exec", "-T", "mongodb"]
    if snapshot(prefix, None)["collections"] != manifest["snapshot"]["collections"]:
        raise SystemExit("Source changed since backup. Writers remain stopped; create a new backup.")
    restore(compose, args.backup, keep_volume=False)
    env = dict(os.environ)
    command = compose + ["exec", "-T"]
    for name in ("MONGODB_DATABASE", "MONGODB_APP_USERNAME", "MONGO_INITDB_ROOT_USERNAME",
                 "MONGODB_KMS_USERNAME", "MONGODB_KMS_PASSWORD",
                 "MONGODB_SUPERVISOR_USERNAME", "MONGODB_SUPERVISOR_PASSWORD"):
        env[name] = str(settings[name])
        command += ["-e", name]
    command += ["mongodb"]
    script = (ROOT / "backend/mongodb/ops/provision-identity-owners.js").read_text(encoding="utf-8")
    shell(command, AUTH + "globalThis.db = database;\n" + script, env=env)
    print(json.dumps({"provisioned": True, "writers_stopped": True,
                      "message": "Restricted accounts verified. Existing passwords and documents unchanged."}))


if __name__ == "__main__":
    main()
