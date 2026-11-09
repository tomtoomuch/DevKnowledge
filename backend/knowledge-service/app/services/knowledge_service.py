"""Knowledge rules, independent of HTTP and of the MongoDB driver."""

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol
from uuid import UUID, uuid4

from app.schemas.knowledge import KnowledgeCreate, KnowledgePage, KnowledgeRead, KnowledgeUpdate


@dataclass(frozen=True)
class RequesterIdentity:
    """Trusted identity adapter for future authentication; anonymous for now."""

    user_id: UUID | None = None


class KnowledgeRepository(Protocol):
    async def create(self, item: dict) -> dict: ...
    async def get(self, knowledge_id: UUID) -> dict | None: ...
    async def list(self, *, skip: int, limit: int, knowledge_type: str | None,
                   status: str | None, q: str | None, is_favorite: bool | None) -> tuple[list[dict], int]: ...
    async def update(self, knowledge_id: UUID, changes: dict, expected_revision: int) -> dict | None: ...
    async def soft_delete(self, knowledge_id: UUID, deleted_at: datetime, expected_revision: int) -> bool: ...


class KnowledgeNotFound(Exception):
    pass


class KnowledgeConflict(Exception):
    pass


def utc_now() -> datetime:
    # BSON dates have millisecond precision: keep API and stored values identical.
    now = datetime.now(UTC)
    return now.replace(microsecond=(now.microsecond // 1000) * 1000)


class KnowledgeService:
    def __init__(self, repository: KnowledgeRepository):
        self.repository = repository

    async def create(self, payload: KnowledgeCreate, requester: RequesterIdentity) -> KnowledgeRead:
        now = utc_now()
        item = payload.model_dump()
        item["knowledge_type"] = payload.knowledge_type.value
        item.update(
            knowledge_id=uuid4(), created_at=now, updated_at=now,
            validated_at=None, created_by_user_id=requester.user_id, deleted_at=None, revision=1,
        )
        return KnowledgeRead.model_validate(await self.repository.create(item))

    async def get(self, knowledge_id: UUID) -> KnowledgeRead:
        item = await self.repository.get(knowledge_id)
        if item is None:
            raise KnowledgeNotFound
        return KnowledgeRead.model_validate(item)

    async def list(self, *, skip: int = 0, limit: int = 20,
                   knowledge_type: str | None = None, status: str | None = None,
                   q: str | None = None, is_favorite: bool | None = None) -> KnowledgePage:
        items, total = await self.repository.list(
            skip=skip, limit=limit, knowledge_type=knowledge_type, status=status,
            q=q, is_favorite=is_favorite,
        )
        return KnowledgePage(items=items, total=total, skip=skip, limit=limit)

    async def update(self, knowledge_id: UUID, payload: KnowledgeUpdate, expected_revision: int = 0) -> KnowledgeRead:
        changes = payload.model_dump(exclude_unset=True)
        if payload.knowledge_type is not None:
            changes["knowledge_type"] = payload.knowledge_type.value
        changes["updated_at"] = utc_now()
        item = await self.repository.update(knowledge_id, changes, expected_revision)
        if item is None:
            await self._raise_write_failure(knowledge_id)
        return KnowledgeRead.model_validate(item)

    async def _raise_write_failure(self, knowledge_id: UUID) -> None:
        if await self.repository.get(knowledge_id) is None:
            raise KnowledgeNotFound
        raise KnowledgeConflict

    async def delete(self, knowledge_id: UUID, expected_revision: int = 0) -> None:
        if not await self.repository.soft_delete(knowledge_id, utc_now(), expected_revision):
            await self._raise_write_failure(knowledge_id)
