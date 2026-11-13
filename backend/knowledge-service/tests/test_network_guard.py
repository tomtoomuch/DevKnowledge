"""Enforce service-to-service peer allowlists without exposing internal IPs."""
import asyncio
from unittest.mock import AsyncMock
from types import SimpleNamespace

from fastapi.testclient import TestClient
from app.auth import network_guard
from app.main import app


def fake_request(path, ip):
    return SimpleNamespace(
        client=SimpleNamespace(host=ip),
        url=SimpleNamespace(path=path),
    )


def test_guard_disabled_for_in_process_tests(monkeypatch):
    monkeypatch.delenv("KMS_NETWORK_GUARD", raising=False)
    assert asyncio.run(network_guard.allowed_peer(fake_request("/api/v1/knowledges", "outside"))) is True


def test_guard_denies_unexpected_peer_before_private_routes(monkeypatch):
    monkeypatch.setenv("KMS_NETWORK_GUARD", "required")
    client = TestClient(app)
    try:
        assert client.get("/api/v1/knowledges").status_code == 404
        assert client.get("/health").status_code == 404
    finally:
        client.close()


def test_kms_peer_gateway_api_and_supervisor_health(monkeypatch):
    monkeypatch.setenv("KMS_NETWORK_GUARD", "required")
    async def fake_resolve(self, name, port, family, type):
        addresses = {"api-gateway": "172.20.0.2", "supervisor": "172.20.0.4"}
        return [(2, 1, 6, "", (addresses[name], 0))]
    monkeypatch.setattr("asyncio.BaseEventLoop.getaddrinfo", fake_resolve, raising=True)
    assert asyncio.run(network_guard.allowed_peer(fake_request("/api/v1/knowledges", "172.20.0.2")))
    assert not asyncio.run(network_guard.allowed_peer(fake_request("/api/v1/knowledges", "172.20.0.4")))
    assert asyncio.run(network_guard.allowed_peer(fake_request("/health", "172.20.0.4")))
    assert asyncio.run(network_guard.allowed_peer(fake_request("/health", "127.0.0.1")))
    assert not asyncio.run(network_guard.allowed_peer(fake_request("/health", "172.20.0.6")))
