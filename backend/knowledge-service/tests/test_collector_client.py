"""Validate the fixed, bounded and sanitized supervisor contract."""
import asyncio
import math
from unittest.mock import MagicMock

import pytest
from app.services import supervisor_client as service


def test_fallback_never_fakes_green_services():
    data = service.fallback()
    assert {x["id"]: x["status"] for x in data["services"]} == {
        "api-gateway": "unknown", "frontend": "unknown",
        "api-kms": "unknown", "mongodb": "unknown",
        "supervisor": "unavailable",
    }
    assert data["gpu"]["status"] == "unknown"


def sample():
    return {
        "checked_at": "2026-11-10T00:00:00Z",
        "services": [{"id": key, "status": "healthy"} for key in service.SERVICES],
        "gpu": {"status": "healthy", "devices": [{
            "index": 0, "name": "RTX 3070", "utilization_pct": 40,
            "memory_used_mib": 400, "memory_total_mib": 8192, "temperature_c": 42,
        }]},
    }


def test_valid_telemetry_is_sanitized():
    data = service.sanitize(sample())
    assert data["gpu"]["devices"][0]["temperature_c"] == 42
    assert len(data["services"]) == 5
    assert data["services"][0]["name"] == "API Gateway"


@pytest.mark.parametrize("value", [101, -1, float("nan"), "30", float("inf")])
def test_invalid_telemetry_rejected(value):
    data = sample()
    data["gpu"]["devices"][0]["utilization_pct"] = value
    with pytest.raises(ValueError):
        service.sanitize(data)


def test_invalid_service_list_rejected():
    data = sample()
    data["services"].append({"id": "injected", "status": "healthy"})
    with pytest.raises(ValueError):
        service.sanitize(data)
    data = sample()
    data["services"][0]["id"] = "supervisor"
    with pytest.raises(ValueError):
        service.sanitize(data)


def test_supervisor_has_fixed_url_and_bounded_body(monkeypatch):
    content = __import__("json").dumps(sample()).encode()
    class Response:
        status = 200
        def read(self, limit):
            assert limit == service.MAX_BYTES + 1
            return content
    class Connection:
        def __init__(self, host, port, timeout):
            assert (host, port, timeout) == ("supervisor", 9109, 4)
        def request(self, method, path, headers):
            assert (method, path) == ("GET", "/snapshot")
        def getresponse(self):
            return Response()
        def close(self):
            pass
    monkeypatch.setattr(service, "HTTPConnection", Connection)
    assert asyncio.run(service.read_snapshot())["gpu"]["status"] == "healthy"


def test_supervisor_error_is_sanitized(monkeypatch):
    class Connection:
        def __init__(self, *args, **kwargs):
            pass
        def request(self, *args, **kwargs):
            raise OSError("secret-host.internal:password")
        def close(self):
            pass
    monkeypatch.setattr(service, "HTTPConnection", Connection)
    result = service.fetch_snapshot()
    assert result["services"][-1]["status"] == "unavailable"
    assert "secret-host" not in str(result)
