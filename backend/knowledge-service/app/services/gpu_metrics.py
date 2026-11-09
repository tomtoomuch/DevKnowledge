"""Optional GPU telemetry from a private in-Compose collector.

No Docker socket, arbitrary host URL, subprocess or GPU device is available to KMS.
The only allowed telemetry peer is the static local Compose service `gpu-monitor`.
"""
import asyncio
import json
import logging
import os
from http.client import HTTPConnection, HTTPException as HTTPClientException

logger = logging.getLogger(__name__)
MAX_RESPONSE_BYTES = 8192
GPU_HOST = "gpu-monitor"
GPU_PORT = 9109


def _snapshot(status: str, detail: str, devices=None) -> dict:
    return {"status": status, "detail": detail, "devices": devices if devices is not None else []}


def _metric(value, minimum: float, maximum: float):
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("Invalid metric type")
    value = float(value)
    if not minimum <= value <= maximum:
        raise ValueError("Metric outside allowed range")
    return value


def _sanitize(payload: dict) -> dict:
    if not isinstance(payload, dict) or payload.get("status") != "ok":
        return _snapshot("unavailable", "Le collecteur GPU ne fournit pas de mesures.")
    raw = payload.get("devices")
    if not isinstance(raw, list) or not 1 <= len(raw) <= 16:
        return _snapshot("unavailable", "Aucun GPU mesurable n'a été détecté.")
    devices = []
    indices = set()
    for item in raw:
        if not isinstance(item, dict):
            raise ValueError("Invalid device")
        index, name = item.get("index"), item.get("name")
        if isinstance(index, bool) or not isinstance(index, int) or not 0 <= index <= 128 or index in indices:
            raise ValueError("Invalid GPU index")
        if not isinstance(name, str) or not 1 <= len(name) <= 120:
            raise ValueError("Invalid GPU name")
        indices.add(index)
        used = _metric(item.get("memory_used_mib"), 0, 1048576)
        total = _metric(item.get("memory_total_mib"), 0, 1048576)
        if used is not None and total is not None and used > total:
            raise ValueError("Invalid GPU memory counters")
        devices.append({
            "index": index,
            "name": name,
            "utilization_pct": _metric(item.get("utilization_pct"), 0, 100),
            "memory_used_mib": used,
            "memory_total_mib": total,
            "temperature_c": _metric(item.get("temperature_c"), -40, 150),
        })
    return _snapshot("healthy", "Mesures GPU disponibles.", devices)


def _fetch_gpu_metrics() -> dict:
    connection = HTTPConnection(GPU_HOST, GPU_PORT, timeout=2)
    try:
        connection.request("GET", "/metrics", headers={"Accept": "application/json", "Connection": "close"})
        response = connection.getresponse()
        if response.status != 200:
            return _snapshot("unavailable", "Le collecteur GPU ne répond pas correctement.")
        raw = response.read(MAX_RESPONSE_BYTES + 1)
        if len(raw) > MAX_RESPONSE_BYTES:
            return _snapshot("unavailable", "Réponse du collecteur GPU invalide.")
        return _sanitize(json.loads(raw))
    except (OSError, TimeoutError, ValueError, HTTPClientException):
        logger.info("GPU telemetry collector unavailable or returned invalid data")
        return _snapshot("unavailable", "Le collecteur GPU est inaccessible ou les mesures sont invalides.")
    finally:
        connection.close()


async def read_gpu_metrics() -> dict:
    if os.getenv("GPU_MONITOR_ENABLED", "false").strip().lower() not in {"true", "1", "yes"}:
        return _snapshot("disabled", "Collecte GPU facultative non configurée.")
    return await asyncio.to_thread(_fetch_gpu_metrics)
