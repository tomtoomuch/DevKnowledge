"""Business rules with an injected repository, no database connection."""

import asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest
from pymongo.errors import ServerSelectionTimeoutError

from app.schemas.knowledge import KnowledgeCreate, KnowledgeUpdate
from app.services.knowledge_service import KnowledgeNotFound, KnowledgeService, RequesterIdentity


def run(coroutine):
    return asyncio.run(coroutine)


def as_dict(value):
    return value.model_dump() if hasattr(value, "model_dump") else value


def document():
    timestamp = datetime(2026, 1, 1, tzinfo=timezone.utc)
    return {
        "knowledge_id": uuid4(), "knowledge_type": "CODE_SNIPPET", "title": "A title",
        "content": "original content\n", "description": "Description", "language_code": "fr",
        "difficulty_level": None, "status": "DRAFT", "is_favorite": False,
        "created_at": timestamp, "updated_at": timestamp, "validated_at": None,
        "created_by_user_id": None, "deleted_at": None,
    }


def repository():
    result = AsyncMock()
    result.create.side_effect = lambda item: item
    return result


def test_create_generates_audit_fields_and_anonymous_identity():
    repo = repository()
    payload = KnowledgeCreate(knowledge_type="CODE_SNIPPET", title="A title", content="code\n")
    result = as_dict(run(KnowledgeService(repo).create(payload, RequesterIdentity())))
    stored = repo.create.await_args.args[0]
    assert UUID(str(stored["knowledge_id"])).version == 4
    assert stored["created_by_user_id"] is None
    assert stored["created_at"] == stored["updated_at"]
    assert stored["created_at"].utcoffset().total_seconds() == 0
    assert stored["created_at"].microsecond % 1000 == 0
    assert stored["validated_at"] is None
    assert stored["deleted_at"] is None
    assert stored["status"] == "DRAFT"
    assert stored["is_favorite"] is False
    assert stored["content"] == "code\n"
    assert result["knowledge_id"] == stored["knowledge_id"]
    repo.create.assert_awaited_once()


def test_create_accepts_identity_only_from_injected_requester():
    repo = repository()
    author = uuid4()
    payload = KnowledgeCreate(knowledge_type="BUG_FIX", title="Fix", content="Details")
    result = as_dict(run(KnowledgeService(repo).create(payload, RequesterIdentity(user_id=author))))
    assert result["created_by_user_id"] == author
    assert repo.create.await_args.args[0]["created_by_user_id"] == author


def test_get_uses_repository_and_returns_resource():
    repo = repository()
    item = document()
    repo.get.return_value = item
    result = as_dict(run(KnowledgeService(repo).get(item["knowledge_id"])))
    assert result["knowledge_id"] == item["knowledge_id"]
    repo.get.assert_awaited_once_with(item["knowledge_id"])


def test_list_passes_filters_and_total_independently_of_page_size():
    repo = repository()
    item = document()
    repo.list.return_value = ([item], 7)
    result = as_dict(run(KnowledgeService(repo).list(skip=2, limit=1, knowledge_type="CODE_SNIPPET", status="DRAFT")))
    assert result["total"] == 7
    assert result["skip"] == 2
    assert result["limit"] == 1
    assert len(result["items"]) == 1
    repo.list.assert_awaited_once_with(skip=2, limit=1, knowledge_type="CODE_SNIPPET", status="DRAFT", q=None, is_favorite=None)


def test_search_and_favorites_filters_are_forwarded_to_repository():
    repo = repository()
    repo.list.return_value = ([], 0)
    result = run(KnowledgeService(repo).list(q="literal.*", is_favorite=True))
    assert result.total == 0
    repo.list.assert_awaited_once_with(
        skip=0, limit=20, knowledge_type=None, status=None,
        q="literal.*", is_favorite=True,
    )


def test_patch_sends_only_explicit_fields_and_server_timestamp():
    repo = repository()
    item = document()
    repo.update.side_effect = lambda knowledge_id, changes, revision: {**item, **changes}
    payload = KnowledgeUpdate(title="Updated", description=None)
    result = as_dict(run(KnowledgeService(repo).update(item["knowledge_id"], payload)))
    knowledge_id, changes, revision = repo.update.await_args.args
    assert knowledge_id == item["knowledge_id"]
    assert set(changes) == {"title", "description", "updated_at"}
    assert changes["title"] == "Updated"
    assert changes["description"] is None
    assert changes["updated_at"] > item["updated_at"]
    assert changes["updated_at"].utcoffset().total_seconds() == 0
    assert changes["updated_at"].microsecond % 1000 == 0
    assert result["created_at"] == item["created_at"]
    assert result["content"] == item["content"]


def test_delete_requests_soft_delete_with_server_utc_timestamp():
    repo = repository()
    repo.soft_delete.return_value = True
    knowledge_id = uuid4()
    run(KnowledgeService(repo).delete(knowledge_id))
    called_id, timestamp, revision = repo.soft_delete.await_args.args
    assert called_id == knowledge_id
    assert timestamp.utcoffset().total_seconds() == 0
    assert timestamp.microsecond % 1000 == 0
    repo.soft_delete.assert_awaited_once()


@pytest.mark.parametrize("operation", ["get", "update", "delete"])
def test_missing_resources_raise_domain_error(operation):
    repo = repository()
    repo.get.return_value = None
    repo.update.return_value = None
    repo.soft_delete.return_value = False
    service = KnowledgeService(repo)
    knowledge_id = uuid4()
    operations = {
        "get": lambda: service.get(knowledge_id),
        "update": lambda: service.update(knowledge_id, KnowledgeUpdate(title="Updated")),
        "delete": lambda: service.delete(knowledge_id),
    }
    with pytest.raises(KnowledgeNotFound):
        run(operations[operation]())


@pytest.mark.parametrize("operation", ["create", "get", "list", "update", "delete"])
def test_technical_failures_propagate_for_http_error_translation(operation):
    repo = repository()
    knowledge_id = uuid4()
    method = {"delete": "soft_delete"}.get(operation, operation)
    getattr(repo, method).side_effect = ServerSelectionTimeoutError("database unavailable")
    service = KnowledgeService(repo)
    operations = {
        "create": lambda: service.create(KnowledgeCreate(knowledge_type="CODE_SNIPPET", title="Title", content="Content"), RequesterIdentity()),
        "get": lambda: service.get(knowledge_id),
        "list": lambda: service.list(),
        "update": lambda: service.update(knowledge_id, KnowledgeUpdate(title="Updated")),
        "delete": lambda: service.delete(knowledge_id),
    }
    with pytest.raises(ServerSelectionTimeoutError):
        run(operations[operation]())
