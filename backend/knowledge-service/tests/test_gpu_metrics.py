"""Optional GPU metrics: fixed local peer, strict validation, graceful absence."""

import json
from unittest.mock import AsyncMock

import pytest
from app.services import gpu_metrics


def test_gpu_disabled_without_sidecar(monkeypatch):
    monkeypatch.delenv("GPU_MONITOR_ENABLED", raising=False)
    assert gpu_metrics._fetch_gpu_metrics is not None
    result = __import__("asyncio").run(gpu_metrics.read_gpu_metrics())
    assert result == {
        "status": "disabled", "detail": "Collecte GPU facultative non configurée.", "devices": [],
    }


def test_valid_multi_gpu_and_nullable_sensors():
    result = gpu_metrics._sanitize({"status": "ok", "devices": [
        {"index": 0, "name": "RTX 4090", "utilization_pct": 64,
         "memory_used_mib": 1024, "memory_total_mib": 24576, "temperature_c": 58},
        {"index": 1, "name": "NVIDIA second GPU", "utilization_pct": None,
         "memory_used_mib": None, "memory_total_mib": None, "temperature_c": None},
    ]})
    assert result["status"] == "healthy"
    assert len(result["devices"]) == 2
    assert result["devices"][0]["memory_total_mib"] == 24576
    assert result["devices"][1]["temperature_c"] is None


@pytest.mark.parametrize("device", [
    {"index": "0", "name": "bad"},
    {"index": 0, "name": "bad", "utilization_pct": 110},
    {"index": 0, "name": "bad", "memory_used_mib": 900, "memory_total_mib": 800},
    {"index": 0, "name": "bad", "temperature_c": float("nan")},
    {"index": 0, "name": ""},
])
def test_invalid_gpu_telemetry_is_rejected(device):
    with pytest.raises(ValueError):
        gpu_metrics._sanitize({"status": "ok", "devices": [device]})


def test_no_data_is_not_healthy():
    assert gpu_metrics._sanitize({"status": "ok", "devices": []})["status"] == "unavailable"
    assert gpu_metrics._sanitize({"status": "unavailable", "devices": []})["status"] == "unavailable"


def test_collector_failures_do_not_disclose_internal_details(monkeypatch):
    class BadConnection:
        def __init__(self, host, port, timeout):
            assert (host, port, timeout) == ("gpu-monitor", 9109, 2)
        def request(self, *args, **kwargs):
            raise OSError("private-http://user:password@gpu-monitor")
        def close(self):
            pass
    monkeypatch.setattr(gpu_metrics, "HTTPConnection", BadConnection)
    snapshot = gpu_metrics._fetch_gpu_metrics()
    assert snapshot["status"] == "unavailable"
    assert "password" not in str(snapshot)
    assert "gpu-monitor" not in str(snapshot)


def test_collect_success_with_fixed_route_and_bounded_response(monkeypatch):
    payload = json.dumps({"status": "ok", "devices": [
        {"index": 0, "name": "Demo", "utilization_pct": 42,
         "memory_total_mib": 2000, "memory_used_mib": 500, "temperature_c": 60},
    ]}).encode()

    class Response:
        status = 200
        def read(self, maximum):
            assert maximum == gpu_metrics.MAX_RESPONSE_BYTES + 1
            return payload

    class Connection:
        def __init__(self, host, port, timeout):
            assert (host, port, timeout) == ("gpu-monitor", 9109, 2)
        def request(self, method, path, headers):
            assert (method, path) == ("GET", "/metrics")
        def getresponse(self):
            return Response()
        def close(self):
            pass
    monkeypatch.setattr(gpu_metrics, "HTTPConnection", Connection)
    result = gpu_metrics._fetch_gpu_metrics()
    assert result["status"] == "healthy"
    assert result["devices"][0]["utilization_pct"] == 42


def test_collection_does_not_block_event_loop_when_enabled(monkeypatch):
    monkeypatch.setenv("GPU_MONITOR_ENABLED", "true")
    monkeypatch.setattr(gpu_metrics, "_fetch_gpu_metrics", lambda: {"status": "unavailable", "devices": []})
    result = __import__("asyncio").run(gpu_metrics.read_gpu_metrics())
    assert result["status"] == "unavailable"
