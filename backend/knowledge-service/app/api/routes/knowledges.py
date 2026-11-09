"""HTTP transport and injectable dependencies for the knowledge CRUD."""

from typing import Annotated
import re
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, Response, status
from pymongo.errors import ConnectionFailure

from app.repositories.knowledge_repository import MongoKnowledgeRepository
from app.schemas.knowledge import (
    KnowledgeCreate, KnowledgePage, KnowledgeRead, KnowledgeType, KnowledgeUpdate, Status,
)
from app.services.knowledge_service import KnowledgeService, RequesterIdentity


router = APIRouter(prefix="/api/v1/knowledges", tags=["Knowledges"])


def get_knowledge_service(request: Request) -> KnowledgeService:
    database = getattr(request.app.state, "mongodb_database", None)
    if database is None:
        raise ConnectionFailure("MongoDB is not initialized")
    return KnowledgeService(MongoKnowledgeRepository(database))


def get_requester_identity() -> RequesterIdentity:
    # No headers or request data are treated as authenticated identity.
    return RequesterIdentity()


Service = Annotated[KnowledgeService, Depends(get_knowledge_service)]
Requester = Annotated[RequesterIdentity, Depends(get_requester_identity)]


def expected_revision(if_match: Annotated[list[str] | None, Header()] = None) -> int:
    if if_match is None:
        raise HTTPException(428, "If-Match is required; read the resource first")
    if len(if_match) != 1 or not re.fullmatch(r'"(0|[1-9][0-9]{0,18})"', if_match[0]):
        raise HTTPException(400, 'If-Match must contain one quoted revision number')
    revision = int(if_match[0][1:-1])
    if revision >= 2**63 - 1:
        raise HTTPException(400, "Revision is out of range")
    return revision


Revision = Annotated[int, Depends(expected_revision)]
WRITE_ERRORS = {404: {"description": "Knowledge not found"},
                400: {"description": "Invalid If-Match"},
                412: {"description": "Revision changed"},
                428: {"description": "If-Match required"},
                503: {"description": "MongoDB unavailable"}}


def with_etag(item: KnowledgeRead, response: Response) -> KnowledgeRead:
    response.headers["ETag"] = f'"{item.revision}"'
    response.headers["Cache-Control"] = "no-store"
    return item


@router.post("", response_model=KnowledgeRead, status_code=status.HTTP_201_CREATED,
             responses={503: {"description": "MongoDB unavailable"}})
async def create_knowledge(payload: KnowledgeCreate, response: Response, service: Service,
                           requester: Requester) -> KnowledgeRead:
    return with_etag(await service.create(payload, requester), response)


@router.get("", response_model=KnowledgePage,
            responses={503: {"description": "MongoDB unavailable"}})
async def list_knowledges(
    service: Service,
    skip: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    knowledge_type: KnowledgeType | None = None,
    status: Annotated[Status | None, Query()] = None,
) -> KnowledgePage:
    return await service.list(skip=skip, limit=limit, knowledge_type=knowledge_type, status=status)


@router.get("/{knowledge_id}", response_model=KnowledgeRead,
            responses={404: {"description": "Knowledge not found"},
                       503: {"description": "MongoDB unavailable"}})
async def get_knowledge(knowledge_id: UUID, response: Response, service: Service) -> KnowledgeRead:
    return with_etag(await service.get(knowledge_id), response)


@router.patch("/{knowledge_id}", response_model=KnowledgeRead,
              responses=WRITE_ERRORS)
async def update_knowledge(knowledge_id: UUID, payload: KnowledgeUpdate,
                           response: Response, service: Service, revision: Revision) -> KnowledgeRead:
    return with_etag(await service.update(knowledge_id, payload, revision), response)


@router.delete("/{knowledge_id}", status_code=status.HTTP_204_NO_CONTENT,
               responses=WRITE_ERRORS)
async def delete_knowledge(knowledge_id: UUID, service: Service, revision: Revision) -> Response:
    await service.delete(knowledge_id, revision)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
