"""Read-only Docker Compose volume audit; never starts/stops containers.

Run from the repository root:
  python scripts/persistence_check.py
  python scripts/persistence_check.py --project devknowledge --env-file .env
"""
import argparse
import json
import subprocess
import sys


class PersistenceError(RuntimeError):
    pass


def docker(*args: str) -> str:
    try:
        result = subprocess.run(
            ["docker", *args], capture_output=True, check=True, text=True,
            timeout=25,
        )
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError):
        # Do not print docker compose config error details, which can contain secrets.
        raise PersistenceError("Docker unavailable or volume audit command failed") from None
    return result.stdout.strip()


def inspect(*, project: str | None = None, env_file: str | None = None) -> dict:
    compose = ["compose"]
    if project:
        compose += ["-p", project]
    if env_file:
        compose += ["--env-file", env_file]
    config = json.loads(docker(*compose, "config", "--format", "json"))
    project_name = config["name"]
    service = config["services"]["mongodb"]
    volumes = config["volumes"]
    mounts = {mount["target"]: mount for mount in service.get("volumes", [])}
    expected = {}
    for mountpoint, logical in (("/data/db", "mongodb"), ("/data/configdb", "mongodb-configdb")):
        mount = mounts.get(mountpoint)
        if not mount or mount.get("type") != "volume" or mount.get("source") != logical:
            raise PersistenceError(f"Expected named volume {logical} at {mountpoint}")
        expected[mountpoint] = volumes[logical]["name"]

    # Read-only inspection: even an absent container does NOT create a volume.
    container = docker(*compose, "ps", "-q", "mongodb").strip()
    candidates = docker("volume", "ls", "-q",
                        "--filter", "label=com.docker.compose.volume=mongodb").splitlines()
    output = {
        "project": project_name,
        "expected_mounts": expected,
        "other_compose_mongodb_volumes": sorted(v for v in candidates
                                                 if v != expected["/data/db"]),
        "container_running": bool(container),
        "mounted": {},
        "status": "not_running",
    }
    if not container:
        return output
    info = json.loads(docker("inspect", container))
    found = {m["Destination"]: m for m in info[0].get("Mounts", [])}
    for mountpoint, volume_name in expected.items():
        actual = found.get(mountpoint, {})
        output["mounted"][mountpoint] = actual.get("Name") if actual.get("Type") == "volume" else None
        if output["mounted"][mountpoint] != volume_name:
            output["status"] = "mismatch"
            return output
    output["status"] = "ok"
    return output


def main() -> int:
    parser = argparse.ArgumentParser(description="Read-only check of DevKnowledge MongoDB volumes")
    parser.add_argument("--project", help="Exact original Compose project name (optional)")
    parser.add_argument("--env-file", help="Compose environment file (optional)")
    args = parser.parse_args()
    try:
        result = inspect(project=args.project, env_file=args.env_file)
    except PersistenceError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2, ensure_ascii=False))
    if result["status"] != "ok":
        print("Volume audit incomplete or inconsistent: no data changed.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
