"""Read-only local service-health snapshot; callable by the browser only through Gateway."""

from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response
from pymongo.errors import PyMongoError

from app.auth.local import requester_identity, require
from app.services.knowledge_service import RequesterIdentity

router = APIRouter(prefix="/api/v1", tags=["Monitoring"])


@router.get("/monitoring/services")
async def list_service_health(
    request: Request,
    response: Response,
    requester: Annotated[RequesterIdentity, Depends(requester_identity)],
):
    # The existing local-session and RBAC mechanism applies to monitoring too.
    require(requester, "knowledge.read")
    response.headers["Cache-Control"] = "no-store"
    checked_at = datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    client = getattr(request.app.state, "mongodb_client", None)
    mongo_status = "unknown"
    mongo_detail = "Le contrôle MongoDB n'a pas pu être effectué."
    if client is not None:
        try:
            await client.admin.command("ping")
        except PyMongoError:
            # Never include driver errors, hostnames, credentials or internal URLs.
            mongo_status = "unavailable"
            mongo_detail = "MongoDB ne répond pas au contrôle de disponibilité."
        else:
            mongo_status = "healthy"
            mongo_detail = "Le ping MongoDB a réussi."

    kms_status = "healthy" if mongo_status == "healthy" else "degraded"
    kms_detail = (
        "L'API répond et son stockage est disponible."
        if kms_status == "healthy" else
        "L'API répond, mais la disponibilité du stockage n'est pas confirmée."
    )
    return {
        "checked_at": checked_at,
        "services": [
            {
                "id": "api-gateway",
                "name": "API Gateway",
                "description": "Point d'entrée HTTP unique",
                "status": "healthy",
                "detail": "La requête est passée par la Gateway.",
            },
            {
                "id": "api-kms",
                "name": "Knowledge Service",
                "description": "API FastAPI et gestion des connaissances",
                "status": kms_status,
                "detail": kms_detail,
            },
            {
                "id": "mongodb",
                "name": "MongoDB",
                "description": "Base documentaire locale",
                "status": mongo_status,
                "detail": mongo_detail,
            },
        ],
    }
