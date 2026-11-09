"""Read/create reusable tags. Tag identities remain immutable once linked."""
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pymongo.errors import ConnectionFailure, DuplicateKeyError

from app.auth.local import requester_identity, require
from app.repositories.tag_repository import MongoTagRepository
from app.schemas.tags import TagCreate, TagPage, TagRead
from app.services.knowledge_service import RequesterIdentity


router = APIRouter(prefix="/api/v1/tags", tags=["Tags"])
Requester = Annotated[RequesterIdentity, Depends(requester_identity)]


def tag_repository(request: Request) -> MongoTagRepository:
    database = getattr(request.app.state, "mongodb_database", None)
    if database is None:
        raise ConnectionFailure("MongoDB is not initialized")
    return MongoTagRepository(database)


TagRepo = Annotated[MongoTagRepository, Depends(tag_repository)]


@router.get("", response_model=TagPage)
async def list_tags(
    repository: TagRepo, requester: Requester,
    skip: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 100,
) -> TagPage:
    require(requester, "knowledge.read")
    return await repository.list(skip=skip, limit=limit)


@router.post("", response_model=TagRead, status_code=status.HTTP_201_CREATED)
async def create_tag(payload: TagCreate, repository: TagRepo, requester: Requester) -> TagRead:
    require(requester, "knowledge.create")
    try:
        return await repository.create(payload)
    except DuplicateKeyError:
        raise HTTPException(409, "A tag with that name already exists") from None


@router.get("/{tag_id}", response_model=TagRead)
async def get_tag(tag_id: UUID, repository: TagRepo, requester: Requester) -> TagRead:
    require(requester, "knowledge.read")
    tag = await repository.get(tag_id)
    if tag is None:
        raise HTTPException(404, "Tag not found")
    return tag
