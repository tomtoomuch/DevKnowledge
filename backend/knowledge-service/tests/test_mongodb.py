"""Connection ownership, retries and startup safety without a MongoDB server."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from fastapi import FastAPI
from pymongo.errors import ConnectionFailure

from app.db import mongodb


@pytest.fixture
def setup_connection(monkeypatch):
    monkeypatch.setenv("MONGODB_USERNAME", "test-user")
    monkeypatch.setenv("MONGODB_PASSWORD", "test-password")
    monkeypatch.setenv("MONGODB_DATABASE", "devknowledge_test_lifespan")
    database = object()
    client = Mock()
    client.__getitem__ = Mock(return_value=database)
    client.admin = SimpleNamespace(command=AsyncMock())
    client.close = AsyncMock()
    constructor = Mock(return_value=client)
    monkeypatch.setattr(mongodb, "AsyncMongoClient", constructor)
    indexes = AsyncMock()
    repository = Mock(return_value=SimpleNamespace(ensure_indexes=indexes))
    monkeypatch.setattr(mongodb, "MongoKnowledgeRepository", repository)
    monkeypatch.setattr(
        mongodb, "MongoKnowledgeTypeRepository",
        Mock(return_value=SimpleNamespace(ensure_catalog=AsyncMock())),
    )
    # The identity subsystem shares this database but is initialized separately.
    monkeypatch.setattr(mongodb, "initialize_identity", AsyncMock())
    delay = AsyncMock()
    monkeypatch.setattr(mongodb.asyncio, "sleep", delay)
    return client, database, constructor, indexes, delay


def test_lifespan_requires_credentials(monkeypatch):
    monkeypatch.delenv("MONGODB_USERNAME", raising=False)
    monkeypatch.delenv("MONGODB_PASSWORD", raising=False)
    async def scenario():
        with pytest.raises(RuntimeError, match="Configuration MongoDB incomplète"):
            async with mongodb.lifespan(FastAPI()):
                pytest.fail("startup must fail")
    asyncio.run(scenario())


def test_one_client_and_indexes_for_lifespan(setup_connection):
    client, database, constructor, indexes, delay = setup_connection
    application = FastAPI()
    async def scenario():
        async with mongodb.lifespan(application):
            assert application.state.mongodb_client is client
            assert application.state.mongodb_database is database
            client.close.assert_not_awaited()
        client.close.assert_awaited_once()
        assert application.state.mongodb_client is None
        assert application.state.mongodb_database is None
    asyncio.run(scenario())
    constructor.assert_called_once()
    assert constructor.call_args.kwargs["tz_aware"] is True
    indexes.assert_awaited_once()
    delay.assert_not_awaited()


def test_lifespan_retries_then_succeeds(setup_connection):
    client, _, _, indexes, delay = setup_connection
    client.admin.command.side_effect = [ConnectionFailure("private connection details"), None]
    async def scenario():
        async with mongodb.lifespan(FastAPI()):
            pass
    asyncio.run(scenario())
    assert client.admin.command.await_count == 2
    indexes.assert_awaited_once()
    delay.assert_awaited_once_with(mongodb.MONGODB_RETRY_DELAY_SECONDS)


@pytest.mark.parametrize("failure_in", ["ping", "indexes"])
def test_failed_startup_closes_client_without_leaking_details(setup_connection, caplog, failure_in):
    client, _, _, indexes, delay = setup_connection
    target = client.admin.command if failure_in == "ping" else indexes
    target.side_effect = ConnectionFailure("private-password")
    async def scenario():
        with pytest.raises(RuntimeError) as error:
            async with mongodb.lifespan(FastAPI()):
                pytest.fail("startup must fail")
        assert "private-password" not in str(error.value)
    asyncio.run(scenario())
    assert target.await_count == mongodb.MONGODB_MAX_ATTEMPTS
    assert delay.await_count == mongodb.MONGODB_MAX_ATTEMPTS - 1
    client.close.assert_awaited_once()
    assert "private-password" not in caplog.text


def test_lifespan_closes_client_on_application_error(setup_connection):
    client, *_ = setup_connection
    async def scenario():
        with pytest.raises(ValueError, match="application"):
            async with mongodb.lifespan(FastAPI()):
                raise ValueError("application")
    asyncio.run(scenario())
    client.close.assert_awaited_once()
