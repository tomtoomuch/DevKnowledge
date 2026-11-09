"""Fail fast when a Compose build context or Dockerfile is missing.

Uses Docker Compose's own path resolution, never guesses paths from the shell's
current directory. Does not print resolved environment values or passwords.
"""
import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def verify_builds(config: dict) -> list[tuple[str, Path]]:
    found = []
    for name, service in sorted(config.get("services", {}).items()):
        build = service.get("build")
        if build is None:
            continue
        if isinstance(build, str):
            build = {"context": build}
        raw_context = build.get("context")
        if not isinstance(raw_context, str) or not raw_context:
            raise ValueError(f"{name}: build context missing")
        context = Path(raw_context)
        if not context.is_absolute():
            context = ROOT / context
        if not context.is_dir():
            raise ValueError(f"{name}: context directory missing: {context}")
        raw_dockerfile = build.get("dockerfile", "Dockerfile")
        if not isinstance(raw_dockerfile, str) or not raw_dockerfile:
            raise ValueError(f"{name}: Dockerfile name missing")
        filename = Path(raw_dockerfile)
        if not filename.is_absolute():
            filename = context / filename
        if not filename.is_file():
            raise ValueError(f"{name}: Dockerfile missing: {filename}")
        # Guard accidentally referenced files outside this repository.
        if not filename.resolve().is_relative_to(ROOT):
            raise ValueError(f"{name}: Dockerfile outside DevKnowledge: {filename}")
        # Check exact case, even when run on case-insensitive Windows/NTFS.
        parent = filename.parent
        if filename.name not in {entry.name for entry in parent.iterdir()}:
            raise ValueError(f"{name}: filename case mismatch: {filename}")
        found.append((name, filename.resolve()))
    if not found:
        raise ValueError("No build services found in Compose configuration")
    return found


def main():
    parser = argparse.ArgumentParser(description="Validate real Docker Compose build paths")
    parser.add_argument("--compose", default="compose.yaml")
    parser.add_argument("--env-file")
    args = parser.parse_args()
    compose_file = (ROOT / args.compose).resolve()
    if not compose_file.is_relative_to(ROOT) or not compose_file.is_file():
        raise SystemExit("Compose file missing or outside repository")
    command = ["docker", "compose"]
    if args.env_file:
        env_file = (ROOT / args.env_file).resolve()
        if not env_file.is_relative_to(ROOT) or not env_file.is_file():
            raise SystemExit("Compose env file missing or outside repository")
        command.extend(["--env-file", str(env_file)])
    command += ["-f", str(compose_file), "config", "--format", "json"]
    try:
        result = subprocess.run(command, cwd=ROOT, check=True,
                                capture_output=True, text=True, timeout=45)
        builds = verify_builds(json.loads(result.stdout))
    except FileNotFoundError:
        raise SystemExit("Docker Compose executable unavailable") from None
    except subprocess.CalledProcessError:
        raise SystemExit("Cannot resolve Compose config: check credentials and YAML (no secrets printed)") from None
    except (ValueError, json.JSONDecodeError) as exc:
        raise SystemExit(f"Docker build path verification failed: {exc}") from None
    for name, dockerfile in builds:
        print(f"OK {name}: {dockerfile.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
