"""Monitoring authorization and unprivileged supervisor delegation."""
from unittest.mock import AsyncMock
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from app.auth.local import requester_identity
from app.api.routes import monitoring as monitoring_route
from app.main import app
from app.services.supervisor_client import fallback
from app.services.knowledge_service import RequesterIdentity

ENDPOINT = "/api/v1/monitoring/services"


@pytest.fixture
def client():
    app.dependency_overrides[requester_identity] = lambda: RequesterIdentity(
        permissions=frozenset({"knowledge.read"}),
    )
    test_client = TestClient(app)
    try:
        yield test_client
    finally:
        test_client.close()
        app.dependency_overrides.pop(requester_identity, None)


def test_snapshot_requires_permission_and_is_never_cached(client, monkeypatch):
    sample = fallback()
    probe = AsyncMock(return_value=sample)
    monkeypatch.setattr(monitoring_route, "read_snapshot", probe)
    response = client.get(ENDPOINT)
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert response.json() == sample
    probe.assert_awaited_once()
    app.dependency_overrides[requester_identity] = lambda: RequesterIdentity(
        permissions=frozenset(),
    )
    assert client.get(ENDPOINT).status_code == 403
    probe.assert_awaited_once()


def test_snapshot_rejects_unauthenticated_request(client, monkeypatch):
    probe = AsyncMock(return_value=fallback())
    monkeypatch.setattr(monitoring_route, "read_snapshot", probe)
    def forbidden():
        raise HTTPException(status_code=401, detail="Authentication required")
    app.dependency_overrides[requester_identity] = forbidden
    assert client.get(ENDPOINT).status_code == 401
    probe.assert_not_awaited()
