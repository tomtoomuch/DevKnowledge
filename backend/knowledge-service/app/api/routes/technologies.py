"""Technology and version reference catalogs (immutable once created)."""
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pymongo.errors import ConnectionFailure, DuplicateKeyError

from app.auth.local import requester_identity, require
from app.repositories.technology_repository import MongoTechnologyRepository, UnknownTechnologyError
from app.schemas.technologies import (
    TechnologyCreate, TechnologyRead, TechnologyPage,
    TechnologyVersionCreate, TechnologyVersionRead, TechnologyVersionPage,
)
from app.services.knowledge_service import RequesterIdentity


router = APIRouter(tags=["Technologies"])
Requester = Annotated[RequesterIdentity, Depends(requester_identity)]


def technology_repository(request: Request) -> MongoTechnologyRepository:
    database = getattr(request.app.state, "mongodb_database", None)
    if database is None:
        raise ConnectionFailure("MongoDB is not initialized")
    return MongoTechnologyRepository(database)


Catalog = Annotated[MongoTechnologyRepository, Depends(technology_repository)]


@router.get("/api/v1/technologies", response_model=TechnologyPage)
async def list_technologies(
    catalog: Catalog, requester: Requester,
    skip: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 100,
) -> TechnologyPage:
    require(requester, "knowledge.read")
    return await catalog.list_technologies(skip=skip, limit=limit)


@router.post("/api/v1/technologies", response_model=TechnologyRead,
             status_code=status.HTTP_201_CREATED)
async def create_technology(payload: TechnologyCreate, catalog: Catalog, requester: Requester) -> TechnologyRead:
    require(requester, "knowledge.create")
    try:
        return await catalog.create_technology(payload)
    except DuplicateKeyError:
        raise HTTPException(409, "A technology with that name already exists") from None


@router.get("/api/v1/technologies/{technology_id}", response_model=TechnologyRead)
async def get_technology(technology_id: UUID, catalog: Catalog, requester: Requester) -> TechnologyRead:
    require(requester, "knowledge.read")
    technology = await catalog.get_technology(technology_id)
    if technology is None:
        raise HTTPException(404, "Technology not found")
    return technology


@router.get("/api/v1/technology-versions", response_model=TechnologyVersionPage)
async def list_versions(
    catalog: Catalog, requester: Requester,
    skip: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 100,
    technology_id: UUID | None = None,
) -> TechnologyVersionPage:
    require(requester, "knowledge.read")
    return await catalog.list_versions(skip=skip, limit=limit, technology_id=technology_id)


@router.post("/api/v1/technology-versions", response_model=TechnologyVersionRead,
             status_code=status.HTTP_201_CREATED)
async def create_version(payload: TechnologyVersionCreate, catalog: Catalog,
                         requester: Requester) -> TechnologyVersionRead:
    require(requester, "knowledge.create")
    try:
        return await catalog.create_version(payload)
    except UnknownTechnologyError:
        raise HTTPException(422, "Unknown parent technology") from None
    except DuplicateKeyError:
        raise HTTPException(409, "This version already exists for the technology") from None


@router.get("/api/v1/technology-versions/{version_id}", response_model=TechnologyVersionRead)
async def get_version(version_id: UUID, catalog: Catalog, requester: Requester) -> TechnologyVersionRead:
    require(requester, "knowledge.read")
    version = await catalog.get_version(version_id)
    if version is None:
        raise HTTPException(404, "Technology version not found")
    return version
