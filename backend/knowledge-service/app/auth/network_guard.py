"""Reject unexpected HTTP peers on the isolated Compose internal network.

This is a temporary IP/source topology guard and NOT an authenticated service
identity. Replace with mutual authentication/service credentials in the next
security iteration. Always fail closed if Docker DNS resolution fails.
"""
import asyncio
import ipaddress
import os
import socket

from fastapi import Request
from starlette.responses import JSONResponse


def guard_enabled():
    return os.getenv("KMS_NETWORK_GUARD") == "required"


def peer_matches(peer, allowed):
    try:
        address = ipaddress.ip_address(peer)
    except ValueError:
        return False
    if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped:
        address = address.ipv4_mapped
    return str(address) in allowed


async def allowed_peer(request: Request):
    if not guard_enabled():
        return True
    client = request.client.host if request.client else ""
    path = request.url.path
    if path in ("/health", "/health/ready") and peer_matches(client, {"127.0.0.1", "::1"}):
        return True
    # All API routes are Gateway-exclusive. Collector may access health probes.
    names = ("api-gateway", "collector") if path in ("/health", "/health/ready") else ("api-gateway",)
    addresses = set()
    try:
        loop = asyncio.get_running_loop()
        for name in names:
            resolved = await asyncio.wait_for(loop.getaddrinfo(
                name, None, family=socket.AF_INET, type=socket.SOCK_STREAM,
            ), timeout=1.0)
            addresses.update(item[4][0] for item in resolved)
    except (OSError, asyncio.TimeoutError):
        return False
    return peer_matches(client, addresses)


async def restrict_to_internal_peers(request: Request, call_next):
    if not await allowed_peer(request):
        return JSONResponse(status_code=404, content={"detail": "Not found"})
    return await call_next(request)
