"""Protected, opt-in RNCP API; all browser paths must traverse Gateway."""
import asyncio
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict, Field
from pymongo.errors import PyMongoError
import psycopg

from app.auth.local import requester_identity, require
from app.rncp.migrate import connection_string
from app.rncp.repository import (
    RncpRepository, MissingCompetency, InvalidEvidenceType, DuplicateKnowledgeLink,
)
from app.services.knowledge_service import RequesterIdentity

router = APIRouter(prefix="/api/v1/rncp", tags=["RNCP"])
Requester = Annotated[RequesterIdentity, Depends(requester_identity)]


class EvidenceCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str = Field(min_length=1, max_length=255)
    evidence_type_code: str = Field(min_length=2, max_length=50, pattern=r"^[A-Z][A-Z0-9_]*$")
    repository_url: str | None = Field(None, max_length=2000)


class KnowledgeLinkCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    knowledge_id: UUID
    confidence_score: float | None = Field(None, ge=0, le=1)
    mapping_rationale: str | None = Field(None, max_length=4000)


def get_rncp_repository() -> RncpRepository:
    try:
        return RncpRepository(connection_string())
    except (KeyError, ValueError) as exc:
        raise HTTPException(503, "RNCP storage not configured") from exc


Repo = Annotated[RncpRepository, Depends(get_rncp_repository)]


@router.get("/frameworks/{code}/versions/{version}")
def get_framework(code: str, version: str, repo: Repo, requester: Requester):
    require(requester, "knowledge.read")
    try:
        value = repo.overview(code, version)
    except psycopg.OperationalError as exc:
        raise HTTPException(503, "RNCP database unavailable") from exc
    if value is None:
        raise HTTPException(404, "Framework version not found")
    return value


@router.get("/competencies/{competency_id}/evidence")
def list_evidence(competency_id: UUID, repo: Repo, requester: Requester):
    require(requester, "knowledge.read")
    try:
        value = repo.competency_evidence(competency_id)
    except psycopg.OperationalError as exc:
        raise HTTPException(503, "RNCP database unavailable") from exc
    if value is None:
        raise HTTPException(404, "Competency not found")
    return {"competency_id": str(competency_id), "evidence": value}


@router.post("/competencies/{competency_id}/evidence", status_code=status.HTTP_201_CREATED)
def add_evidence(competency_id: UUID, payload: EvidenceCreate, repo: Repo, requester: Requester):
    require(requester, "knowledge.create")
    if requester.user_id is None:
        raise HTTPException(401, "Authenticated user ID required")
    try:
        return repo.create_evidence(
            competency_id, payload.title.strip(), payload.evidence_type_code,
            requester.user_id, payload.repository_url,
        )
    except MissingCompetency as exc:
        raise HTTPException(404, "Competency not found") from exc
    except InvalidEvidenceType as exc:
        raise HTTPException(422, "Unknown evidence type") from exc
    except psycopg.OperationalError as exc:
        raise HTTPException(503, "RNCP database unavailable") from exc


@router.post("/competencies/{competency_id}/knowledge-links",
             status_code=status.HTTP_201_CREATED)
async def add_knowledge_link(competency_id: UUID, payload: KnowledgeLinkCreate,
                             request: Request, repo: Repo, requester: Requester):
    require(requester, "knowledge.create")
    if requester.user_id is None:
        raise HTTPException(401, "Authenticated user ID required")
    db = getattr(request.app.state, "mongodb_database", None)
    if db is None:
        raise HTTPException(503, "MongoDB reference validation unavailable")
    try:
        active = await db["knowledge_items"].find_one(
            {"_id": str(payload.knowledge_id), "deleted_at": None},
            projection={"_id": 1},
        )
    except PyMongoError as exc:
        raise HTTPException(503, "MongoDB reference validation unavailable") from exc
    if active is None:
        raise HTTPException(422, "Active knowledge not found in MongoDB")
    # A MongoDB delete after validation may race this SQL insert.
    # Cross-store outbox/reconciliation is needed before production activation.
    try:
        return await asyncio.to_thread(
            repo.create_knowledge_link, competency_id, payload.knowledge_id,
            requester.user_id, payload.confidence_score, payload.mapping_rationale,
        )
    except MissingCompetency as exc:
        raise HTTPException(404, "Competency not found") from exc
    except DuplicateKnowledgeLink as exc:
        raise HTTPException(409, "Knowledge already linked to competency") from exc
    except psycopg.OperationalError as exc:
        raise HTTPException(503, "RNCP database unavailable") from exc
