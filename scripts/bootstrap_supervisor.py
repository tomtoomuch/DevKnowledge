"""Create the first local admin using stdin and a hidden password prompt."""
import argparse
import getpass
import json
import subprocess
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--username", default="admin")
    parser.add_argument("--project")
    parser.add_argument("--env-file", type=Path)
    args = parser.parse_args()
    password = getpass.getpass("Administrator password: ")
    if password != getpass.getpass("Confirm password: "):
        raise SystemExit("Passwords differ")
    command = ["docker", "compose"]
    if args.project:
        command += ["-p", args.project]
    if args.env_file:
        command += ["--env-file", str(args.env_file.resolve())]
    result = subprocess.run(
        command + ["exec", "-T", "supervisor", "node", "src/bootstrap-admin.js"],
        cwd=Path(__file__).resolve().parents[1],
        input=json.dumps({"username": args.username, "password": password}),
        text=True, encoding="utf-8", check=False,
    )
    raise SystemExit(result.returncode)


if __name__ == "__main__":
    main()
