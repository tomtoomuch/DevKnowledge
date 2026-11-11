"""Real MongoDB verification of directed and undirected knowledge graph edges."""
import asyncio
from uuid import uuid4

import pytest
from fastapi import FastAPI
from httpx2 import ASGITransport, AsyncClient

from app.api.routes.knowledges import router as knowledge_router
from app.api.routes.relations import router as relations_router
from app.auth.local import requester_identity
from app.main import relation_not_found, relation_conflict, relation_reference_error
from app.repositories.relation_repository import (
    MongoRelationRepository, RelationNotFound, RelationConflict, RelationReferenceError,
)
from app.services.knowledge_service import RequesterIdentity


pytestmark = pytest.mark.integration


def test_relation_types_and_edges_with_disposable_mongodb(isolated_database):
    async def scenario():
        async with isolated_database() as db:
            repo = MongoRelationRepository(db)
            await repo.ensure_catalog()
            await repo.ensure_catalog()
            assert await db.relation_types.count_documents({}) == 5
            app = FastAPI()
            app.state.mongodb_database = db
            app.include_router(knowledge_router)
            app.include_router(relations_router)
            app.add_exception_handler(RelationNotFound, relation_not_found)
            app.add_exception_handler(RelationConflict, relation_conflict)
            app.add_exception_handler(RelationReferenceError, relation_reference_error)
            app.dependency_overrides[requester_identity] = lambda: RequesterIdentity(
                permissions=frozenset({"knowledge.read", "knowledge.create",
                                       "knowledge.update", "knowledge.delete"}),
            )
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
                types = (await c.get("/api/v1/relation-types")).json()
                kinds = {t["code"]: t for t in types}
                assert kinds["DEPENDS_ON"]["is_directed"] is True
                assert kinds["RELATED_TO"]["is_directed"] is False
                knowledge = {"title": "Test", "content": "Knowledge body",
                             "knowledge_type": "COURSE_NOTE"}
                x = (await c.post("/api/v1/knowledges", json={**knowledge, "title": "Source"})).json()
                y = (await c.post("/api/v1/knowledges", json={**knowledge, "title": "Target"})).json()
                a, b = x["knowledge_id"], y["knowledge_id"]
                uri = "/api/v1/knowledge-relations"
                payload = {
                    "origin_knowledge_id": a, "target_knowledge_id": b,
                    "relation_type_id": kinds["RELATED_TO"]["relation_type_id"],
                    "relation_notes": "Associées",
                }
                assert (await c.post(uri, json={**payload, "target_knowledge_id": a})).status_code == 422
                assert (await c.post(uri, json={**payload, "target_knowledge_id": str(uuid4())})).status_code == 422
                assert (await c.post(uri, json={
                    **payload, "relation_type_id": str(uuid4()),
                })).status_code == 422
                rel = await c.post(uri, json=payload)
                assert rel.status_code == 201, rel.text
                rid = rel.json()["relation_id"]
                assert rel.headers["etag"] == '"1"'
                # The undirected canonical pair cannot be duplicated in reverse.
                reverse = await c.post(uri, json={**payload,
                    "origin_knowledge_id": b, "target_knowledge_id": a})
                assert reverse.status_code == 409
                listed = await c.get(uri, params={"knowledge_id": b})
                assert listed.status_code == 200 and listed.json()["total"] == 1
                assert (await c.get(uri, params={"knowledge_id": a})).json()["total"] == 1
                assert (await c.get(f"{uri}/{rid}")).headers["etag"] == '"1"'
                # A directed edge and its reverse are two different relations.
                directed = kinds["DEPENDS_ON"]["relation_type_id"]
                d1 = await c.post(uri, json={**payload, "relation_type_id": directed})
                d2 = await c.post(uri, json={**payload, "relation_type_id": directed,
                    "origin_knowledge_id": b, "target_knowledge_id": a})
                assert d1.status_code == 201 and d2.status_code == 201
                assert (await c.get(uri, params={"knowledge_id": b})).json()["total"] == 3
                stale = await c.patch(f"{uri}/{rid}", headers={"If-Match": '"0"'},
                                      json={"relation_notes": "stale"})
                assert stale.status_code == 412
                updated = await c.patch(f"{uri}/{rid}", headers={"If-Match": '"1"'},
                                        json={"relation_notes": "mise à jour"})
                assert updated.status_code == 200 and updated.headers["etag"] == '"2"'
                assert (await c.delete(f"{uri}/{rid}", headers={"If-Match": '"1"'})).status_code == 412
                assert (await c.delete(f"{uri}/{rid}", headers={"If-Match": '"2"'})).status_code == 204
                assert (await c.get(f"{uri}/{rid}")).status_code == 404
                assert (await c.get(uri, params={"knowledge_id": a})).json()["total"] == 2
                # Soft deletion does not cascade or physically destroy existing relations.
                assert (await c.delete(f"/api/v1/knowledges/{a}",
                                       headers={"If-Match": '"1"'})).status_code == 204
                assert (await c.get(uri, params={"knowledge_id": a})).status_code == 404
                assert (await c.post(uri, json=payload)).status_code == 422
                assert await db.knowledge_relations.count_documents({}) == 2
    asyncio.run(scenario())
