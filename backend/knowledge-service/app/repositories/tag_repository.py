"""MongoDB reference catalog of immutable, reusable tag identities."""
from uuid import UUID, uuid4

from pymongo import ASCENDING
from pymongo.asynchronous.database import AsyncDatabase

from app.schemas.tags import TagCreate, TagPage, TagRead


class UnknownTagError(Exception):
    """An assigned tag ID does not exist in the reference catalog."""


class MongoTagRepository:
    def __init__(self, database: AsyncDatabase) -> None:
        self.collection = database["tags"]

    async def ensure_indexes(self) -> None:
        await self.collection.create_index(
            [("name_key", ASCENDING)], name="name_key_unique", unique=True,
        )

    async def create(self, payload: TagCreate) -> TagRead:
        document = {
            "_id": str(uuid4()),
            "name": payload.name,
            "name_key": payload.name.casefold(),
        }
        await self.collection.insert_one(document)
        return TagRead(tag_id=UUID(document["_id"]), name=document["name"])

    async def get(self, tag_id: UUID) -> TagRead | None:
        document = await self.collection.find_one({"_id": str(tag_id)})
        if document is None:
            return None
        return TagRead(tag_id=UUID(document["_id"]), name=document["name"])

    async def list(self, *, skip: int, limit: int) -> TagPage:
        total = await self.collection.count_documents({})
        cursor = self.collection.find({}).sort(
            [("name_key", ASCENDING), ("_id", ASCENDING)]
        ).skip(skip).limit(limit)
        rows = await cursor.to_list(length=limit)
        return TagPage(
            items=[TagRead(tag_id=UUID(row["_id"]), name=row["name"]) for row in rows],
            total=total, skip=skip, limit=limit,
        )

    async def ensure_exist(self, tag_ids: list[UUID]) -> None:
        if not tag_ids:
            return
        keys = [str(tag_id) for tag_id in tag_ids]
        if await self.collection.count_documents({"_id": {"$in": keys}}) != len(keys):
            raise UnknownTagError
