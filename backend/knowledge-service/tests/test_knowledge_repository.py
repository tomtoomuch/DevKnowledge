import asyncio
from datetime import UTC, datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4

import pytest
from bson import BSON
from bson.codec_options import CodecOptions
from pymongo import ReturnDocument
from pymongo.errors import ConnectionFailure

from app.repositories.knowledge_repository import MongoKnowledgeRepository


def run(coroutine):
    return asyncio.run(coroutine)


@pytest.fixture
def collection():
    collection = MagicMock()
    for method in ("create_index", "insert_one", "find_one", "count_documents", "find_one_and_update"):
        setattr(collection, method, AsyncMock())
    return collection


@pytest.fixture
def repository(collection):
    database = MagicMock()
    database.__getitem__.return_value = collection
    return MongoKnowledgeRepository(database)


@pytest.fixture
def item():
    timestamp = datetime(2026, 11, 2, 14, 30, 0, 123000, tzinfo=UTC)
    return {
        "knowledge_id": uuid4(),
        "knowledge_type": "CODE_SNIPPET",
        "title": "Example",
        "description": None,
        "content": "print('hello')",
        "language_code": "python",
        "difficulty_level": None,
        "status": "DRAFT",
        "created_at": timestamp,
        "updated_at": timestamp,
        "validated_at": None,
        "created_by_user_id": None,
        "is_favorite": False,
        "deleted_at": None,
    }


def test_create_stores_canonical_uuid_without_duplicate_identifier(repository, collection, item):
    result = run(repository.create(item))
    document = collection.insert_one.await_args.args[0]
    assert document["_id"] == str(item["knowledge_id"])
    assert "knowledge_id" not in document
    assert result == item
    assert "_id" not in item


def test_uuid_and_utc_dates_survive_real_bson_serialization(repository, item):
    item["created_by_user_id"] = uuid4()
    document = repository._encode(item)
    raw = BSON.encode(document)
    decoded = BSON(raw).decode(codec_options=CodecOptions(tz_aware=True, tzinfo=UTC))
    restored = repository._decode(decoded)
    assert restored == item
    assert isinstance(restored["knowledge_id"], UUID)
    assert isinstance(restored["created_by_user_id"], UUID)
    assert restored["created_at"].utcoffset() == timedelta(0)


def test_decode_normalizes_naive_and_offset_dates(repository, item):
    document = repository._encode(item)
    document["created_at"] = item["created_at"].replace(tzinfo=None)
    document["updated_at"] = item["updated_at"].astimezone(timezone(timedelta(hours=2)))
    restored = repository._decode(document)
    assert restored["created_at"] == item["created_at"]
    assert restored["updated_at"] == item["updated_at"]
    assert restored["updated_at"].utcoffset() == timedelta(0)


def test_get_only_reads_active_documents(repository, collection, item):
    collection.find_one.return_value = repository._encode(item)
    assert run(repository.get(item["knowledge_id"])) == item
    collection.find_one.assert_awaited_once_with({"_id": str(item["knowledge_id"]), "deleted_at": None})
    collection.find_one.return_value = None
    assert run(repository.get(uuid4())) is None


@pytest.mark.parametrize("knowledge_type,status", [(None, None), ("CODE_SNIPPET", None), (None, "DRAFT"), ("CODE_SNIPPET", "DRAFT")])
def test_list_filters_paginates_and_sorts_deterministically(repository, collection, item, knowledge_type, status):
    cursor = MagicMock()
    collection.find.return_value = cursor
    cursor.sort.return_value = cursor
    cursor.skip.return_value = cursor
    cursor.limit.return_value = cursor
    cursor.to_list = AsyncMock(return_value=[repository._encode(item)])
    collection.count_documents.return_value = 7

    result = run(repository.list(skip=2, limit=3, knowledge_type=knowledge_type, status=status))

    expected_filter = {"deleted_at": None}
    if knowledge_type:
        expected_filter["knowledge_type"] = knowledge_type
    if status:
        expected_filter["status"] = status
    collection.find.assert_called_once_with(expected_filter)
    collection.count_documents.assert_awaited_once_with(expected_filter)
    cursor.sort.assert_called_once_with([("created_at", -1), ("_id", 1)])
    cursor.skip.assert_called_once_with(2)
    cursor.limit.assert_called_once_with(3)
    cursor.to_list.assert_awaited_once_with(length=3)
    assert result == ([item], 7)


