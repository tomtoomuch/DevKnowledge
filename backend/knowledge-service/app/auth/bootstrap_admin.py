"""One-time operator command: python -m app.auth.bootstrap_admin --username admin."""
import argparse
import asyncio
import getpass
import os
import sys
from datetime import UTC

from pymongo import AsyncMongoClient
from app.auth.local import bootstrap_admin, initialize_identity, username_key


async def setup(username, password):
    name = os.getenv("MONGODB_DATABASE", "devknowledge")
    client = AsyncMongoClient(
        host=os.getenv("MONGODB_HOST", "localhost"), port=int(os.getenv("MONGODB_PORT", "27017")),
        username=os.environ["MONGODB_USERNAME"], password=os.environ["MONGODB_PASSWORD"],
        authSource=os.getenv("MONGODB_AUTH_SOURCE", name),
        serverSelectionTimeoutMS=3000, tz_aware=True, tzinfo=UTC,
    )
    try:
        db = client[name]
        await initialize_identity(db)
        user = await bootstrap_admin(db, username, password)
        print("Administrateur créé :", user["username"])
    finally:
        await client.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Bootstrap first local administrator")
    parser.add_argument("--username", default="admin")
    args = parser.parse_args()
    try:
        username = username_key(args.username)
        password = getpass.getpass("Mot de passe (12 à 256 caractères) : ")
        confirmation = getpass.getpass("Confirmer le mot de passe : ")
        if password != confirmation:
            raise ValueError("Passwords differ")
        asyncio.run(setup(username, password))
    except (ValueError, RuntimeError, KeyError) as exc:
        print(f"Initialisation refusée : {exc}", file=sys.stderr)
        raise SystemExit(1) from None
