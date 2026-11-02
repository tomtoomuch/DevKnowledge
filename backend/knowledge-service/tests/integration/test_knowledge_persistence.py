import asyncio
from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from fastapi import FastAPI
from httpx2 import ASGITransport, AsyncClient
from pymongo.errors import PyMongoError

from app.api.routes.knowledges import router
from app.main import knowledge_not_found, mongodb_unavailable
from app.repositories.knowledge_repository import MongoKnowledgeRepository
from app.services.knowledge_service import KnowledgeNotFound


pytestmark = pytest.mark.integration


def make_item(identifier: int, *, knowledge_type="CODE_SNIPPET", status="DRAFT", timestamp=None):
    timestamp = timestamp or datetime(2026, 11, 2, 12, 0, 0, 123000, tzinfo=UTC)
    return {
        "knowledge_id": UUID(int=identifier),
        "knowledge_type": knowledge_type,
        "title": f"Knowledge {identifier}",
        "description": None,
        "content": "print('hello')",
        "language_code": "python",
        "difficulty_level": None,
        "status": status,
        "created_at": timestamp,
        "updated_at": timestamp,
        "validated_at": None,
        "created_by_user_id": None,
        "is_favorite": False,
        "deleted_at": None,
    }


def test_crud_and_serialization_on_real_isolated_mongodb(isolated_database):
    async def scenario():
        async with isolated_database() as database:
            repository = MongoKnowledgeRepository(database)
            await repository.ensure_indexes()
            await repository.ensure_indexes()
            indexes = await repository.collection.index_information()
            assert set(indexes) == {"_id_", "active_chronological"}
            assert indexes["active_chronological"]["key"] == [("deleted_at", 1), ("created_at", -1), ("_id", 1)]
            assert await repository.list(skip=0, limit=10) == ([], 0)

            original = make_item(1)
            assert await repository.create(original) == original
            raw = await database.knowledge_items.find_one({"_id": str(original["knowledge_id"])})
            assert raw["_id"] == str(original["knowledge_id"])
            assert "knowledge_id" not in raw
            assert raw["created_at"].utcoffset() == timedelta(0)
            assert raw["created_at"] == original["created_at"]
            assert await repository.get(original["knowledge_id"]) == original

            updated_at = original["updated_at"] + timedelta(seconds=1)
            changed = await repository.update(original["knowledge_id"], {"title": "Changed", "updated_at": updated_at})
            assert changed["title"] == "Changed"
            assert changed["content"] == original["content"]
            assert changed["updated_at"] == updated_at
            assert await repository.soft_delete(original["knowledge_id"], updated_at)
            assert await repository.get(original["knowledge_id"]) is None
            assert await repository.update(original["knowledge_id"], {"title": "Hidden"}) is None
            assert await repository.list(skip=0, limit=10) == ([], 0)
            assert not await repository.soft_delete(original["knowledge_id"], updated_at)
            stored = await repository.collection.find_one({"_id": str(original["knowledge_id"])})
            assert stored["deleted_at"] == updated_at
            assert await repository.collection.count_documents({}) == 1
            assert await repository.get(UUID(int=999)) is None

    asyncio.run(scenario())


def test_filters_and_stable_pagination_on_real_isolated_mongodb(isolated_database):
    async def scenario():
        async with isolated_database() as database:
            repository = MongoKnowledgeRepository(database)
            await repository.ensure_indexes()
            # Equal timestamps intentionally exercise the identifier tie breaker.
            for item in (make_item(3), make_item(1), make_item(2, knowledge_type="BUG_FIX", status="VALIDATED")):
                await repository.create(item)
            page, total = await repository.list(skip=1, limit=1)
            assert total == 3
            assert [item["knowledge_id"] for item in page] == [UUID(int=2)]
            page, total = await repository.list(skip=0, limit=10, knowledge_type="CODE_SNIPPET")
            assert total == 2
            assert [item["knowledge_id"] for item in page] == [UUID(int=1), UUID(int=3)]
            page, total = await repository.list(skip=0, limit=10, status="VALIDATED")
            assert total == 1 and page[0]["knowledge_type"] == "BUG_FIX"
            assert await repository.list(skip=0, limit=10, knowledge_type="CODE_SNIPPET", status="VALIDATED") == ([], 0)

    asyncio.run(scenario())


