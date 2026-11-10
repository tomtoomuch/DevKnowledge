"""Separate MongoDB graph edges with canonical undirected keys and CAS."""
from datetime import UTC, datetime
from uuid import UUID, uuid4, uuid5, NAMESPACE_URL

from pymongo import ASCENDING, DESCENDING, ReturnDocument
from pymongo.asynchronous.database import AsyncDatabase

from app.schemas.relations import (
    RelationCreate, RelationPage, RelationRead, RelationTypeRead, RelationUpdate,
)

# MLD v0.2 names; directedness is explicit instead of implicit.
RELATION_TYPES = (
    ("DEPENDS_ON", "Dépend de", True),
    ("COMPLEMENTS", "Complète", False),
    ("CONTRADICTS", "Contredit", False),
    ("SUPERSEDES", "Remplace", True),
    ("RELATED_TO", "En rapport avec", False),
)


class RelationNotFound(Exception):
    """Requested relation or knowledge endpoint is unavailable."""


class RelationConflict(Exception):
    """The relation has been updated by someone else."""


class RelationReferenceError(Exception):
    """Relation type or active endpoint does not exist."""


class MongoRelationRepository:
    def __init__(self, database: AsyncDatabase) -> None:
        self.types = database["relation_types"]
        self.edges = database["knowledge_relations"]
        self.knowledge = database["knowledge_items"]

    @staticmethod
    def _now() -> datetime:
        stamp = datetime.now(UTC)
        return stamp.replace(microsecond=(stamp.microsecond // 1000) * 1000)

    @staticmethod
    def _type_id(code: str) -> str:
        return str(uuid5(NAMESPACE_URL, f"devknowledge:relation-type:{code}"))

    async def ensure_catalog(self) -> None:
        await self.types.create_index([("code", ASCENDING)], name="code_unique", unique=True)
        await self.edges.create_index([("relation_key", ASCENDING)],
                                      name="relation_key_unique", unique=True)
        await self.edges.create_index([("origin_knowledge_id", ASCENDING)],
                                      name="origin_index")
        await self.edges.create_index([("target_knowledge_id", ASCENDING)],
                                      name="target_index")
        for code, label, directed in RELATION_TYPES:
            await self.types.update_one(
                {"_id": self._type_id(code)},
                {"$setOnInsert": {
                    "code": code, "label": label, "is_directed": directed,
                }},
                upsert=True,
            )

    @staticmethod
    def _decode_type(doc: dict) -> RelationTypeRead:
        return RelationTypeRead(
            relation_type_id=UUID(doc["_id"]),
            code=doc["code"], label=doc["label"], is_directed=doc["is_directed"],
        )

    @staticmethod
    def _decode(doc: dict) -> RelationRead:
        return RelationRead(
            relation_id=UUID(doc["_id"]),
            origin_knowledge_id=UUID(doc["origin_knowledge_id"]),
            target_knowledge_id=UUID(doc["target_knowledge_id"]),
            relation_type_id=UUID(doc["relation_type_id"]),
            relation_notes=doc.get("relation_notes"),
            revision=doc["revision"],
            created_at=doc["created_at"], updated_at=doc["updated_at"],
        )

    async def list_types(self) -> list[RelationTypeRead]:
        cursor = self.types.find({}).sort([("code", ASCENDING)])
        return [self._decode_type(row) for row in await cursor.to_list(length=100)]

    async def _active_knowledge(self, knowledge_id: UUID) -> bool:
        return await self.knowledge.find_one(
            {"_id": str(knowledge_id), "deleted_at": None},
            projection={"_id": 1},
        ) is not None

    async def _validate_endpoints(self, source: UUID, target: UUID) -> None:
        if not await self._active_knowledge(source) or not await self._active_knowledge(target):
            raise RelationReferenceError

    async def create(self, payload: RelationCreate) -> RelationRead:
        kind = await self.types.find_one({"_id": str(payload.relation_type_id)})
        if kind is None:
            raise RelationReferenceError
        await self._validate_endpoints(payload.origin_knowledge_id, payload.target_knowledge_id)
        origin, target = str(payload.origin_knowledge_id), str(payload.target_knowledge_id)
        if not kind["is_directed"] and target < origin:
            origin, target = target, origin
        now = self._now()
        doc = {
            "_id": str(uuid4()), "origin_knowledge_id": origin,
            "target_knowledge_id": target,
            "relation_type_id": str(payload.relation_type_id),
            "relation_key": f"{payload.relation_type_id}:{origin}:{target}",
            "relation_notes": payload.relation_notes,
            "revision": 1, "created_at": now, "updated_at": now,
        }
        await self.edges.insert_one(doc)
        return self._decode(doc)

    async def get(self, relation_id: UUID) -> RelationRead | None:
        doc = await self.edges.find_one({"_id": str(relation_id)})
        return self._decode(doc) if doc else None

    async def list(
        self, *, knowledge_id: UUID, skip: int, limit: int,
    ) -> RelationPage:
        if not await self._active_knowledge(knowledge_id):
            raise RelationNotFound
        link_query = {"$or": [
            {"origin_knowledge_id": str(knowledge_id)},
            {"target_knowledge_id": str(knowledge_id)},
        ]}
        total = await self.edges.count_documents(link_query)
        docs = await self.edges.find(link_query).sort(
            [("created_at", DESCENDING), ("_id", ASCENDING)]
        ).skip(skip).limit(limit).to_list(length=limit)
        return RelationPage(
            items=[self._decode(doc) for doc in docs],
            total=total, skip=skip, limit=limit,
        )

    async def _raise_write_failure(self, relation_id: UUID) -> None:
        if await self.edges.find_one({"_id": str(relation_id)}) is None:
            raise RelationNotFound
        raise RelationConflict

    async def update(
        self, relation_id: UUID, payload: RelationUpdate, revision: int,
    ) -> RelationRead:
        doc = await self.edges.find_one_and_update(
            {"_id": str(relation_id), "revision": revision},
            {"$set": {
                "relation_notes": payload.relation_notes, "updated_at": self._now(),
            }, "$inc": {"revision": 1}},
            return_document=ReturnDocument.AFTER,
        )
        if doc is None:
            await self._raise_write_failure(relation_id)
        return self._decode(doc)

    async def delete(self, relation_id: UUID, revision: int) -> None:
        result = await self.edges.delete_one({"_id": str(relation_id), "revision": revision})
        if not result.deleted_count:
            await self._raise_write_failure(relation_id)
