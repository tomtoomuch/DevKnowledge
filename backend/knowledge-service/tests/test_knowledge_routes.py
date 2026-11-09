"""HTTP contracts exercised without a running MongoDB server."""

from copy import deepcopy
from datetime import datetime, timezone
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from pymongo.errors import ServerSelectionTimeoutError

from app.api.routes.knowledges import get_knowledge_service, get_requester_identity
from app.services.knowledge_service import RequesterIdentity
from app.main import app
from app.services.knowledge_service import KnowledgeService


BASE = "/api/v1/knowledges"
VALID_PAYLOAD = {
    "knowledge_type": "CODE_SNIPPET",
    "title": "Un exemple Python",
    "content": "print('bonjour')\n",
}


class MemoryRepository:
    """A repository double, injected at the HTTP composition boundary."""

    def __init__(self):
        self.items = {}
        self.fail = False

    def check_available(self):
        if self.fail:
            raise ServerSelectionTimeoutError("secret-message-password")

    async def create(self, item):
        self.check_available()
        self.items[item["knowledge_id"]] = deepcopy(item)
        return deepcopy(item)

    async def get(self, knowledge_id):
        self.check_available()
        item = self.items.get(knowledge_id)
        if item is None or item["deleted_at"] is not None:
            return None
        return deepcopy(item)

    async def list(self, *, skip, limit, knowledge_type=None, status=None, q=None, is_favorite=None):
        self.check_available()
        items = [
            deepcopy(item)
            for item in self.items.values()
            if item["deleted_at"] is None
            and (knowledge_type is None or item["knowledge_type"] == knowledge_type)
            and (status is None or item["status"] == status)
            and (is_favorite is None or item["is_favorite"] is is_favorite)
            and (q is None or q.casefold() in (
                item["title"] + " " + (item["description"] or "") + " " + item["content"]
            ).casefold())
        ]
        items.sort(key=lambda item: (-item["created_at"].timestamp(), str(item["knowledge_id"])))
        return items[skip : skip + limit], len(items)

    async def update(self, knowledge_id, changes, expected_revision=0):
        self.check_available()
        if await self.get(knowledge_id) is None or self.items[knowledge_id].get("revision", 0) != expected_revision:
            return None
        self.items[knowledge_id].update(deepcopy(changes))
        self.items[knowledge_id]["revision"] = expected_revision + 1
        return deepcopy(self.items[knowledge_id])

    async def soft_delete(self, knowledge_id, deleted_at, expected_revision=0):
        self.check_available()
        if await self.get(knowledge_id) is None or self.items[knowledge_id].get("revision", 0) != expected_revision:
            return False
        self.items[knowledge_id].update(deleted_at=deleted_at, updated_at=deleted_at, revision=expected_revision + 1)
        return True


@pytest.fixture
def api():
    repository = MemoryRepository()
    app.dependency_overrides[get_knowledge_service] = lambda: KnowledgeService(repository)
    app.dependency_overrides[get_requester_identity] = lambda: RequesterIdentity(
        permissions=frozenset({"knowledge.read", "knowledge.create", "knowledge.update", "knowledge.delete"}),
    )
    # Deliberately do not enter TestClient: lifespan would need a real database.
    client = TestClient(app)
    try:
        yield client, repository
    finally:
        client.close()
        app.dependency_overrides.pop(get_knowledge_service, None)
        app.dependency_overrides.pop(get_requester_identity, None)


def create(client, **changes):
    response = client.post(BASE, json={**VALID_PAYLOAD, **changes})
    assert response.status_code == 201, response.text
    return response.json()


def test_create_defaults_uuid_and_utc_serialization(api):
    client, repository = api
    item = create(client)
    knowledge_id = UUID(item["knowledge_id"])
    assert knowledge_id.version == 4
    assert str(knowledge_id) == item["knowledge_id"]
    assert item["status"] == "DRAFT"
    assert item["is_favorite"] is False
    assert item["created_by_user_id"] is None
    assert item["validated_at"] is None
    assert item["deleted_at"] is None
    assert item["content"] == VALID_PAYLOAD["content"]
    for field in ("created_at", "updated_at"):
        value = datetime.fromisoformat(item[field].replace("Z", "+00:00"))
        assert value.utcoffset().total_seconds() == 0
        assert repository.items[knowledge_id][field].tzinfo is not None
    assert item["created_at"] == item["updated_at"]
    assert "_id" not in item


