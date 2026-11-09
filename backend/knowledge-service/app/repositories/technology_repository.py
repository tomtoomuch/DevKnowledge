"""Immutable technology/version catalogs, with explicit referential checks."""
from uuid import UUID, uuid4

from pymongo import ASCENDING
from pymongo.asynchronous.database import AsyncDatabase

from app.schemas.technologies import (
    TechnologyCreate, TechnologyPage, TechnologyRead,
    TechnologyVersionCreate, TechnologyVersionPage, TechnologyVersionRead,
)


class UnknownTechnologyError(Exception):
    """A generic or parent technology ID does not exist."""


class UnknownTechnologyVersionError(Exception):
    """A referenced version ID does not exist."""


class DuplicateTechnologyAssociationError(Exception):
    """The same technology was linked both generically and at version level."""


class MongoTechnologyRepository:
    def __init__(self, database: AsyncDatabase) -> None:
        self.technologies = database["technologies"]
        self.versions = database["technology_versions"]

    async def ensure_indexes(self) -> None:
        await self.technologies.create_index(
            [("name_key", ASCENDING)], name="technology_name_unique", unique=True,
        )
        await self.versions.create_index(
            [("technology_id", ASCENDING), ("version_key", ASCENDING)],
            name="technology_version_unique", unique=True,
        )

    @staticmethod
    def _technology(document: dict) -> TechnologyRead:
        return TechnologyRead(
            technology_id=UUID(document["_id"]),
            name=document["name"], category=document.get("category"),
        )

    @staticmethod
    def _version(document: dict) -> TechnologyVersionRead:
        return TechnologyVersionRead(
            technology_version_id=UUID(document["_id"]),
            technology_id=UUID(document["technology_id"]),
            version=document["version"],
            release_date=document.get("release_date"),
        )

    async def create_technology(self, payload: TechnologyCreate) -> TechnologyRead:
        doc = {"_id": str(uuid4()), "name": payload.name,
               "name_key": payload.name.casefold(), "category": payload.category}
        await self.technologies.insert_one(doc)
        return self._technology(doc)

    async def get_technology(self, technology_id: UUID) -> TechnologyRead | None:
        doc = await self.technologies.find_one({"_id": str(technology_id)})
        return self._technology(doc) if doc else None

    async def list_technologies(self, *, skip: int, limit: int) -> TechnologyPage:
        total = await self.technologies.count_documents({})
        rows = await self.technologies.find({}).sort(
            [("name_key", ASCENDING), ("_id", ASCENDING)]
        ).skip(skip).limit(limit).to_list(length=limit)
        return TechnologyPage(items=[self._technology(doc) for doc in rows],
                              total=total, skip=skip, limit=limit)

    async def create_version(self, payload: TechnologyVersionCreate) -> TechnologyVersionRead:
        if await self.get_technology(payload.technology_id) is None:
            raise UnknownTechnologyError
        doc = {
            "_id": str(uuid4()),
            "technology_id": str(payload.technology_id),
            "version": payload.version,
            "version_key": payload.version.casefold(),
            # BSON has no date-only type: ISO strings avoid tz/date conversion.
            "release_date": payload.release_date.isoformat() if payload.release_date else None,
        }
        await self.versions.insert_one(doc)
        return self._version(doc)

    async def get_version(self, version_id: UUID) -> TechnologyVersionRead | None:
        doc = await self.versions.find_one({"_id": str(version_id)})
        return self._version(doc) if doc else None

    async def list_versions(
        self, *, skip: int, limit: int, technology_id: UUID | None = None,
    ) -> TechnologyVersionPage:
        query = {"technology_id": str(technology_id)} if technology_id is not None else {}
        total = await self.versions.count_documents(query)
        rows = await self.versions.find(query).sort(
            [("technology_id", ASCENDING), ("version_key", ASCENDING), ("_id", ASCENDING)]
        ).skip(skip).limit(limit).to_list(length=limit)
        return TechnologyVersionPage(items=[self._version(doc) for doc in rows],
                                     total=total, skip=skip, limit=limit)

    async def ensure_links(
        self, technology_ids: list[UUID], version_ids: list[UUID],
    ) -> None:
        """Protect both foreign keys and forbid a generic + precise double link."""
        if technology_ids:
            keys = [str(item) for item in technology_ids]
            if await self.technologies.count_documents({"_id": {"$in": keys}}) != len(keys):
                raise UnknownTechnologyError
        if version_ids:
            keys = [str(item) for item in version_ids]
            rows = await self.versions.find({"_id": {"$in": keys}}).to_list(
                length=len(keys),
            )
            if len(rows) != len(keys):
                raise UnknownTechnologyVersionError
            if set(str(item) for item in technology_ids) & {
                row["technology_id"] for row in rows
            }:
                raise DuplicateTechnologyAssociationError