def test_http_crud_roundtrip_on_real_isolated_mongodb(isolated_database):
    async def scenario():
        async with isolated_database() as database:
            repository = MongoKnowledgeRepository(database)
            await repository.ensure_indexes()
            # Use the real router, dependencies and exception handlers without
            # the production lifespan, which would connect to the development DB.
            api = FastAPI()
            api.state.mongodb_database = database
            api.include_router(router)
            api.add_exception_handler(KnowledgeNotFound, knowledge_not_found)
            api.add_exception_handler(PyMongoError, mongodb_unavailable)
            async with AsyncClient(transport=ASGITransport(app=api), base_url="http://test") as client:
                prefix = "/api/v1/knowledges"
                assert (await client.get(prefix)).json() == {"items": [], "total": 0, "skip": 0, "limit": 20}

                payload = {
                    "knowledge_type": "CODE_SNIPPET", "title": "Échantillon",
                    "content": "print('é')\n", "description": "To clear",
                }
                created_response = await client.post(prefix, json=payload)
                assert created_response.status_code == 201
                created = created_response.json()
                knowledge_id = created["knowledge_id"]
                assert UUID(knowledge_id).version == 4
                assert created["status"] == "DRAFT"
                assert created["created_by_user_id"] is None
                assert datetime.fromisoformat(created["created_at"]).utcoffset() == timedelta(0)

                stored = await repository.collection.find_one({"_id": knowledge_id})
                assert isinstance(stored["_id"], str)
                assert "knowledge_id" not in stored
                assert stored["created_at"] == datetime.fromisoformat(created["created_at"])
                assert stored["updated_at"] == datetime.fromisoformat(created["updated_at"])
                assert stored["content"] == payload["content"]
                read_response = await client.get(f"{prefix}/{knowledge_id}")
                assert read_response.status_code == 200
                assert read_response.json() == created

                patched_response = await client.patch(f"{prefix}/{knowledge_id}", json={"description": None, "is_favorite": True})
                assert patched_response.status_code == 200
                patched = patched_response.json()
                assert patched["description"] is None and patched["is_favorite"] is True
                assert patched["content"] == payload["content"]
                assert patched["title"] == payload["title"]
                assert patched["created_at"] == created["created_at"]
                assert patched["updated_at"] >= created["updated_at"]
                assert (await client.get(f"{prefix}/{knowledge_id}")).json() == patched
                matching = await client.get(prefix, params={"skip": 0, "limit": 1, "knowledge_type": "CODE_SNIPPET", "status": "DRAFT"})
                assert matching.status_code == 200
                assert matching.json() == {"items": [patched], "total": 1, "skip": 0, "limit": 1}
                assert (await client.get(prefix, params={"status": "VALIDATED"})).json()["total"] == 0

                delete_response = await client.delete(f"{prefix}/{knowledge_id}")
                assert delete_response.status_code == 204
                assert delete_response.content == b""
                assert (await client.get(f"{prefix}/{knowledge_id}")).status_code == 404
                assert (await client.patch(f"{prefix}/{knowledge_id}", json={"title": "Hidden"})).status_code == 404
                assert (await client.delete(f"{prefix}/{knowledge_id}")).status_code == 404
                assert (await client.get(prefix)).json()["items"] == []
                stored = await repository.collection.find_one({"_id": knowledge_id})
                assert stored is not None
                assert stored["deleted_at"] is not None
                assert stored["deleted_at"].utcoffset() == timedelta(0)
                assert stored["updated_at"] == stored["deleted_at"]
                assert await repository.collection.count_documents({}) == 1

    asyncio.run(scenario())
