"""Real PostgreSQL + controlled fake MongoDB references, with KMS RBAC checks."""
import uuid

from fastapi import FastAPI
from fastapi.testclient import TestClient
from app.auth.local import requester_identity
from app.rncp.router import get_rncp_repository, router
from app.rncp.repository import RncpRepository
from app.services.knowledge_service import RequesterIdentity

from test_rncp import DSN, COMP1, COMP2, ACTOR, KNOWLEDGE

NEW_KNOWLEDGE = uuid.UUID("70000000-0000-0000-0000-000000000002")
ABSENT_KNOWLEDGE = uuid.UUID("70000000-0000-0000-0000-000000000003")


class FakeKnowledgeDB:
    """Only the MongoDB reference check is stubbed; PostgreSQL is real."""
    def __init__(self, active=True):
        self.active = active
        self.calls = []

    def __getitem__(self, collection):
        assert collection == "knowledge_items"
        return self

    async def find_one(self, query, projection=None):
        self.calls.append(query)
        if self.active and query.get("_id") in (str(NEW_KNOWLEDGE), str(KNOWLEDGE)) and query.get("deleted_at") is None:
            return {"_id": query["_id"]}
        return None


def app_for(permissions=("knowledge.read", "knowledge.create"), *, actor=ACTOR, active=True):
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[requester_identity] = (
        lambda: RequesterIdentity(user_id=actor, permissions=frozenset(permissions))
    )
    app.dependency_overrides[get_rncp_repository] = lambda: RncpRepository(DSN)
    app.state.mongodb_database = FakeKnowledgeDB(active=active)
    return app


def test_rncp_reader_permissions_are_enforced(database):
    with TestClient(app_for(("knowledge.read",))) as client:
        assert client.get("/api/v1/rncp/frameworks/RNCP-TEST/versions/v1").status_code == 200
        assert client.get(f"/api/v1/rncp/competencies/{COMP1}/evidence").status_code == 200
        assert client.post(f"/api/v1/rncp/competencies/{COMP2}/evidence", json={
            "title": "Reader is not an author", "evidence_type_code": "SOURCE_CODE",
        }).status_code == 403
        assert client.post(f"/api/v1/rncp/competencies/{COMP2}/knowledge-links", json={
            "knowledge_id": str(NEW_KNOWLEDGE),
        }).status_code == 403
        assert client.get("/api/v1/rncp/frameworks/UNKNOWN/versions/v1").status_code == 404


def test_rncp_requires_user_id_for_writes(database):
    with TestClient(app_for(actor=None)) as client:
        response = client.post(f"/api/v1/rncp/competencies/{COMP2}/evidence", json={
            "title": "Unknown author", "evidence_type_code": "SOURCE_CODE",
        })
        assert response.status_code == 401


def test_evidence_is_written_atomically_and_read_back(database):
    with TestClient(app_for()) as client:
        response = client.post(f"/api/v1/rncp/competencies/{COMP2}/evidence", json={
            "title": "New fictional evidence", "evidence_type_code": "UNIT_TEST",
        })
        assert response.status_code == 201, response.text
        evidence_id = response.json()["id"]
        assert response.json()["verification_status"] == "PENDING"
        response = client.get(f"/api/v1/rncp/competencies/{COMP2}/evidence")
        assert response.status_code == 200
        assert any(item["id"] == evidence_id for item in response.json()["evidence"])
        bad = client.post(f"/api/v1/rncp/competencies/{COMP2}/evidence", json={
            "title": "Invalid evidence", "evidence_type_code": "UNKNOWN_TYPE",
        })
        assert bad.status_code == 422
        absent = client.post(f"/api/v1/rncp/competencies/{uuid.uuid4()}/evidence", json={
            "title": "Nonexistent competency", "evidence_type_code": "UNIT_TEST",
        })
        assert absent.status_code == 404


def test_mongo_reference_and_unique_link_controls(database):
    app = app_for()
    with TestClient(app) as client:
        url = f"/api/v1/rncp/competencies/{COMP2}/knowledge-links"
        payload = {
            "knowledge_id": str(NEW_KNOWLEDGE),
            "confidence_score": 0.75,
            "mapping_rationale": "Fictional mapping",
        }
        first = client.post(url, json=payload)
        assert first.status_code == 201, first.text
        assert first.json()["knowledge_id"] == str(NEW_KNOWLEDGE)
        assert client.post(url, json=payload).status_code == 409
        assert client.post(url, json={**payload, "knowledge_id": str(ABSENT_KNOWLEDGE)}).status_code == 422
        assert client.post(url, json={**payload, "confidence_score": 1.5}).status_code == 422
        assert client.post(f"/api/v1/rncp/competencies/{uuid.uuid4()}/knowledge-links",
                           json={**payload, "knowledge_id": str(KNOWLEDGE)}).status_code == 404
        assert app.state.mongodb_database.calls[0]["deleted_at"] is None

    # An inactive/soft-deleted MongoDB knowledge must never create a SQL link.
    with TestClient(app_for(active=False)) as client:
        assert client.post(url, json={**payload, "knowledge_id": str(KNOWLEDGE)}).status_code == 422


def test_rncp_default_without_permission_fails_closed(database):
    with TestClient(app_for(())) as client:
        assert client.get("/api/v1/rncp/frameworks/RNCP-TEST/versions/v1").status_code == 403
        assert client.post(f"/api/v1/rncp/competencies/{COMP2}/evidence", json={
            "title": "Denied", "evidence_type_code": "UNIT_TEST",
        }).status_code == 403