@pytest.mark.parametrize(
    "change",
    [
        {"knowledge_type": "UNKNOWN"},
        {"knowledge_type": None},
        {"title": " "},
        {"title": "x" * 151},
        {"title": None},
        {"content": "\n\t"},
        {"content": None},
        {"status": " "},
        {"status": "x" * 31},
        {"language_code": "x" * 11},
        {"difficulty_level": "x" * 31},
        {"is_favorite": "false"},
        {"is_favorite": None},
        {"knowledge_id": str(uuid4())},
        {"knowledge_type_id": str(uuid4())},
        {"created_by_user_id": str(uuid4())},
        {"created_at": "2026-01-01T00:00:00Z"},
        {"updated_at": "2026-01-01T00:00:00Z"},
        {"validated_at": "2026-01-01T00:00:00Z"},
        {"deleted_at": "2026-01-01T00:00:00Z"},
        {"unexpected": True},
    ],
)
def test_create_invalid_and_internal_fields_are_rejected(api, change):
    client, repository = api
    response = client.post(BASE, json={**VALID_PAYLOAD, **change})
    assert response.status_code == 422
    assert repository.items == {}


@pytest.mark.parametrize("missing", ["title", "content", "knowledge_type"])
def test_create_required_fields(api, missing):
    client, _ = api
    payload = dict(VALID_PAYLOAD)
    del payload[missing]
    assert client.post(BASE, json=payload).status_code == 422


@pytest.mark.parametrize(
    "knowledge_type",
    [
        "CODE_SNIPPET", "TERMINAL_COMMAND", "TECHNICAL_PROCEDURE", "COURSE_NOTE",
        "BUG_FIX", "DOCUMENTATION_RESOURCE", "BEST_PRACTICE", "COMPLIANCE_STANDARD",
    ],
)
def test_all_eight_knowledge_types_are_accepted(api, knowledge_type):
    client, _ = api
    assert create(client, knowledge_type=knowledge_type)["knowledge_type"] == knowledge_type


def test_get_existing_and_missing(api):
    client, _ = api
    item = create(client)
    response = client.get(f"{BASE}/{item['knowledge_id']}")
    assert response.status_code == 200
    assert response.json() == item
    assert client.get(f"{BASE}/{uuid4()}").status_code == 404


@pytest.mark.parametrize("method", ["get", "patch", "delete"])
def test_invalid_uuid_returns_422(api, method):
    client, _ = api
    kwargs = {"json": {"title": "Updated"}} if method == "patch" else {}
    assert getattr(client, method)(f"{BASE}/invalid-id", headers={"If-Match": '"0"'}, **kwargs).status_code == 422


def test_list_empty(api):
    client, _ = api
    response = client.get(BASE)
    assert response.status_code == 200
    assert response.json() == {"items": [], "total": 0, "skip": 0, "limit": 20}


def test_list_pagination_and_filters(api):
    client, repository = api
    first = create(client, title="First", status="PUBLISHED")
    second = create(client, title="Second", knowledge_type="BUG_FIX", status="PUBLISHED")
    third = create(client, title="Third", knowledge_type="BUG_FIX")
    # Equal dates exercise the documented UUID tie-breaker deterministically.
    for item in repository.items.values():
        item["created_at"] = datetime(2026, 1, 1, tzinfo=timezone.utc)
    expected_ids = sorted([item["knowledge_id"] for item in (first, second, third)])
    page = client.get(BASE, params={"skip": 1, "limit": 1}).json()
    assert page["total"] == 3
    assert page["skip"] == 1
    assert page["limit"] == 1
    assert [item["knowledge_id"] for item in page["items"]] == expected_ids[1:2]
    assert client.get(BASE, params={"skip": 99}).json()["items"] == []
    by_type = client.get(BASE, params={"knowledge_type": "BUG_FIX"}).json()
    assert by_type["total"] == 2
    by_status = client.get(BASE, params={"status": "PUBLISHED"}).json()
    assert by_status["total"] == 2
    combined = client.get(BASE, params={"knowledge_type": "BUG_FIX", "status": "PUBLISHED"}).json()
    assert combined["total"] == 1
    assert combined["items"][0]["knowledge_id"] == second["knowledge_id"]


