"""Monitoring endpoint contracts without live Docker or MongoDB."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from pymongo.errors import ConnectionFailure

from app.auth.local import requester_identity
from app.main import app
from app.services.knowledge_service import RequesterIdentity

ENDPOINT = "/api/v1/monitoring/services"


@pytest.fixture
def client(monkeypatch):
    app.dependency_overrides[requester_identity] = lambda: RequesterIdentity(
        permissions=frozenset({"knowledge.read"}),
    )
    monkeypatch.setitem(app.state._state, "mongodb_client", None)
    test_client = TestClient(app)
    try:
        yield test_client
    finally:
        test_client.close()
        app.dependency_overrides.pop(requester_identity, None)


def test_missing_mongodb_client_is_unknown_and_kms_degraded(client):
    response = client.get(ENDPOINT)
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    data = response.json()
    assert data["checked_at"].endswith("Z")
    statuses = {entry["id"]: entry["status"] for entry in data["services"]}
    assert statuses == {"api-gateway": "healthy", "api-kms": "degraded", "mongodb": "unknown"}


def test_healthy_mongodb_ping(client, monkeypatch):
    command = AsyncMock()
    monkeypatch.setitem(app.state._state, "mongodb_client", SimpleNamespace(
        admin=SimpleNamespace(command=command),
    ))
    response = client.get(ENDPOINT)
    assert response.status_code == 200
    statuses = {entry["id"]: entry["status"] for entry in response.json()["services"]}
    assert statuses == {"api-gateway": "healthy", "api-kms": "healthy", "mongodb": "healthy"}
    command.assert_awaited_once_with("ping")


def test_failed_ping_is_sanitized_and_does_not_cascade_to_gateway(client, monkeypatch):
    command = AsyncMock(side_effect=ConnectionFailure("mongodb://secret:password@internal.invalid"))
    monkeypatch.setitem(app.state._state, "mongodb_client", SimpleNamespace(
        admin=SimpleNamespace(command=command),
    ))
    response = client.get(ENDPOINT)
    assert response.status_code == 200
    assert "password" not in response.text
    assert "internal.invalid" not in response.text
    statuses = {entry["id"]: entry["status"] for entry in response.json()["services"]}
    assert statuses == {"api-gateway": "healthy", "api-kms": "degraded", "mongodb": "unavailable"}


def test_monitoring_requires_read_permission(client):
    app.dependency_overrides[requester_identity] = lambda: RequesterIdentity(
        permissions=frozenset(),
    )
    assert client.get(ENDPOINT).status_code == 403


def test_monitoring_requires_session(client):
    def unauthenticated():
        raise HTTPException(status_code=401, detail="Authentication required")
    app.dependency_overrides[requester_identity] = unauthenticated
    assert client.get(ENDPOINT).status_code == 401
