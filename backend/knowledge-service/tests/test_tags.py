"""Unit tests of the local tag catalog: normalization, auth and no Mongo required."""
from copy import deepcopy
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from pymongo.errors import DuplicateKeyError
from pydantic import ValidationError

from app.api.routes.tags import tag_repository
from app.auth.local import requester_identity
from app.main import app
from app.schemas.tags import TagCreate, TagPage, TagRead
from app.services.knowledge_service import RequesterIdentity


BASE = "/api/v1/tags"


class InMemoryTags:
    def __init__(self):
        self.items = {}

    async def create(self, payload):
        key = payload.name.casefold()
        if key in self.items:
            raise DuplicateKeyError("duplicate")
        item = TagRead(tag_id=uuid4(), name=payload.name)
        self.items[key] = item
        return item

    async def get(self, tag_id):
        return next((t for t in self.items.values() if t.tag_id == tag_id), None)

    async def list(self, *, skip, limit):
        items = sorted(self.items.values(), key=lambda t: t.name.casefold())
        return TagPage(items=items[skip:skip + limit], total=len(items), skip=skip, limit=limit)


@pytest.fixture()
def client():
    catalog = InMemoryTags()
    app.dependency_overrides[tag_repository] = lambda: catalog
    app.dependency_overrides[requester_identity] = lambda: RequesterIdentity(
        permissions=frozenset({"knowledge.create", "knowledge.read"}),
    )
    api = TestClient(app)
    try:
        yield api, catalog
    finally:
        api.close()
        app.dependency_overrides.pop(tag_repository, None)
        app.dependency_overrides.pop(requester_identity, None)


def test_names_are_unicode_normalized_and_reject_blank():
    assert TagCreate(name="  Kubernetes  ").name == "Kubernetes"
    assert TagCreate(name=" Ａngular ").name == "Angular"
    for bad in ["", " \t\n ", "x" * 101]:
        with pytest.raises(ValidationError):
            TagCreate(name=bad)


def test_tag_catalog_create_read_paginate_and_conflict(client):
    api, repo = client
    created = api.post(BASE, json={"name": "  Python  "})
    assert created.status_code == 201
    assert created.json()["name"] == "Python"
    tag_id = created.json()["tag_id"]
    assert api.post(BASE, json={"name": "PYTHON"}).status_code == 409
    assert api.get(f"{BASE}/{tag_id}").json() == created.json()
    assert api.get(f"{BASE}/{uuid4()}").status_code == 404
    second = api.post(BASE, json={"name": "Docker"}).json()
    page = api.get(BASE, params={"skip": 1, "limit": 1}).json()
    assert page == {"items": [created.json()], "total": 2, "skip": 1, "limit": 1}
    assert api.get(BASE, params={"limit": 0}).status_code == 422
    assert api.get(BASE, params={"limit": 101}).status_code == 422
    assert api.post(BASE, json={"name": "A", "tag_id": str(uuid4())}).status_code == 422
    assert len(repo.items) == 2


def test_tag_routes_enforce_read_and_write_permissions(client):
    api, _ = client
    app.dependency_overrides[requester_identity] = lambda: RequesterIdentity(
        permissions=frozenset({"knowledge.read"}),
    )
    assert api.get(BASE).status_code == 200
    assert api.post(BASE, json={"name": "No"}).status_code == 403
    app.dependency_overrides[requester_identity] = lambda: RequesterIdentity(
        permissions=frozenset({"knowledge.create"}),
    )
    assert api.get(BASE).status_code == 403
    assert api.post(BASE, json={"name": "Yes"}).status_code == 201
