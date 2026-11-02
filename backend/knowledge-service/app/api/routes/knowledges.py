"""HTTP transport and injectable dependencies for the knowledge CRUD."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, Response, status
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


@router.post("", response_model=KnowledgeRead, status_code=status.HTTP_201_CREATED,
             responses={503: {"description": "MongoDB unavailable"}})
async def create_knowledge(payload: KnowledgeCreate, service: Service,
                           requester: Requester) -> KnowledgeRead:
    return await service.create(payload, requester)


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
async def get_knowledge(knowledge_id: UUID, service: Service) -> KnowledgeRead:
    return await service.get(knowledge_id)


@router.patch("/{knowledge_id}", response_model=KnowledgeRead,
              responses={404: {"description": "Knowledge not found"},
                         503: {"description": "MongoDB unavailable"}})
async def update_knowledge(knowledge_id: UUID, payload: KnowledgeUpdate,
                           service: Service) -> KnowledgeRead:
    return await service.update(knowledge_id, payload)


@router.delete("/{knowledge_id}", status_code=status.HTTP_204_NO_CONTENT,
               responses={404: {"description": "Knowledge not found"},
                          503: {"description": "MongoDB unavailable"}})
async def delete_knowledge(knowledge_id: UUID, service: Service) -> Response:
    await service.delete(knowledge_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
