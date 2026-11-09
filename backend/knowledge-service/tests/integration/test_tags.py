"""Real MongoDB tests: reference integrity and atomic tag association (disposable only)."""
import asyncio
from uuid import uuid4

import pytest
from fastapi import FastAPI
from httpx2 import ASGITransport, AsyncClient

from app.api.routes.knowledges import router as knowledge_router
from app.api.routes.tags import router as tags_router
from app.auth.local import requester_identity
from app.main import knowledge_conflict, knowledge_not_found, unknown_tag
from app.repositories.knowledge_repository import MongoKnowledgeRepository
from app.repositories.tag_repository import MongoTagRepository, UnknownTagError
from app.services.knowledge_service import KnowledgeConflict, KnowledgeNotFound, RequesterIdentity


pytestmark = pytest.mark.integration


def test_catalog_unique_index_and_tagged_knowledge_crud(isolated_database):
    async def scenario():
        async with isolated_database() as database:
            catalog = MongoTagRepository(database)
            await catalog.ensure_indexes()
            await catalog.ensure_indexes()
            await MongoKnowledgeRepository(database).ensure_indexes()
            app = FastAPI()
            app.state.mongodb_database = database
            app.include_router(knowledge_router)
            app.include_router(tags_router)
            app.add_exception_handler(UnknownTagError, unknown_tag)
            app.add_exception_handler(KnowledgeConflict, knowledge_conflict)
            app.add_exception_handler(KnowledgeNotFound, knowledge_not_found)
            app.dependency_overrides[requester_identity] = lambda: RequesterIdentity(
                permissions=frozenset({
                    "knowledge.read", "knowledge.create",
                    "knowledge.update", "knowledge.delete",
                })
            )
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                first = await client.post("/api/v1/tags", json={"name": "  Python "})
                assert first.status_code == 201, first.text
                tag_id = first.json()["tag_id"]
                assert (await client.post("/api/v1/tags", json={"name": "pYtHoN"})).status_code == 409
                assert (await client.get(f"/api/v1/tags/{tag_id}")).json() == first.json()
                assert (await client.get("/api/v1/tags")).json()["total"] == 1
                second = await client.post("/api/v1/tags", json={"name": "Docker"})
                second_id = second.json()["tag_id"]
                assert second.status_code == 201

                invalid = await client.post("/api/v1/knowledges", json={
                    "title": "No tag", "knowledge_type": "CODE_SNIPPET",
                    "content": "print(1)", "tag_ids": [str(uuid4())],
                })
                assert invalid.status_code == 422
                assert await database.knowledge_items.count_documents({}) == 0

                created = await client.post("/api/v1/knowledges", json={
                    "title": "Snippet", "knowledge_type": "CODE_SNIPPET",
                    "content": "print(1)", "tag_ids": [tag_id],
                })
                assert created.status_code == 201, created.text
                knowledge_id = created.json()["knowledge_id"]
                endpoint = f"/api/v1/knowledges/{knowledge_id}"
                stored = await database.knowledge_items.find_one({"_id": knowledge_id})
                assert stored["tag_ids"] == [tag_id]
                assert created.json()["tag_ids"] == [tag_id]
                filtered = await client.get("/api/v1/knowledges", params={"tag_id": tag_id})
                assert filtered.json()["total"] == 1
                missing = await client.get("/api/v1/knowledges", params={"tag_id": second_id})
                assert missing.json()["total"] == 0

                unknown = await client.patch(endpoint, headers={"If-Match": '"1"'},
                                             json={"tag_ids": [str(uuid4())]})
                assert unknown.status_code == 422
                assert (await client.get(endpoint)).headers["etag"] == '"1"'
                updated = await client.patch(endpoint, headers={"If-Match": '"1"'},
                                             json={"tag_ids": [tag_id, second_id]})
                assert updated.status_code == 200
                assert updated.json()["revision"] == 2
                assert updated.json()["tag_ids"] == [tag_id, second_id]
                stale = await client.patch(endpoint, headers={"If-Match": '"1"'},
                                           json={"tag_ids": []})
                assert stale.status_code == 412
                cleared = await client.patch(endpoint, headers={"If-Match": '"2"'},
                                             json={"tag_ids": []})
                assert cleared.status_code == 200 and cleared.json()["tag_ids"] == []
                assert (await client.get("/api/v1/knowledges", params={"tag_id": tag_id})).json()["total"] == 0
                assert (await client.delete(endpoint, headers={"If-Match": '"3"'})).status_code == 204
                assert (await client.get(endpoint)).status_code == 404
    asyncio.run(scenario())
