"""Integration tests with a disposable MongoDB: catalog indexes and knowledge links."""
import asyncio
from uuid import uuid4

import pytest
from fastapi import FastAPI
from httpx2 import ASGITransport, AsyncClient

from app.api.routes.knowledges import router as knowledge_router
from app.api.routes.technologies import router as tech_router
from app.auth.local import requester_identity
from app.main import (
    invalid_technology_association, knowledge_conflict, knowledge_not_found,
)
from app.repositories.knowledge_repository import MongoKnowledgeRepository
from app.repositories.technology_repository import (
    MongoTechnologyRepository, DuplicateTechnologyAssociationError,
    UnknownTechnologyError, UnknownTechnologyVersionError,
)
from app.services.knowledge_service import (
    KnowledgeConflict, KnowledgeNotFound, RequesterIdentity,
)

pytestmark = pytest.mark.integration


def test_catalog_and_knowledge_links_real_mongodb(isolated_database):
    async def scenario():
        async with isolated_database() as db:
            catalog = MongoTechnologyRepository(db)
            await catalog.ensure_indexes()
            await catalog.ensure_indexes()
            await MongoKnowledgeRepository(db).ensure_indexes()
            app = FastAPI()
            app.state.mongodb_database = db
            app.include_router(knowledge_router)
            app.include_router(tech_router)
            app.add_exception_handler(UnknownTechnologyError, invalid_technology_association)
            app.add_exception_handler(UnknownTechnologyVersionError, invalid_technology_association)
            app.add_exception_handler(DuplicateTechnologyAssociationError, invalid_technology_association)
            app.add_exception_handler(KnowledgeConflict, knowledge_conflict)
            app.add_exception_handler(KnowledgeNotFound, knowledge_not_found)
            app.dependency_overrides[requester_identity] = lambda: RequesterIdentity(
                permissions=frozenset({
                    "knowledge.read", "knowledge.create", "knowledge.update", "knowledge.delete",
                })
            )
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
                python = await c.post("/api/v1/technologies", json={"name": "  Python  ", "category": "Language"})
                assert python.status_code == 201, python.text
                pyid = python.json()["technology_id"]
                assert (await c.post("/api/v1/technologies", json={"name": "PYTHON"})).status_code == 409
                docker = await c.post("/api/v1/technologies", json={"name": "Docker", "category": "Tool"})
                assert docker.status_code == 201
                did = docker.json()["technology_id"]
                assert (await c.get("/api/v1/technologies")).json()["total"] == 2
                assert (await c.get(f"/api/v1/technologies/{pyid}")).json() == python.json()
                assert (await c.post("/api/v1/technology-versions", json={
                    "technology_id": str(uuid4()), "version": "1",
                })).status_code == 422
                version = await c.post("/api/v1/technology-versions", json={
                    "technology_id": pyid, "version": "3.14", "release_date": "2026-10-01",
                })
                assert version.status_code == 201, version.text
                vid = version.json()["technology_version_id"]
                assert version.json()["release_date"] == "2026-10-01"
                assert (await c.post("/api/v1/technology-versions", json={
                    "technology_id": pyid, "version": "3.14",
                })).status_code == 409
                assert (await c.get("/api/v1/technology-versions", params={
                    "technology_id": pyid,
                })).json()["total"] == 1

                base = {"knowledge_type": "CODE_SNIPPET", "title": "Snippet", "content": "print(1)"}
                for patch in [
                    {"technology_ids": [str(uuid4())]},
                    {"technology_version_ids": [str(uuid4())]},
                    {"technology_ids": [pyid], "technology_version_ids": [vid]},
                ]:
                    invalid = await c.post("/api/v1/knowledges", json={**base, **patch})
                    assert invalid.status_code == 422, invalid.text
                assert await db.knowledge_items.count_documents({}) == 0

                created = await c.post("/api/v1/knowledges", json={
                    **base, "technology_ids": [did], "technology_version_ids": [vid],
                })
                assert created.status_code == 201, created.text
                ident = created.json()["knowledge_id"]
                path = f"/api/v1/knowledges/{ident}"
                assert created.json()["technology_ids"] == [did]
                assert created.json()["technology_version_ids"] == [vid]
                stored = await db.knowledge_items.find_one({"_id": ident})
                assert stored["technology_ids"] == [did]
                assert stored["technology_version_ids"] == [vid]
                assert (await c.get("/api/v1/knowledges", params={"technology_id": did})).json()["total"] == 1
                assert (await c.get("/api/v1/knowledges", params={"technology_id": pyid})).json()["total"] == 0
                assert (await c.get("/api/v1/knowledges", params={"technology_version_id": vid})).json()["total"] == 1
                invalid = await c.patch(path, headers={"If-Match": '"1"'},
                                        json={"technology_ids": [did, pyid]})
                assert invalid.status_code == 422
                assert (await c.get(path)).headers["etag"] == '"1"'
                invalid = await c.patch(path, headers={"If-Match": '"1"'},
                                        json={"technology_version_ids": [str(uuid4())]})
                assert invalid.status_code == 422
                updated = await c.patch(path, headers={"If-Match": '"1"'},
                                        json={"technology_ids": [did, pyid], "technology_version_ids": []})
                assert updated.status_code == 200, updated.text
                assert updated.json()["revision"] == 2
                assert (await c.patch(path, headers={"If-Match": '"1"'},
                                      json={"technology_ids": []})).status_code == 412
                assert (await c.patch(path, headers={"If-Match": '"2"'},
                                      json={"technology_version_ids": [vid]})).status_code == 422
                cleared = await c.patch(path, headers={"If-Match": '"2"'},
                                        json={"technology_ids": [], "technology_version_ids": []})
                assert cleared.status_code == 200 and cleared.json()["revision"] == 3
                assert (await c.get("/api/v1/knowledges", params={"technology_id": did})).json()["total"] == 0

                # Legacy documents with no new fields must deserialize to empty lists.
                await db.knowledge_items.update_one({"_id": ident}, {"$unset": {
                    "technology_ids": "", "technology_version_ids": "",
                }})
                legacy = await c.get(path)
                assert legacy.status_code == 200
                assert legacy.json()["technology_ids"] == []
                assert legacy.json()["technology_version_ids"] == []
                assert (await c.delete(path, headers={"If-Match": '"3"'})).status_code == 204
                assert (await c.get(path)).status_code == 404
    asyncio.run(scenario())
