"""Read-only local knowledge type catalog."""
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from pymongo.errors import ConnectionFailure

from app.auth.local import requester_identity, require
from app.repositories.knowledge_type_repository import MongoKnowledgeTypeRepository, KnowledgeTypeRead
from app.services.knowledge_service import RequesterIdentity

router = APIRouter(prefix="/api/v1/knowledge-types", tags=["Knowledge types"])
Requester = Annotated[RequesterIdentity, Depends(requester_identity)]


@router.get("", response_model=list[KnowledgeTypeRead])
async def list_types(request: Request, requester: Requester):
    require(requester, "knowledge.read")
    database = getattr(request.app.state, "mongodb_database", None)
    if database is None:
        raise ConnectionFailure("MongoDB is not initialized")
    return await MongoKnowledgeTypeRepository(database).list()
