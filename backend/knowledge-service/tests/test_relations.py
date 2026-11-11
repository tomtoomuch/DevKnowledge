"""HTTP contract, permissions and validation for knowledge graph links."""
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from pymongo.errors import DuplicateKeyError

from app.api.routes.relations import relation_repository
from app.auth.local import requester_identity
from app.main import app
from app.repositories.relation_repository import (
    RelationConflict, RelationNotFound, RelationReferenceError,
)
from app.schemas.relations import RelationCreate, RelationRead, RelationTypeRead
from app.services.knowledge_service import RequesterIdentity


BASE = "/api/v1/knowledge-relations"
TYPE_ID = uuid4()
K1 = uuid4()
K2 = uuid4()


class MemoryRelations:
    def __init__(self):
        self.items = {}
        self.kind = RelationTypeRead(relation_type_id=TYPE_ID, code="RELATED_TO",
                                     label="Lié", is_directed=False)

    async def list_types(self):
        return [self.kind]

    async def create(self, payload):
        if payload.relation_type_id != TYPE_ID:
            raise RelationReferenceError
        key = (frozenset((payload.origin_knowledge_id, payload.target_knowledge_id)),
               payload.relation_type_id)
        if any((frozenset((record.origin_knowledge_id, record.target_knowledge_id)),
                record.relation_type_id) == key for record in self.items.values()):
            raise DuplicateKeyError("duplicate")
        now = datetime.now(UTC)
        item = RelationRead(**payload.model_dump(), relation_id=uuid4(), revision=1,
                            created_at=now, updated_at=now)
        self.items[item.relation_id] = item
        return item

    async def get(self, relation_id):
        return self.items.get(relation_id)

    async def list(self, *, knowledge_id, skip, limit):
        from app.schemas.relations import RelationPage
        items = [r for r in self.items.values()
                 if knowledge_id in (r.origin_knowledge_id, r.target_knowledge_id)]
        return RelationPage(items=items[skip:skip+limit], total=len(items), skip=skip, limit=limit)

    async def update(self, relation_id, payload, revision):
        item = self.items.get(relation_id)
        if item is None:
            raise RelationNotFound
        if item.revision != revision:
            raise RelationConflict
        updated = item.model_copy(update={
            "relation_notes": payload.relation_notes, "revision": revision+1,
        })
        self.items[relation_id] = updated
        return updated

    async def delete(self, relation_id, revision):
        item = self.items.get(relation_id)
        if item is None:
            raise RelationNotFound
        if item.revision != revision:
            raise RelationConflict
        del self.items[relation_id]


@pytest.fixture()
def api():
    fake = MemoryRelations()
    app.dependency_overrides[relation_repository] = lambda: fake
    app.dependency_overrides[requester_identity] = lambda: RequesterIdentity(
        permissions=frozenset({"knowledge.read", "knowledge.create",
                               "knowledge.update", "knowledge.delete"}),
    )
    client = TestClient(app)  # No lifespan; Mongo remains unconnected.
    try:
        yield client
    finally:
        client.close()
        app.dependency_overrides.pop(relation_repository, None)
        app.dependency_overrides.pop(requester_identity, None)


def post(client, **kwargs):
    return client.post(BASE, json={
        "origin_knowledge_id": str(K1),
        "target_knowledge_id": str(K2),
        "relation_type_id": str(TYPE_ID),
        **kwargs,
    })


def test_relation_catalog_create_read_filter_and_duplicate(api):
    response = post(api, relation_notes="Voir le document")
    assert response.status_code == 201, response.text
    first = response.json()
    rid = first["relation_id"]
    assert response.headers["etag"] == '"1"'
    assert api.get("/api/v1/relation-types").json()[0]["code"] == "RELATED_TO"
    assert api.get(BASE, params={"knowledge_id": str(K1)}).json()["total"] == 1
    assert api.get(BASE, params={"knowledge_id": str(K2)}).json()["total"] == 1
    assert api.get(BASE, params={"knowledge_id": str(uuid4())}).json()["total"] == 0
    assert api.get(f"{BASE}/{rid}").headers["etag"] == '"1"'
    assert post(api, origin_knowledge_id=str(K2), target_knowledge_id=str(K1)).status_code == 409
    assert api.get(f"{BASE}/{uuid4()}").status_code == 404


def test_schema_rejects_self_links_unknown_fields_and_unbounded_notes(api):
    assert post(api, target_knowledge_id=str(K1)).status_code == 422
    assert post(api, relation_notes="x"*4001).status_code == 422
    assert post(api, relation_type_id="not-uuid").status_code == 422
    assert post(api, relation_id=str(uuid4())).status_code == 422
    assert api.get(BASE).status_code == 422  # knowledge_id required
    assert api.get(BASE, params={"knowledge_id": "abc"}).status_code == 422
    assert api.get(BASE, params={"knowledge_id": str(K1), "limit": 0}).status_code == 422
    assert post(api, relation_type_id=str(uuid4())).status_code == 422


def test_relation_notes_patch_etag_and_delete(api):
    created = post(api).json()
    ident = created["relation_id"]
    path = f"{BASE}/{ident}"
    assert api.patch(path, json={"relation_notes": "update"}).status_code == 428
    assert api.patch(path, headers={"If-Match": '"1"'}, json={}).status_code == 422
    assert api.patch(path, headers={"If-Match": '"1"'}, json={"relation_type_id": str(TYPE_ID)}).status_code == 422
    updated = api.patch(path, headers={"If-Match": '"1"'}, json={"relation_notes": "updated"})
    assert updated.status_code == 200, updated.text
    assert updated.headers["etag"] == '"2"'
    assert updated.json()["revision"] == 2
    assert updated.json()["relation_notes"] == "updated"
    assert api.patch(path, headers={"If-Match": '"1"'}, json={"relation_notes": None}).status_code == 412
    assert api.delete(path, headers={"If-Match": '"1"'}).status_code == 412
    assert api.delete(path).status_code == 428
    clear = api.patch(path, headers={"If-Match": '"2"'}, json={"relation_notes": None})
    assert clear.status_code == 200
    assert clear.json()["relation_notes"] is None
    assert api.delete(path, headers={"If-Match": '"3"'}).status_code == 204
    assert api.get(path).status_code == 404
    assert api.delete(path, headers={"If-Match": '"3"'}).status_code == 404


def test_relation_rbac(api):
    app.dependency_overrides[requester_identity] = lambda: RequesterIdentity(
        permissions=frozenset({"knowledge.read"}),
    )
    assert api.get("/api/v1/relation-types").status_code == 200
    assert post(api).status_code == 403
    app.dependency_overrides[requester_identity] = lambda: RequesterIdentity(
        permissions=frozenset({"knowledge.create"}),
    )
    assert api.get("/api/v1/relation-types").status_code == 403
    assert api.get(BASE, params={"knowledge_id": str(K1)}).status_code == 403
    assert post(api).status_code == 201
