"""Real MongoDB persistence and catalog tests: disposable database only."""
import asyncio
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from fastapi import FastAPI
from httpx2 import ASGITransport, AsyncClient

from app.api.routes.knowledge_types import router as type_router
from app.auth.local import requester_identity
from app.repositories.knowledge_repository import MongoKnowledgeRepository
from app.repositories.knowledge_type_repository import MongoKnowledgeTypeRepository
from app.schemas.knowledge import KnowledgeCreate, KnowledgeUpdate
from app.services.knowledge_service import KnowledgeService, RequesterIdentity


pytestmark = pytest.mark.integration


def test_catalog_seed_is_idempotent_and_authorized(isolated_database):
    async def scenario():
        async with isolated_database() as db:
            repo = MongoKnowledgeTypeRepository(db)
            await repo.ensure_catalog()
            await repo.ensure_catalog()
            assert await db.knowledge_types.count_documents({}) == 8
            rows = await repo.list()
            assert len(rows) == 8
            assert len({row.code for row in rows}) == 8
            code = next(row for row in rows if row.code == "CODE_SNIPPET")
            assert code.required_fields == ["code", "programming_language"]

            api = FastAPI()
            api.state.mongodb_database = db
            api.include_router(type_router)
            api.dependency_overrides[requester_identity] = (
                lambda: RequesterIdentity(permissions=frozenset({"knowledge.read"}))
            )
            async with AsyncClient(transport=ASGITransport(app=api), base_url="http://test") as client:
                response = await client.get("/api/v1/knowledge-types")
                assert response.status_code == 200
                assert len(response.json()) == 8
                assert response.json()[0]["code"] == "BEST_PRACTICE"
            api.dependency_overrides[requester_identity] = lambda: RequesterIdentity()
            async with AsyncClient(transport=ASGITransport(app=api), base_url="http://test") as client:
                assert (await client.get("/api/v1/knowledge-types")).status_code == 403
    asyncio.run(scenario())


def test_embedded_specialization_is_atomic_and_legacy_safe(isolated_database):
    async def scenario():
        async with isolated_database() as db:
            repo = MongoKnowledgeRepository(db)
            await repo.ensure_indexes()
            svc = KnowledgeService(repo)
            first = await svc.create(KnowledgeCreate(
                knowledge_type="TERMINAL_COMMAND", title="CLI", content="Vérifier les services",
                details={"command": "docker compose ps", "shell": "bash", "is_destructive": False},
            ), RequesterIdentity())
            raw = await db.knowledge_items.find_one({"_id": str(first.knowledge_id)})
            assert raw["details"]["command"] == "docker compose ps"
            assert raw["knowledge_type"] == "TERMINAL_COMMAND"
            assert first.revision == 1

            edited = await svc.update(first.knowledge_id, KnowledgeUpdate(
                details={"command": "docker compose config", "shell": "bash"},
            ), expected_revision=1)
            assert edited.revision == 2
            assert edited.details == {"command": "docker compose config", "shell": "bash"}
            assert (await repo.get(first.knowledge_id))["details"] == edited.details

            # Switching type is atomic with clearing the old specialized value.
            switched = await svc.update(first.knowledge_id, KnowledgeUpdate(
                knowledge_type="BUG_FIX",
            ), expected_revision=2)
            assert switched.revision == 3 and switched.details is None
            stored = await db.knowledge_items.find_one({"_id": str(first.knowledge_id)})
            assert stored["knowledge_type"] == "BUG_FIX" and stored["details"] is None

            legacy_id = uuid4()
            now = datetime(2026, 11, 9, tzinfo=UTC)
            await db.knowledge_items.insert_one({
                "_id": str(legacy_id), "knowledge_type": "CODE_SNIPPET",
                "title": "Legacy", "content": "print(1)", "status": "DRAFT",
                "description": None, "language_code": None, "difficulty_level": None,
                "is_favorite": False, "created_at": now, "updated_at": now,
                "validated_at": None, "deleted_at": None, "created_by_user_id": None,
            })
            legacy = await svc.get(legacy_id)
            assert legacy.details is None
            assert legacy.revision == 0
            filled = await svc.update(legacy_id, KnowledgeUpdate(details={
                "code": "print(1)", "programming_language": "Python",
            }), expected_revision=0)
            assert filled.revision == 1 and filled.details["programming_language"] == "Python"
            assert (await svc.list(knowledge_type="CODE_SNIPPET")).total == 1
    asyncio.run(scenario())


def test_full_http_crud_cycle_for_all_eight_types_on_disposable_mongodb(isolated_database):
    """POST, GET, PATCH, stale If-Match, DELETE and tombstone for every specialization."""
    from app.api.routes.knowledges import router as knowledge_router
    from app.main import knowledge_not_found, knowledge_conflict
    from app.services.knowledge_service import KnowledgeNotFound, KnowledgeConflict

    details_by_type = {
        "CODE_SNIPPET": {"code": "print(42)", "programming_language": "Python"},
        "TERMINAL_COMMAND": {"command": "git status", "shell": "bash", "is_destructive": False},
        "TECHNICAL_PROCEDURE": {"objective": "Déployer la Gateway", "estimated_duration_minutes": 10},
        "COURSE_NOTE": {"concept": "Troisième forme normale", "mastery_level": 3},
        "BUG_FIX": {"error_title": "Missing index", "root_cause": "Index non initialisé"},
        "DOCUMENTATION_RESOURCE": {"url": "https://example.org/docs", "is_official": False},
        "BEST_PRACTICE": {"principle": "Moindre privilège"},
        "COMPLIANCE_STANDARD": {"reference_code": "ISO/IEC 27001"},
    }

    async def scenario():
        async with isolated_database() as db:
            await MongoKnowledgeRepository(db).ensure_indexes()
            app = FastAPI()
            app.state.mongodb_database = db
            app.include_router(knowledge_router)
            app.add_exception_handler(KnowledgeNotFound, knowledge_not_found)
            app.add_exception_handler(KnowledgeConflict, knowledge_conflict)
            app.dependency_overrides[requester_identity] = lambda: RequesterIdentity(
                permissions=frozenset({
                    "knowledge.read", "knowledge.create", "knowledge.update", "knowledge.delete",
                })
            )
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                for knowledge_type, details in details_by_type.items():
                    created = await client.post("/api/v1/knowledges", json={
                        "knowledge_type": knowledge_type, "title": knowledge_type,
                        "content": "Contenu générique", "details": details,
                    })
                    assert created.status_code == 201, (knowledge_type, created.text)
                    resource = f"/api/v1/knowledges/{created.json()['knowledge_id']}"
                    assert created.json()["details"] == details
                    assert created.headers["etag"] == '"1"'
                    read = await client.get(resource)
                    assert read.status_code == 200 and read.json()["details"] == details
                    assert read.headers["etag"] == '"1"'
                    changed = await client.patch(resource, json={
                        "details": details, "is_favorite": True,
                    }, headers={"If-Match": '"1"'})
                    assert changed.status_code == 200, (knowledge_type, changed.text)
                    assert changed.json()["revision"] == 2
                    assert changed.json()["details"] == details
                    assert changed.json()["is_favorite"] is True
                    stale = await client.patch(resource, json={"title": "Perdu"},
                                               headers={"If-Match": '"1"'})
                    assert stale.status_code == 412
                    removed = await client.delete(resource, headers={"If-Match": '"2"'})
                    assert removed.status_code == 204
                    assert (await client.get(resource)).status_code == 404
            assert await db.knowledge_items.count_documents({}) == 8
            assert await db.knowledge_items.count_documents({"deleted_at": None}) == 0
    asyncio.run(scenario())
