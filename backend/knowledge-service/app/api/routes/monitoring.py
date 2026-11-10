"""Authenticated monitoring façade. The collector owns every probe."""

from typing import Annotated

from fastapi import APIRouter, Depends, Response
from app.auth.local import requester_identity, require
from app.services.collector_client import read_snapshot
from app.services.knowledge_service import RequesterIdentity

router = APIRouter(prefix="/api/v1", tags=["Monitoring"])


@router.get("/monitoring/services")
async def list_service_health(
    response: Response,
    requester: Annotated[RequesterIdentity, Depends(requester_identity)],
):
    require(requester, "knowledge.read")
    response.headers["Cache-Control"] = "no-store"
    return await read_snapshot()