@pytest.mark.parametrize(
    "params",
    [
        {"skip": -1}, {"skip": "invalid"}, {"limit": 0}, {"limit": 101},
        {"knowledge_type": "UNKNOWN"}, {"status": " "}, {"status": "x" * 31},
        {"q": " "}, {"q": ""}, {"q": "x" * 101}, {"is_favorite": "invalid"},
    ],
)
def test_invalid_list_parameters(api, params):
    client, _ = api
    assert client.get(BASE, params=params).status_code == 422


def test_global_search_favorites_pagination_and_deleted_items(api):
    client, _ = api
    create(client, title="Alpha MongoDB", content="Indexes", is_favorite=True)
    create(client, title="Autre", description="alpha sauvegarde", is_favorite=False)
    other = create(client, title="Sans rapport", content="ALPHA dans le contenu", is_favorite=True)
    hidden = create(client, title="Alpha secret", is_favorite=True)
    assert delete(client, f"{BASE}/{hidden['knowledge_id']}").status_code == 204
    first = client.get(BASE, params={"q": " aLpHa ", "is_favorite": True, "limit": 1})
    assert first.status_code == 200
    assert first.json()["total"] == 2
    assert len(first.json()["items"]) == 1
    second = client.get(BASE, params={"q": "alpha", "is_favorite": True, "skip": 1, "limit": 1})
    assert second.json()["total"] == 2
    ids = {first.json()["items"][0]["knowledge_id"], second.json()["items"][0]["knowledge_id"]}
    assert other["knowledge_id"] in ids
    assert hidden["knowledge_id"] not in ids
    assert client.get(BASE, params={"q": "alpha", "is_favorite": False}).json()["total"] == 1
    assert client.get(BASE, params={"q": "no match"}).json()["total"] == 0


def test_patch_only_supplied_fields_and_optional_null(api):
    client, _ = api
    item = create(client, description="Description", language_code="fr", difficulty_level="intermediate")
    response = patch(client, f"{BASE}/{item['knowledge_id']}", json={"title": "Nouveau titre", "description": None})
    assert response.status_code == 200
    updated = response.json()
    assert updated["title"] == "Nouveau titre"
    assert updated["description"] is None
    for field in ("knowledge_id", "created_at", "created_by_user_id", "content", "status", "is_favorite", "language_code", "difficulty_level"):
        assert updated[field] == item[field]
    assert datetime.fromisoformat(updated["updated_at"].replace("Z", "+00:00")) >= datetime.fromisoformat(item["updated_at"].replace("Z", "+00:00"))
    assert patch(client, f"{BASE}/{uuid4()}", json={"title": "Updated"}).status_code == 404


def test_patch_can_change_each_mutable_field(api):
    client, _ = api
    item = create(client)
    changes = {
        "knowledge_type": "TERMINAL_COMMAND", "title": "Commande",
        "content": "git status\n", "description": "Voir les changements",
        "language_code": "fr", "difficulty_level": "beginner",
        "status": "PUBLISHED", "is_favorite": True,
    }
    response = patch(client, f"{BASE}/{item['knowledge_id']}", json=changes)
    assert response.status_code == 200
    assert all(response.json()[field] == value for field, value in changes.items())
    clear_response = patch(client,
        f"{BASE}/{item['knowledge_id']}", json={"language_code": None, "difficulty_level": None},
    )
    assert clear_response.status_code == 200
    assert clear_response.json()["language_code"] is None
    assert clear_response.json()["difficulty_level"] is None


@pytest.mark.parametrize(
    "payload",
    [
        {}, {"title": None}, {"content": None}, {"knowledge_type": None},
        {"status": None}, {"is_favorite": None}, {"title": " "}, {"content": "\n\t"},
        {"knowledge_id": str(uuid4())}, {"created_by_user_id": str(uuid4())},
        {"created_at": "2026-01-01T00:00:00Z"}, {"updated_at": "2026-01-01T00:00:00Z"},
        {"validated_at": None}, {"deleted_at": None}, {"unknown": "field"},
    ],
)
def test_patch_forbidden_invalid_and_empty_inputs(api, payload):
    client, _ = api
    item = create(client)
    assert patch(client, f"{BASE}/{item['knowledge_id']}", json=payload).status_code == 422
    assert client.get(f"{BASE}/{item['knowledge_id']}").json() == item


