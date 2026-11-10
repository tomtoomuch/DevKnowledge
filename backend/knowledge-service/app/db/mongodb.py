"""One async MongoDB client per application lifespan, shared by requests."""

import asyncio
import logging
import os
from contextlib import asynccontextmanager
from datetime import UTC
from typing import AsyncIterator

from fastapi import FastAPI
from pymongo import AsyncMongoClient
from pymongo.errors import PyMongoError

from app.repositories.knowledge_repository import MongoKnowledgeRepository
from app.repositories.knowledge_type_repository import MongoKnowledgeTypeRepository
from app.repositories.tag_repository import MongoTagRepository
from app.repositories.technology_repository import MongoTechnologyRepository
from app.repositories.relation_repository import MongoRelationRepository
from app.auth.local import initialize_identity


logger = logging.getLogger(__name__)
MONGODB_MAX_ATTEMPTS = 5
MONGODB_RETRY_DELAY_SECONDS = 2


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    username = os.getenv("MONGODB_USERNAME")
    password = os.getenv("MONGODB_PASSWORD")
    database_name = os.getenv("MONGODB_DATABASE", "devknowledge")
    if not username or not password:
        raise RuntimeError(
            "Configuration MongoDB incomplète : "
            "MONGODB_USERNAME et MONGODB_PASSWORD sont requis."
        )

    client = AsyncMongoClient(
        host=os.getenv("MONGODB_HOST", "localhost"),
        port=int(os.getenv("MONGODB_PORT", "27017")),
        username=username, password=password,
        authSource=os.getenv("MONGODB_AUTH_SOURCE", database_name),
        serverSelectionTimeoutMS=3000, tz_aware=True, tzinfo=UTC,
    )
    app.state.mongodb_client = client
    app.state.mongodb_database = client[database_name]
    try:
        for attempt in range(1, MONGODB_MAX_ATTEMPTS + 1):
            try:
                await client.admin.command("ping")
                await MongoKnowledgeRepository(app.state.mongodb_database).ensure_indexes()
                await MongoKnowledgeTypeRepository(app.state.mongodb_database).ensure_catalog()
                await MongoTagRepository(app.state.mongodb_database).ensure_indexes()
                await MongoTechnologyRepository(app.state.mongodb_database).ensure_indexes()
                await MongoRelationRepository(app.state.mongodb_database).ensure_catalog()
                await initialize_identity(app.state.mongodb_database)
                logger.info("MongoDB connection and indexes ready")
                break
            except PyMongoError as exc:
                # Driver exception strings can contain connection details.
                logger.warning("MongoDB startup failure (%s), attempt %s/%s",
                               type(exc).__name__, attempt, MONGODB_MAX_ATTEMPTS)
                if attempt == MONGODB_MAX_ATTEMPTS:
                    raise RuntimeError("MongoDB reste inaccessible ou ses index ne sont pas prêts.") from None
                await asyncio.sleep(MONGODB_RETRY_DELAY_SECONDS)
        yield
    finally:
        await client.close()
        app.state.mongodb_client = None
        app.state.mongodb_database = None
        logger.info("MongoDB connection closed")
