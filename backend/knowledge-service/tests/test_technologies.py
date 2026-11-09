"""FastAPI contracts for an immutable technology catalog (no Mongo required)."""
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from pymongo.errors import DuplicateKeyError

from app.api.routes.technologies import technology_repository
from app.auth.local import requester_identity
from app.main import app
from app.repositories.technology_repository import UnknownTechnologyError
from app.schemas.technologies import (
    TechnologyCreate, TechnologyPage, TechnologyRead,
    TechnologyVersionCreate, TechnologyVersionPage, TechnologyVersionRead,
)
from app.services.knowledge_service import RequesterIdentity


class MemoryCatalog:
    def __init__(self):
        self.technologies = {}
        self.versions = {}

    async def create_technology(self, payload):
        if payload.name.casefold() in (t.name.casefold() for t in self.technologies.values()):
            raise DuplicateKeyError('duplicate')
        record = TechnologyRead(technology_id=uuid4(), **payload.model_dump())
        self.technologies[record.technology_id] = record
        return record

    async def get_technology(self, tech_id):
        return self.technologies.get(tech_id)

    async def list_technologies(self, *, skip, limit):
        records = sorted(self.technologies.values(), key=lambda t: t.name.casefold())
        return TechnologyPage(items=records[skip:skip+limit], total=len(records), skip=skip, limit=limit)

    async def create_version(self, payload):
        if payload.technology_id not in self.technologies:
            raise UnknownTechnologyError
        if any(v.technology_id == payload.technology_id and
               v.version.casefold() == payload.version.casefold() for v in self.versions.values()):
            raise DuplicateKeyError('duplicate')
        record = TechnologyVersionRead(technology_version_id=uuid4(), **payload.model_dump())
        self.versions[record.technology_version_id] = record
        return record

    async def get_version(self, version_id):
        return self.versions.get(version_id)

    async def list_versions(self, *, skip, limit, technology_id=None):
        records = sorted(
            (v for v in self.versions.values() if technology_id is None or v.technology_id == technology_id),
            key=lambda v: (str(v.technology_id), v.version.casefold()),
        )
        return TechnologyVersionPage(items=records[skip:skip+limit], total=len(records), skip=skip, limit=limit)


@pytest.fixture()
def api():
    catalog = MemoryCatalog()
    app.dependency_overrides[technology_repository] = lambda: catalog
    app.dependency_overrides[requester_identity] = lambda: RequesterIdentity(
        permissions=frozenset({"knowledge.read", "knowledge.create"}),
    )
    # Deliberately do not enter TestClient lifespan: it requires real MongoDB.
    client = TestClient(app)
    try:
        yield client
    finally:
        client.close()
        app.dependency_overrides.pop(technology_repository, None)
        app.dependency_overrides.pop(requester_identity, None)


def test_normalization_date_and_validation():
    assert TechnologyCreate(name="  Python  ", category=" Language ").model_dump() == {
        "name": "Python", "category": "Language",
    }
    assert TechnologyCreate(name="  \uff21ngular  ").name == "Angular"
    assert TechnologyVersionCreate(technology_id=uuid4(), version="  3.14  ").version == "3.14"
    for name in (" ", "", "A" * 101):
        with pytest.raises(ValidationError):
            TechnologyCreate(name=name)
    with pytest.raises(ValidationError):
        TechnologyVersionCreate(technology_id=uuid4(), version=" ")
    with pytest.raises(ValidationError):
        TechnologyVersionCreate(technology_id=uuid4(), version="3.14", release_date="2026-02-30")


def test_catalog_routes_and_duplicates(api):
    first = api.post("/api/v1/technologies", json={"name": " Python ", "category": "Language"})
    assert first.status_code == 201, first.text
    tid = first.json()["technology_id"]
    assert api.post("/api/v1/technologies", json={"name": "PYTHON"}).status_code == 409
    assert api.get(f"/api/v1/technologies/{tid}").json() == first.json()
    assert api.get(f"/api/v1/technologies/{uuid4()}").status_code == 404
    assert api.get("/api/v1/technologies").json()["total"] == 1
    assert api.get("/api/v1/technologies", params={"limit": 101}).status_code == 422
    assert api.post("/api/v1/technologies", json={"name": "Bad", "unexpected": 1}).status_code == 422
    orphan = api.post("/api/v1/technology-versions", json={"technology_id": str(uuid4()), "version": "1.0"})
    assert orphan.status_code == 422
    version = api.post("/api/v1/technology-versions", json={
        "technology_id": tid, "version": " 3.14 ", "release_date": "2026-10-01",
    })
    assert version.status_code == 201, version.text
    vid = version.json()["technology_version_id"]
    assert version.json()["release_date"] == "2026-10-01"
    assert api.get(f"/api/v1/technology-versions/{vid}").json() == version.json()
    assert api.get(f"/api/v1/technology-versions/{uuid4()}").status_code == 404
    assert api.post("/api/v1/technology-versions", json={"technology_id": tid, "version": "3.14"}).status_code == 409
    assert api.get("/api/v1/technology-versions", params={"technology_id": tid}).json()["total"] == 1
    assert api.get("/api/v1/technology-versions", params={"technology_id": str(uuid4())}).json()["total"] == 0
    assert api.get("/api/v1/technology-versions", params={"limit": 0}).status_code == 422


def test_catalog_rbacs(api):
    app.dependency_overrides[requester_identity] = lambda: RequesterIdentity(
        permissions=frozenset({"knowledge.read"}),
    )
    assert api.get("/api/v1/technologies").status_code == 200
    assert api.post("/api/v1/technologies", json={"name": "Go"}).status_code == 403
    assert api.post("/api/v1/technology-versions", json={
        "technology_id": str(uuid4()), "version": "1",
    }).status_code == 403
    app.dependency_overrides[requester_identity] = lambda: RequesterIdentity(
        permissions=frozenset({"knowledge.create"}),
    )
    assert api.get("/api/v1/technologies").status_code == 403
    assert api.get("/api/v1/technology-versions").status_code == 403
    assert api.post("/api/v1/technologies", json={"name": "Go"}).status_code == 201