def test_soft_delete_hides_resource_and_double_delete_returns_404(api):
    client, repository = api
    item = create(client)
    resource = f"{BASE}/{item['knowledge_id']}"
    response = delete(client, resource)
    assert response.status_code == 204
    assert response.content == b""
    stored = repository.items[UUID(item["knowledge_id"])]
    assert stored["deleted_at"].tzinfo is not None
    assert stored["content"] == item["content"]
    assert client.get(resource).status_code == 404
    assert patch(client, resource, json={"title": "Updated"}).status_code == 404
    assert delete(client, resource).status_code == 404
    assert delete(client, f"{BASE}/{uuid4()}").status_code == 404
    assert client.get(BASE).json()["total"] == 0


@pytest.mark.parametrize("operation", ["create", "get", "list", "update", "delete"])
def test_mongodb_unavailable_returns_sanitized_503(api, caplog, operation):
    client, repository = api
    item = create(client)
    resource = f"{BASE}/{item['knowledge_id']}"
    repository.fail = True
    requests = {
        "create": lambda: client.post(BASE, json=VALID_PAYLOAD),
        "get": lambda: client.get(resource),
        "list": lambda: client.get(BASE),
        "update": lambda: patch(client, resource, json={"title": "Updated"}),
        "delete": lambda: delete(client, resource),
    }
    response = requests[operation]()
    assert response.status_code == 503
    assert "secret-message-password" not in response.text
    assert "secret-message-password" not in caplog.text


def test_uninitialized_database_returns_503(monkeypatch):
    monkeypatch.setattr(app.state, "mongodb_database", None, raising=False)
    client = TestClient(app)
    try:
        response = client.get(BASE)
    finally:
        client.close()
    assert response.status_code == 503


def test_openapi_exposes_crud_and_validation_contract():
    schema = app.openapi()
    assert set(schema["paths"][BASE]) == {"post", "get"}
    assert set(schema["paths"][BASE + "/{knowledge_id}"]) == {"get", "patch", "delete"}
    assert "201" in schema["paths"][BASE]["post"]["responses"]
    assert "204" in schema["paths"][BASE + "/{knowledge_id}"]["delete"]["responses"]
    assert "422" in schema["paths"][BASE]["post"]["responses"]
    patch_schema = schema["components"]["schemas"]["KnowledgeUpdate"]
    assert patch_schema["minProperties"] == 1
    assert "required" not in patch_schema
    for field in ("knowledge_type", "title", "content", "status", "is_favorite"):
        assert {"type": "null"} not in patch_schema["properties"][field].get("anyOf", [])
        assert patch_schema["properties"][field].get("type") != "null"
    assert {"type": "null"} in patch_schema["properties"]["description"]["anyOf"]


def patch(client, path, **kwargs):
    headers = {"If-Match": client.get(path).headers.get("etag", '"0"')}
    return client.patch(path, headers=headers, **kwargs)


def delete(client, path, **kwargs):
    headers = {"If-Match": client.get(path).headers.get("etag", '"0"')}
    return client.delete(path, headers=headers, **kwargs)


def test_revision_and_etag_prevent_lost_update_and_stale_delete(api):
    client, repository = api
    created = client.post(BASE, json=VALID_PAYLOAD)
    path = f"{BASE}/{created.json()['knowledge_id']}"
    assert created.json()["revision"] == 1
    assert created.headers["etag"] == '"1"'
    assert client.get(path).headers["etag"] == '"1"'
    assert client.patch(path, json={"title": "missing"}).status_code == 428
    assert client.delete(path).status_code == 428
    updated = client.patch(path, headers={"If-Match": '"1"'}, json={"title": "winner"})
    assert updated.status_code == 200 and updated.json()["revision"] == 2
    assert updated.headers["etag"] == '"2"'
    assert client.patch(path, headers={"If-Match": '"1"'}, json={"title": "lost"}).status_code == 412
    assert client.delete(path, headers={"If-Match": '"1"'}).status_code == 412
    assert client.get(path).json()["title"] == "winner"
    assert client.delete(path, headers={"If-Match": '"2"'}).status_code == 204


