import os
import asyncio

from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from starlette.responses import Response
from pymongo import AsyncMongoClient
from pymongo.errors import PyMongoError

# Configuration MongoDB
MONGODB_HOST = os.getenv("MONGODB_HOST", "localhost")
MONGODB_PORT = int(os.getenv("MONGODB_PORT", "27017"))
MONGODB_DATABASE = os.getenv("MONGODB_DATABASE", "devknowledge")
MONGODB_USERNAME = os.getenv("MONGODB_USERNAME")
MONGODB_PASSWORD = os.getenv("MONGODB_PASSWORD")
MONGODB_AUTH_SOURCE = os.getenv(
    "MONGODB_AUTH_SOURCE",
    MONGODB_DATABASE,
)

MONGODB_MAX_ATTEMPTS = 5
MONGODB_RETRY_DELAY_SECONDS = 2

mongodb_configured = bool(MONGODB_USERNAME and MONGODB_PASSWORD)
mongodb_options = {
    "host": MONGODB_HOST,
    "port": MONGODB_PORT,
    "serverSelectionTimeoutMS": 3000,
}

@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    # Initialisation DB
    if not mongodb_configured:
        raise RuntimeError(
            "Configuration MongoDB incomplète : "
            "MONGODB_USERNAME et MONGODB_PASSWORD sont requis."
        )

    if mongodb_configured:
        mongodb_options.update(
            username=MONGODB_USERNAME,
            password=MONGODB_PASSWORD,
            authSource=MONGODB_AUTH_SOURCE,
        )

    client = AsyncMongoClient(**mongodb_options)

    app.state.mongodb_client = client
    app.state.mongodb_database = client[MONGODB_DATABASE]

    try:
        for attempt in range(1, MONGODB_MAX_ATTEMPTS +1):
            try:
                await client.admin.command("ping")
                print("Connexion MongoDB établie.")
                break

            except PyMongoError as exc:
                if attempt == MONGODB_MAX_ATTEMPTS:
                    raise RuntimeError(
                        "MongoDB reste inaccessible après "
                        f"{MONGODB_MAX_ATTEMPTS} tentatives."
                    ) from exc

            print(
                f"MongoDB indisponible "
                f"(tentative {attempt}/{MONGODB_MAX_ATTEMPTS}). "
                "Nouvel essai dans "
                f"{MONGODB_RETRY_DELAY_SECONDS} secondes."
            )
            await asyncio.sleep(MONGODB_RETRY_DELAY_SECONDS)

        yield

    finally:
        await client.close()
        print("Connexion MongoDB fermée.")


app = FastAPI(
    title="Knowledge Management System",
    description="Service local de gestion des connaissances de DevKnowledge/BrainBlox",
    version="0.1.0",
    lifespan=lifespan,
)

@app.get("/health", tags=["Health"])
def health_check() -> dict[str, str]:
    return {
        "status":"ok",
        "service":"api-kms"
    }

@app.get(
        "/health/ready",
        tags=["Health"],
        response_model=None,
)
async def mongodb_ready_check(request: Request) -> JSONResponse:
    # Vérifie l'accès à MongoDB
    client = getattr(request.app.state, "mongodb_client", None)

    if client is None:
        return JSONResponse(
            status_code=503,
            content={
                "status": "error",
                "service": "api-kms",
                "dependency": "mongodb",
                "reason": "mongodb n'est pas initialisée.",
            },
        )

    try:
        await client.admin.command("ping")
    
    except PyMongoError:
        return JSONResponse(
            status_code=503,
            content={
                "status": "error",
                "service": "api-kms",
                "dependency": "mongodb",
                "reason": "Connection failed",
            },
        )

    return JSONResponse(
        status_code=200,
        content={
            "status": "ok",
            "service": "api-kms",
            "dependency": "mongodb",
        },
    )