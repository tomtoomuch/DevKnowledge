"""Strictly verify Supervisor-issued HMAC-SHA256 service tokens.

This is a transitional contract: HMAC does not encrypt claims, and the
verifying KMS also knows the signing key. Follow ADR-004 for Ed25519 later.
"""
import base64
import binascii
import hashlib
import hmac
import json
import re
import time
from uuid import UUID

from app.services.knowledge_service import RequesterIdentity

ISSUER = "devknowledge-supervisor"
AUDIENCE = "api-kms"
ALLOWED_SCOPES = frozenset({
    "knowledge.read", "knowledge.create", "knowledge.update", "knowledge.delete",
})
_TOKEN_SEGMENT = re.compile(r"[A-Za-z0-9_-]+")
_KEY_HEX = re.compile(r"[0-9a-fA-F]{64}")
_JTI = re.compile(r"[0-9a-f]{32}")


class InvalidServiceToken(ValueError):
    """Malformed, untrusted or unauthorized service credential."""


def _strict_json(data: bytes) -> dict:
    def reject_duplicate(pairs):
        output = {}
        for key, value in pairs:
            if key in output:
                raise InvalidServiceToken("duplicate claim")
            output[key] = value
        return output

    value = json.loads(data, object_pairs_hook=reject_duplicate)
    if not isinstance(value, dict):
        raise InvalidServiceToken("JWT section must be an object")
    return value


def _decode(segment: str) -> dict:
    if not segment or not _TOKEN_SEGMENT.fullmatch(segment):
        raise InvalidServiceToken("invalid base64url")
    try:
        data = base64.urlsafe_b64decode(segment + "=" * (-len(segment) % 4))
        if base64.urlsafe_b64encode(data).decode("ascii").rstrip("=") != segment:
            raise InvalidServiceToken("noncanonical base64url")
        return _strict_json(data)
    except (ValueError, UnicodeError, binascii.Error, json.JSONDecodeError):
        raise InvalidServiceToken("invalid JWT section") from None


def verify_kms_token(
    authorization: str | None,
    secret_hex: str | None,
    *,
    now_seconds: int | None = None,
) -> RequesterIdentity:
    if not isinstance(secret_hex, str) or not _KEY_HEX.fullmatch(secret_hex):
        raise RuntimeError("Supervisor/KMS signing key is not configured securely")
    if not authorization or not authorization.startswith("Bearer "):
        raise InvalidServiceToken("Bearer token required")
    token = authorization[7:]
    if len(token) > 2048:
        raise InvalidServiceToken("oversized token")
    parts = token.split(".")
    if len(parts) != 3 or any(not _TOKEN_SEGMENT.fullmatch(x) for x in parts):
        raise InvalidServiceToken("invalid JWT shape")
    header, payload, signature = parts
    signing_input = (header + "." + payload).encode("ascii")
    expected = hmac.new(bytes.fromhex(secret_hex), signing_input, hashlib.sha256).digest()
    try:
        received = base64.urlsafe_b64decode(signature + "=" * (-len(signature) % 4))
    except (binascii.Error, ValueError):
        raise InvalidServiceToken("invalid JWT signature") from None
    if not hmac.compare_digest(expected, received):
        raise InvalidServiceToken("invalid JWT signature")
    header_data = _decode(header)
    if header_data != {"alg": "HS256", "typ": "JWT"}:
        raise InvalidServiceToken("disallowed JWT algorithm")
    claims = _decode(payload)
    if set(claims) != {"iss", "aud", "sub", "scope", "iat", "exp", "jti"}:
        raise InvalidServiceToken("unexpected or missing JWT claims")
    if claims["iss"] != ISSUER or claims["aud"] != AUDIENCE:
        raise InvalidServiceToken("wrong issuer or audience")
    if type(claims["iat"]) is not int or type(claims["exp"]) is not int:
        raise InvalidServiceToken("invalid timestamps")
    now = int(time.time()) if now_seconds is None else now_seconds
    if (claims["iat"] < 1 or claims["iat"] > now + 30 or
            claims["exp"] <= now or claims["exp"] <= claims["iat"] or
            claims["exp"] - claims["iat"] > 60):
        raise InvalidServiceToken("expired or invalid token lifetime")
    if not isinstance(claims["scope"], str) or claims["scope"] not in ALLOWED_SCOPES:
        raise InvalidServiceToken("disallowed token scope")
    if not isinstance(claims["jti"], str) or not _JTI.fullmatch(claims["jti"]):
        raise InvalidServiceToken("invalid token identifier")
    try:
        subject = UUID(claims["sub"])
        if str(subject) != claims["sub"]:
            raise ValueError("noncanonical UUID")
    except (TypeError, ValueError, AttributeError):
        raise InvalidServiceToken("invalid token subject") from None
    return RequesterIdentity(user_id=subject, permissions=frozenset({claims["scope"]}))