@pytest.mark.parametrize("tag", ['*', 'W/"1"', '1', '"-1"', '"01"', '"1", "2"', '"9223372036854775807"'])
def test_invalid_precondition_does_not_modify_data(api, tag):
    client, _ = api
    item = create(client)
    path = f"{BASE}/{item['knowledge_id']}"
    assert client.patch(path, headers={"If-Match": tag}, json={"title": "bad"}).status_code == 400
    assert client.get(path).json() == item


def test_duplicate_if_match_headers_rejected(api):
    client, _ = api
    item = create(client)
    assert client.delete(f"{BASE}/{item['knowledge_id']}", headers=[("If-Match", '"1"'), ("If-Match", '"2"')]).status_code == 400


def test_revision_is_server_owned(api):
    client, _ = api
    assert client.post(BASE, json={**VALID_PAYLOAD, "revision": 90}).status_code == 422
    item = create(client)
    assert patch(client, f"{BASE}/{item['knowledge_id']}", json={"revision": 90}).status_code == 422


def test_specialization_is_validated_and_persisted_through_the_existing_http_contract(api):
    client, repository = api
    bad = client.post(BASE, json={
        **VALID_PAYLOAD, "details": {"shell": "bash", "command": "ls"},
    })
    assert bad.status_code == 422
    assert repository.items == {}
    created = client.post(BASE, json={
        **VALID_PAYLOAD,
        "details": {"code": "print(1)", "programming_language": "Python"},
    })
    assert created.status_code == 201
    ident = created.json()["knowledge_id"]
    assert created.json()["details"]["code"] == "print(1)"
    assert client.get(f"{BASE}/{ident}").json()["details"]["programming_language"] == "Python"
    invalid = client.patch(f"{BASE}/{ident}", headers={"If-Match": '"1"'},
                           json={"details": {"shell": "bash", "command": "ls"}})
    assert invalid.status_code == 422
    assert client.get(f"{BASE}/{ident}").json()["revision"] == 1
    success = client.patch(f"{BASE}/{ident}", headers={"If-Match": '"1"'},
                           json={"knowledge_type": "BUG_FIX"})
    assert success.status_code == 200
    assert success.json()["details"] is None
    assert success.json()["revision"] == 2
    assert client.patch(f"{BASE}/{ident}", headers={"If-Match": '"1"'},
                        json={"details": {"root_cause": "stale"}}).status_code == 412
    assert client.get(f"{BASE}/{ident}").json()["details"] is None


def test_tag_ids_are_validated_and_legacy_records_stay_compatible(api):
    client, repository = api
    from uuid import uuid4
    tag = uuid4()
    created = create(client)
    assert created["tag_ids"] == []
    path = f"{BASE}/{created['knowledge_id']}"
    assert patch(client, path, json={"tag_ids": None}).status_code == 422
    assert patch(client, path, json={"tag_ids": [str(tag), str(tag)]}).status_code == 422
    assert patch(client, path, json={"tag_ids": ["not-a-uuid"]}).status_code == 422
    # The in-memory unit fake does not check catalog membership; database
    # integration tests exercise real referential validation.
    updated = patch(client, path, json={"tag_ids": [str(tag)]})
    assert updated.status_code == 200
    assert updated.json()["tag_ids"] == [str(tag)]
    assert patch(client, path, json={"tag_ids": []}).status_code == 200
    assert patch(client, path, json={"tag_ids": []}).json()["tag_ids"] == []


def test_technology_id_contracts_and_legacy_defaults(api):
    client, _ = api
    tech, version = str(uuid4()), str(uuid4())
    created = create(client)
    assert created["technology_ids"] == []
    assert created["technology_version_ids"] == []
    path = f"{BASE}/{created['knowledge_id']}"
    for name in ("technology_ids", "technology_version_ids"):
        for value in (None, ["not-uuid"], [tech, tech], [str(uuid4())] * 31):
            response = patch(client, path, json={name: value})
            assert response.status_code == 422, response.text
        assert client.post(BASE, json={**VALID_PAYLOAD, name: [tech, tech]}).status_code == 422
    # MemoryRepository is a shallow fake: referential integrity is exercised in Mongo integration.
    updated = patch(client, path, json={
        "technology_ids": [tech], "technology_version_ids": [version],
    })
    assert updated.status_code == 200, updated.text
    assert updated.json()["technology_ids"] == [tech]
    assert updated.json()["technology_version_ids"] == [version]
    assert patch(client, path, json={
        "technology_ids": [], "technology_version_ids": [],
    }).status_code == 200
