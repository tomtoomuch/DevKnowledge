"""Real MongoDB tests opt in explicitly and own a disposable database."""

import os
from contextlib import asynccontextmanager
from datetime import UTC
from uuid import uuid4

import pytest
from pymongo import AsyncMongoClient


@pytest.fixture
def isolated_database():
    uri = os.getenv("KMS_TEST_MONGODB_URI")
    if not uri:
        pytest.skip("Set KMS_TEST_MONGODB_URI to an isolated MongoDB instance")

    @asynccontextmanager
    async def connect():
        # No development database name can enter this fixture or its cleanup.
        database_name = f"devknowledge_test_{uuid4().hex}"
        client = AsyncMongoClient(uri, tz_aware=True, tzinfo=UTC, serverSelectionTimeoutMS=3000)
        try:
            await client.admin.command("ping")
            yield client[database_name]
        finally:
            try:
                if database_name.startswith("devknowledge_test_") and len(database_name) == 50:
                    await client.drop_database(database_name)
            finally:
                await client.close()

    return connect
