"""An isolated read-only API to exercise the future KMS RNCP repository.

SECURITY: Do not include this router in app.main until Gateway + Superviseur
authorization and interservice authentication are implemented and tested.
"""
import uuid

from fastapi import FastAPI, HTTPException

from .repository import RncpRepository


def create_test_app(dsn: str) -> FastAPI:
    repository = RncpRepository(dsn)
    app = FastAPI(
        title="RNCP PostgreSQL isolated integration prototype",
        docs_url=None,
        redoc_url=None,
    )

    @app.get("/health/ready")
    def ready():
        # This endpoint is only ever called through in-process TestClient.
        import psycopg
        with psycopg.connect(dsn) as conn:
            conn.execute("SELECT 1")
        return {"status": "ok", "dependency": "postgresql"}

    @app.get("/api/v1/rncp/frameworks/{code}/versions/{version}")
    def overview(code: str, version: str):
        result = repository.overview(code, version)
        if result is None:
            raise HTTPException(404, "Framework version not found")
        return result

    @app.get("/api/v1/rncp/competencies/{competency_id}/evidence")
    def evidence(competency_id: uuid.UUID):
        result = repository.competency_evidence(competency_id)
        if result is None:
            raise HTTPException(404, "Competency not found")
        return {"competency_id": str(competency_id), "evidence": result}

    return app
