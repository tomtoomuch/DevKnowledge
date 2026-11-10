import logging

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pymongo.errors import PyMongoError

from app.api.routes.knowledges import router
from app.api.routes.auth import router as identity_router
from app.auth.user_management import (
    UserNotFound, UserRevisionConflict, LastAdminError, SelfLockoutError,
    AdminMutationBusy,
)
from app.api.routes.knowledge_types import router as knowledge_types_router
from app.api.routes.tags import router as tags_router
from app.api.routes.technologies import router as technologies_router
from app.api.routes.monitoring import router as monitoring_router
from app.db.mongodb import lifespan
from app.repositories.tag_repository import UnknownTagError
from app.repositories.technology_repository import (
    UnknownTechnologyError, UnknownTechnologyVersionError,
    DuplicateTechnologyAssociationError,
)
from app.services.knowledge_service import (
    KnowledgeNotFound, KnowledgeConflict, KnowledgeDetailsValidationError,
)


logger = logging.getLogger(__name__)
app = FastAPI(
    title="Knowledge Management System",
    description="Service local de gestion des connaissances de DevKnowledge/BrainBlox",
    version="0.2.0",
    lifespan=lifespan,
)
app.include_router(router)
app.include_router(identity_router)
app.include_router(knowledge_types_router)
app.include_router(tags_router)
app.include_router(technologies_router)
app.include_router(monitoring_router)


@app.exception_handler(UserNotFound)
async def user_not_found(request: Request, exc: UserNotFound) -> JSONResponse:
    return JSONResponse(status_code=404, content={"detail": "User not found"})


@app.exception_handler(UserRevisionConflict)
async def user_conflict(request: Request, exc: UserRevisionConflict) -> JSONResponse:
    return JSONResponse(status_code=412, content={"detail": "User revision changed; reload"})


@app.exception_handler(LastAdminError)
@app.exception_handler(SelfLockoutError)
@app.exception_handler(AdminMutationBusy)
async def admin_lockout(request: Request, exc: Exception) -> JSONResponse:
    return JSONResponse(status_code=409, content={"detail": "Cannot remove the current or last active administrator"})


@app.exception_handler(UnknownTechnologyError)
@app.exception_handler(UnknownTechnologyVersionError)
@app.exception_handler(DuplicateTechnologyAssociationError)
async def invalid_technology_association(request: Request, exc: Exception) -> JSONResponse:
    return JSONResponse(status_code=422, content={
        "detail": "Unknown technology/version identifier or duplicate generic/version association",
    })


@app.exception_handler(UnknownTagError)
async def unknown_tag(request: Request, exc: UnknownTagError) -> JSONResponse:
    return JSONResponse(status_code=422, content={"detail": "Some tag identifiers do not exist"})


@app.exception_handler(KnowledgeConflict)
async def knowledge_conflict(request: Request, exc: KnowledgeConflict) -> JSONResponse:
    return JSONResponse(status_code=412, content={"detail": "Knowledge revision changed; reload before retrying"})


@app.exception_handler(KnowledgeDetailsValidationError)
async def invalid_knowledge_details(request: Request, exc: KnowledgeDetailsValidationError) -> JSONResponse:
    return JSONResponse(status_code=422, content={"detail": "Invalid specialization for knowledge type"})


@app.exception_handler(KnowledgeNotFound)
async def knowledge_not_found(request: Request, exc: KnowledgeNotFound) -> JSONResponse:
    return JSONResponse(status_code=404, content={"detail": "Knowledge not found"})


@app.exception_handler(PyMongoError)
async def mongodb_unavailable(request: Request, exc: PyMongoError) -> JSONResponse:
    logger.warning("MongoDB request failure (%s)", type(exc).__name__)
    return JSONResponse(status_code=503, content={"detail": "MongoDB unavailable"})


@app.get("/health", tags=["Health"])
def health_check() -> dict[str, str]:
    return {"status": "ok", "service": "api-kms"}


@app.get("/health/ready", tags=["Health"], response_model=None)
async def mongodb_ready_check(request: Request) -> JSONResponse:
    client = getattr(request.app.state, "mongodb_client", None)
    if client is None:
        return JSONResponse(status_code=503, content={
            "status": "error", "service": "api-kms", "dependency": "mongodb",
            "reason": "mongodb n'est pas initialisée.",
        })
    try:
        await client.admin.command("ping")
    except PyMongoError as exc:
        logger.warning("MongoDB readiness failure (%s)", type(exc).__name__)
        return JSONResponse(status_code=503, content={
            "status": "error", "service": "api-kms", "dependency": "mongodb",
            "reason": "Connection failed",
        })
    return JSONResponse(status_code=200, content={
        "status": "ok", "service": "api-kms", "dependency": "mongodb",
    })
