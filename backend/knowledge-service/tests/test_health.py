from fastapi.testclient import TestClient
from types import SimpleNamespace
from unittest.mock import AsyncMock

from pymongo.errors import ConnectionFailure

from app.main import app

client = TestClient(app)

def test_health_returns_200() -> None:
# La route doit répondre avec un statut 200
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {
        "status":"ok",
        "service":"api-kms",
    }

def test_unknown_route_returns_404() -> None:
# Une route inexistante doit répondre avec le statut 404
    response = client.get("/route-inconnue")

    assert response.status_code == 404


def test_ready_without_client_returns_503(monkeypatch):
    monkeypatch.setattr(app.state, "mongodb_client", None, raising=False)
    response = client.get("/health/ready")
    assert response.status_code == 503
    assert response.json()["dependency"] == "mongodb"


def test_ready_with_mongodb_returns_200(monkeypatch):
    command = AsyncMock()
    monkeypatch.setattr(app.state, "mongodb_client", SimpleNamespace(admin=SimpleNamespace(command=command)), raising=False)
    response = client.get("/health/ready")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "api-kms", "dependency": "mongodb"}
    command.assert_awaited_once_with("ping")


def test_ready_failure_does_not_disclose_driver_details(monkeypatch, caplog):
    command = AsyncMock(side_effect=ConnectionFailure("mongodb://secret-user:secret-pass@internal"))
    monkeypatch.setattr(app.state, "mongodb_client", SimpleNamespace(admin=SimpleNamespace(command=command)), raising=False)
    response = client.get("/health/ready")
    assert response.status_code == 503
    assert "secret" not in response.text
    assert "secret" not in caplog.text
    assert "ConnectionFailure" in caplog.text