def test_global_search_matches_literals_only_and_can_combine_favorite_filter(repository, collection, item):
    cursor = MagicMock()
    collection.find.return_value = cursor
    cursor.sort.return_value = cursor
    cursor.skip.return_value = cursor
    cursor.limit.return_value = cursor
    cursor.to_list = AsyncMock(return_value=[repository._encode(item)])
    collection.count_documents.return_value = 1
    page, total = run(repository.list(
        skip=0, limit=20, knowledge_type="CODE_SNIPPET", q="a.*(b)",
        is_favorite=False,
    ))
    query = collection.find.call_args.args[0]
    assert query["deleted_at"] is None
    assert query["is_favorite"] is False
    assert query["knowledge_type"] == "CODE_SNIPPET"
    assert [next(iter(part)) for part in query["$or"]] == ["title", "description", "content"]
    for part in query["$or"]:
        expression = next(iter(part.values()))
        assert expression == {"$regex": r"a\.\*\(b\)", "$options": "i"}
    collection.count_documents.assert_awaited_once_with(query)
    assert total == 1 and page[0]["knowledge_id"] == item["knowledge_id"]


def test_update_is_atomic_and_only_targets_active_documents(repository, collection, item):
    changes = {"title": "Updated", "updated_at": item["updated_at"]}
    collection.find_one_and_update.return_value = repository._encode({**item, **changes})
    assert run(repository.update(item["knowledge_id"], changes))["title"] == "Updated"
    collection.find_one_and_update.assert_awaited_once_with(
        {"_id": str(item["knowledge_id"]), "deleted_at": None, "$or": [{"revision": 0}, {"revision": {"$exists": False}}]},
        {"$set": changes, "$inc": {"revision": 1}},
        return_document=ReturnDocument.AFTER,
    )
    collection.find_one_and_update.return_value = None
    assert run(repository.update(uuid4(), changes)) is None


def test_soft_delete_is_atomic_and_never_calls_physical_delete(repository, collection, item):
    collection.find_one_and_update.return_value = repository._encode(item)
    assert run(repository.soft_delete(item["knowledge_id"], item["updated_at"])) is True
    collection.find_one_and_update.assert_awaited_once_with(
        {"_id": str(item["knowledge_id"]), "deleted_at": None, "$or": [{"revision": 0}, {"revision": {"$exists": False}}]},
        {"$set": {"deleted_at": item["updated_at"], "updated_at": item["updated_at"]}, "$inc": {"revision": 1}},
        return_document=ReturnDocument.AFTER,
    )
    collection.find_one_and_update.return_value = None
    assert run(repository.soft_delete(item["knowledge_id"], item["updated_at"])) is False
    collection.delete_one.assert_not_called()


def test_index_initialization_is_idempotent_request(repository, collection):
    run(repository.ensure_indexes())
    run(repository.ensure_indexes())
    assert collection.create_index.await_count == 2
    collection.create_index.assert_awaited_with(
        [("deleted_at", 1), ("created_at", -1), ("_id", 1)],
        name="active_chronological",
    )


@pytest.mark.parametrize("operation", ["create", "get", "list", "update", "soft_delete", "ensure_indexes"])
def test_mongodb_errors_propagate_for_sanitized_http_handling(repository, collection, item, operation):
    collection.insert_one.side_effect = ConnectionFailure("sensitive connection details")
    collection.find_one.side_effect = ConnectionFailure("sensitive connection details")
    collection.count_documents.side_effect = ConnectionFailure("sensitive connection details")
    collection.find_one_and_update.side_effect = ConnectionFailure("sensitive connection details")
    collection.create_index.side_effect = ConnectionFailure("sensitive connection details")
    calls = {
        "create": lambda: repository.create(item),
        "get": lambda: repository.get(item["knowledge_id"]),
        "list": lambda: repository.list(skip=0, limit=10),
        "update": lambda: repository.update(item["knowledge_id"], {"title": "updated"}),
        "soft_delete": lambda: repository.soft_delete(item["knowledge_id"], item["updated_at"]),
        "ensure_indexes": repository.ensure_indexes,
    }
    with pytest.raises(ConnectionFailure):
        run(calls[operation]())
