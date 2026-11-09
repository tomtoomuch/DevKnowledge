"""MongoDB persistence with explicit UUID and UTC representations."""

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from pymongo import ASCENDING, DESCENDING, ReturnDocument
from pymongo.asynchronous.database import AsyncDatabase


class MongoKnowledgeRepository:
    """Reuse the application's database; never create a client per request."""

    def __init__(self, database: AsyncDatabase) -> None:
        self.collection = database["knowledge_items"]

    async def ensure_indexes(self) -> None:
        await self.collection.create_index(
            [("deleted_at", ASCENDING), ("created_at", DESCENDING), ("_id", ASCENDING)],
            name="active_chronological",
        )

    @staticmethod
    def _encode(item: dict[str, Any]) -> dict[str, Any]:
        document = dict(item)
        document["_id"] = str(document.pop("knowledge_id"))
        if document.get("created_by_user_id") is not None:
            document["created_by_user_id"] = str(document["created_by_user_id"])
        return document

    @staticmethod
    def _decode(document: dict[str, Any]) -> dict[str, Any]:
        item = dict(document)
        item["knowledge_id"] = UUID(item.pop("_id"))
        if item.get("created_by_user_id") is not None:
            item["created_by_user_id"] = UUID(item["created_by_user_id"])
        # BSON dates are UTC with millisecond precision. The configured client
        # uses tz_aware=True; normalize to UTC also for a supplied test adapter.
        for field in ("created_at", "updated_at", "validated_at", "deleted_at"):
            value = item.get(field)
            if isinstance(value, datetime):
                item[field] = (
                    value.replace(tzinfo=UTC) if value.tzinfo is None
                    else value.astimezone(UTC)
                )
        return item

    @staticmethod
    def _active_filter(knowledge_id: UUID) -> dict[str, Any]:
        return {"_id": str(knowledge_id), "deleted_at": None}

    @classmethod
    def _revision_filter(cls, knowledge_id: UUID, revision: int) -> dict[str, Any]:
        query = cls._active_filter(knowledge_id)
        if revision == 0:
            query["$or"] = [{"revision": 0}, {"revision": {"$exists": False}}]
        else:
            query["revision"] = revision
        return query

    async def create(self, item: dict[str, Any]) -> dict[str, Any]:
        document = self._encode(item)
        await self.collection.insert_one(document)
        return self._decode(document)

    async def get(self, knowledge_id: UUID) -> dict[str, Any] | None:
        document = await self.collection.find_one(self._active_filter(knowledge_id))
        return self._decode(document) if document is not None else None

    async def list(
        self,
        *,
        skip: int,
        limit: int,
        knowledge_type: str | None = None,
        status: str | None = None,
    ) -> tuple[list[dict[str, Any]], int]:
        query: dict[str, Any] = {"deleted_at": None}
        if knowledge_type is not None:
            query["knowledge_type"] = knowledge_type
        if status is not None:
            query["status"] = status
        total = await self.collection.count_documents(query)
        cursor = (
            self.collection.find(query)
            .sort([("created_at", DESCENDING), ("_id", ASCENDING)])
            .skip(skip)
            .limit(limit)
        )
        documents = await cursor.to_list(length=limit)
        return [self._decode(document) for document in documents], total

    async def update(
        self, knowledge_id: UUID, changes: dict[str, Any], expected_revision: int = 0
    ) -> dict[str, Any] | None:
        document = await self.collection.find_one_and_update(
            self._revision_filter(knowledge_id, expected_revision),
            {"$set": changes, "$inc": {"revision": 1}},
            return_document=ReturnDocument.AFTER,
        )
        return self._decode(document) if document is not None else None

    async def soft_delete(self, knowledge_id: UUID, deleted_at: datetime, expected_revision: int = 0) -> bool:
        document = await self.collection.find_one_and_update(
            self._revision_filter(knowledge_id, expected_revision),
            {"$set": {"deleted_at": deleted_at, "updated_at": deleted_at}, "$inc": {"revision": 1}},
            return_document=ReturnDocument.AFTER,
        )
        return document is not None
