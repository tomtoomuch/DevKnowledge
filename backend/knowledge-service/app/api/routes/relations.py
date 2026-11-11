"""Relationship read/write endpoints, exposed only behind the Express Gateway."""
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from pymongo.errors import ConnectionFailure, DuplicateKeyError

from app.api.routes.knowledges import expected_revision
from app.auth.local import requester_identity, require
from app.repositories.relation_repository import MongoRelationRepository
from app.schemas.relations import (
    RelationCreate, RelationPage, RelationRead, RelationTypeRead, RelationUpdate,
)
from app.services.knowledge_service import RequesterIdentity


router = APIRouter(tags=["Knowledge Relations"])
Requester = Annotated[RequesterIdentity, Depends(requester_identity)]
Revision = Annotated[int, Depends(expected_revision)]


def relation_repository(request: Request) -> MongoRelationRepository:
    database = getattr(request.app.state, "mongodb_database", None)
    if database is None:
        raise ConnectionFailure("MongoDB is not initialized")
    return MongoRelationRepository(database)


Repo = Annotated[MongoRelationRepository, Depends(relation_repository)]


def etag(item: RelationRead, response: Response) -> RelationRead:
    response.headers["ETag"] = f'"{item.revision}"'
    response.headers["Cache-Control"] = "no-store"
    return item


@router.get("/api/v1/relation-types", response_model=list[RelationTypeRead])
async def list_relation_types(repo: Repo, requester: Requester) -> list[RelationTypeRead]:
    require(requester, "knowledge.read")
    return await repo.list_types()


@router.get("/api/v1/knowledge-relations", response_model=RelationPage)
async def list_relations(
    repo: Repo, requester: Requester, knowledge_id: UUID,
    skip: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> RelationPage:
    require(requester, "knowledge.read")
    return await repo.list(knowledge_id=knowledge_id, skip=skip, limit=limit)


@router.post("/api/v1/knowledge-relations", response_model=RelationRead,
             status_code=status.HTTP_201_CREATED)
async def create_relation(
    payload: RelationCreate, response: Response, repo: Repo, requester: Requester,
) -> RelationRead:
    require(requester, "knowledge.create")
    try:
        return etag(await repo.create(payload), response)
    except DuplicateKeyError:
        raise HTTPException(409, "Relationship already exists") from None


@router.get("/api/v1/knowledge-relations/{relation_id}", response_model=RelationRead)
async def get_relation(
    relation_id: UUID, response: Response, repo: Repo, requester: Requester,
) -> RelationRead:
    require(requester, "knowledge.read")
    item = await repo.get(relation_id)
    if item is None:
        raise HTTPException(404, "Relation not found")
    return etag(item, response)


@router.patch("/api/v1/knowledge-relations/{relation_id}", response_model=RelationRead)
async def update_relation(
    relation_id: UUID, payload: RelationUpdate, response: Response,
    revision: Revision, repo: Repo, requester: Requester,
) -> RelationRead:
    require(requester, "knowledge.update")
    return etag(await repo.update(relation_id, payload, revision), response)


@router.delete("/api/v1/knowledge-relations/{relation_id}",
               status_code=status.HTTP_204_NO_CONTENT)
async def delete_relation(
    relation_id: UUID, revision: Revision, repo: Repo, requester: Requester,
) -> Response:
    require(requester, "knowledge.delete")
    await repo.delete(relation_id, revision)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
