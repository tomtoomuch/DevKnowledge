"""Idempotent reference catalog; no migration or destructive rewriting."""
from uuid import NAMESPACE_URL, uuid5

from pydantic import BaseModel, ConfigDict, Field
from pymongo.asynchronous.database import AsyncDatabase

from app.schemas.specializations import KnowledgeType, LABELS, SCHEMAS


class KnowledgeTypeRead(BaseModel):
    model_config = ConfigDict(extra="forbid")
    code: KnowledgeType
    label: str
    schema_version: int = Field(ge=1)
    required_fields: list[str]


class MongoKnowledgeTypeRepository:
    def __init__(self, database: AsyncDatabase) -> None:
        self.collection = database["knowledge_types"]

    async def ensure_catalog(self) -> None:
        await self.collection.create_index("code", unique=True, name="code_unique")
        for kind, schema in SCHEMAS.items():
            document = {
                "_id": str(uuid5(NAMESPACE_URL, "devknowledge:knowledge-type:" + kind.value)),
                "code": kind.value,
                "label": LABELS[kind],
                "schema_version": 1,
                "required_fields": [
                    name for name, field in schema.model_fields.items() if field.is_required()
                ],
            }
            # Evolve only managed metadata; never remove user knowledge.
            await self.collection.update_one({"_id": document["_id"]},
                                             {"$set": {k: v for k, v in document.items() if k != "_id"}},
                                             upsert=True)

    async def list(self) -> list[KnowledgeTypeRead]:
        cursor = self.collection.find({}, {"_id": 0}).sort("code", 1)
        docs = await cursor.to_list(length=len(SCHEMAS))
        return [KnowledgeTypeRead.model_validate(doc) for doc in docs]
