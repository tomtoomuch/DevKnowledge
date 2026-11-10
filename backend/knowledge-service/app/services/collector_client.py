"""Bounded internal connection to the collector; no GPU or health probes in KMS."""

import asyncio
import json
import logging
import math
from datetime import UTC, datetime
from http.client import HTTPConnection, HTTPException as HTTPClientException

logger = logging.getLogger(__name__)
HOST, PORT, MAX_BYTES = "collector", 9109, 16384
STATES = frozenset({"healthy", "degraded", "unavailable", "unknown"})
GPU_STATES = frozenset({"healthy", "unavailable", "disabled", "unknown"})
SERVICES = {
    "api-gateway": ("API Gateway", "Point d'entrée HTTP unique"),
    "api-kms": ("Knowledge Service", "API FastAPI et gestion des connaissances"),
    "mongodb": ("MongoDB", "Base documentaire locale"),
    "collector": ("Collector", "Collecte centralisée des services et du GPU"),
}


def entry(key, status):
    name, description = SERVICES[key]
    descriptions = {
        "healthy": "Sonde de disponibilité opérationnelle.",
        "degraded": "Disponibilité partielle ou dégradée.",
        "unavailable": "La sonde ne répond pas correctement.",
        "unknown": "Aucune mesure fiable disponible.",
    }
    return {"id": key, "name": name, "description": description,
            "status": status, "detail": descriptions[status]}


def fallback():
    return {
        "checked_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "services": [entry(key, "unavailable" if key == "collector" else "unknown")
                     for key in SERVICES],
        "gpu": {"status": "unknown", "detail": "Collecte GPU non vérifiée.", "devices": []},
    }


def number(value, minimum, maximum):
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("Invalid measurement type")
    result = float(value)
    if not math.isfinite(result) or not minimum <= result <= maximum:
        raise ValueError("Invalid measurement value")
    return result


def sanitize(raw):
    if not isinstance(raw, dict):
        raise ValueError("Invalid response type")
    checked_at = raw.get("checked_at")
    if not isinstance(checked_at, str) or len(checked_at) > 40 or not checked_at.endswith("Z"):
        raise ValueError("Invalid collection timestamp")
    try:
        if datetime.fromisoformat(checked_at.replace("Z", "+00:00")).tzinfo is None:
            raise ValueError("Invalid timezone")
    except ValueError:
        raise ValueError("Invalid collection timestamp") from None
    services = raw.get("services")
    if not isinstance(services, list) or len(services) != len(SERVICES):
        raise ValueError("Missing service probes")
    states = {}
    for service in services:
        if not isinstance(service, dict) or service.get("id") not in SERVICES or service.get("status") not in STATES:
            raise ValueError("Invalid probe")
        key = service["id"]
        if key in states:
            raise ValueError("Duplicate probe")
        states[key] = service["status"]
    if set(states) != set(SERVICES) or states["collector"] != "healthy":
        raise ValueError("Incomplete collector snapshot")
    raw_gpu = raw.get("gpu")
    if not isinstance(raw_gpu, dict) or raw_gpu.get("status") not in GPU_STATES:
        raise ValueError("Invalid GPU status")
    gpu_status = raw_gpu["status"]
    raw_devices = raw_gpu.get("devices")
    if not isinstance(raw_devices, list) or len(raw_devices) > 16 or (
        gpu_status == "healthy" and not raw_devices
    ) or (gpu_status != "healthy" and raw_devices):
        raise ValueError("Invalid GPU count")
    devices, seen = [], set()
    for raw_device in raw_devices:
        if not isinstance(raw_device, dict):
            raise ValueError("Invalid GPU")
        index, name = raw_device.get("index"), raw_device.get("name")
        if (isinstance(index, bool) or not isinstance(index, int) or
                not 0 <= index <= 128 or index in seen):
            raise ValueError("Invalid GPU index")
        if not isinstance(name, str) or not 1 <= len(name) <= 120 or not name.isprintable():
            raise ValueError("Invalid GPU name")
        seen.add(index)
        used = number(raw_device.get("memory_used_mib"), 0, 1048576)
        total = number(raw_device.get("memory_total_mib"), 0, 1048576)
        if used is not None and total is not None and used > total:
            raise ValueError("Invalid GPU VRAM")
        devices.append({
            "index": index, "name": name,
            "utilization_pct": number(raw_device.get("utilization_pct"), 0, 100),
            "memory_used_mib": used, "memory_total_mib": total,
            "temperature_c": number(raw_device.get("temperature_c"), -40, 150),
        })
    gpu_detail = {
        "healthy": "Mesures GPU disponibles.",
        "disabled": "Collecte GPU facultative non configurée.",
        "unavailable": "Le collecteur GPU ne fournit pas de mesures.",
        "unknown": "État de la collecte GPU inconnu.",
    }
    return {
        "checked_at": checked_at,
        "services": [entry(key, states[key]) for key in SERVICES],
        "gpu": {"status": gpu_status, "detail": gpu_detail[gpu_status], "devices": devices},
    }


def fetch_snapshot():
    connection = HTTPConnection(HOST, PORT, timeout=4)
    try:
        connection.request("GET", "/snapshot", headers={
            "Accept": "application/json", "Connection": "close",
        })
        response = connection.getresponse()
        if response.status != 200:
            return fallback()
        body = response.read(MAX_BYTES + 1)
        if len(body) > MAX_BYTES:
            return fallback()
        return sanitize(json.loads(body))
    except (OSError, TimeoutError, ValueError, TypeError, HTTPClientException):
        logger.info("Collector unavailable or returned an invalid snapshot")
        return fallback()
    finally:
        connection.close()


async def read_snapshot():
    return await asyncio.to_thread(fetch_snapshot)
