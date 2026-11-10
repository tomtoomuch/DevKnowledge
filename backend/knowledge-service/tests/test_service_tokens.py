"""Supervisor-issued HMAC tokens: strict claims, expiry, audience and RBAC."""
import base64
import hashlib
import hmac
import json
from uuid import UUID

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from app.auth.local import require, requester_identity
from app.auth.service_tokens import InvalidServiceToken, verify_kms_token

KEY = "0123456789abcdef" * 4
SUB = "e627de24-880c-4a22-b18e-7884ee0396a3"
NOW = 1794300000
FIXTURE = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJkZXZrbm93bGVkZ2Utc3VwZXJ2aXNvciIsImF1ZCI6ImFwaS1rbXMiLCJzdWIiOiJlNjI3ZGUyNC04ODBjLTRhMjItYjE4ZS03ODg0ZWUwMzk2YTMiLCJzY29wZSI6Imtub3dsZWRnZS5yZWFkIiwiaWF0IjoxNzk0MzAwMDAwLCJleHAiOjE3OTQzMDAwNjAsImp0aSI6ImFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhIn0.eqvXQ0NG2-vu7zYGcGCDYIfGlzFwBp9sZuDvQEmGs_w"
PAYLOAD = {
    "iss": "devknowledge-supervisor", "aud": "api-kms", "sub": SUB,
    "scope": "knowledge.read", "iat": NOW, "exp": NOW + 60,
    "jti": "a" * 32,
}


def _encode(value):
    return base64.urlsafe_b64encode(json.dumps(
        value, separators=(",", ":"),
    ).encode()).decode().rstrip("=")


def _signed(claims=None, header=None):
    h = _encode({"alg": "HS256", "typ": "JWT"} if header is None else header)
    p = _encode(PAYLOAD if claims is None else claims)
    raw = h + "." + p
    digest = hmac.new(bytes.fromhex(KEY), raw.encode(), hashlib.sha256).digest()
    return raw + "." + base64.urlsafe_b64encode(digest).decode().rstrip("=")


def test_cross_language_node_fixture_and_read_only_scope():
    assert _signed() == FIXTURE
    user = verify_kms_token("Bearer " + FIXTURE, KEY, now_seconds=NOW + 10)
    assert user.user_id == UUID(SUB)
    assert user.permissions == frozenset({"knowledge.read"})
    assert "knowledge.delete" not in user.permissions


@pytest.mark.parametrize("tampered", [
    lambda t: t[:-1] + ("x" if t[-1] != "x" else "y"),
    lambda t: t.replace("eyJhbGci", "eyJhbGdp"),
    lambda t: t + ".extra",
    lambda t: "",
    lambda t: "abc.def.ghi",
])
def test_tampered_or_malformed_tokens_are_rejected(tampered):
    with pytest.raises(InvalidServiceToken):
        verify_kms_token("Bearer " + tampered(FIXTURE), KEY, now_seconds=NOW)


@pytest.mark.parametrize("changes", [
    {"iss": "fake-issuer"},
    {"aud": "some-other-service"},
    {"scope": "users.manage"},
    {"iat": NOW + 120},
    {"exp": NOW},
    {"exp": NOW + 120},
    {"sub": "not-a-uuid"},
    {"jti": "wrong"},
    {"iat": True},
    {"extra": "unexpected"},
])
def test_even_properly_signed_tokens_with_invalid_claims_are_rejected(changes):
    with pytest.raises(InvalidServiceToken):
        verify_kms_token(
            "Bearer " + _signed({**PAYLOAD, **changes}), KEY, now_seconds=NOW,
        )


@pytest.mark.parametrize("header", [
    {"alg": "none", "typ": "JWT"},
    {"alg": "HS512", "typ": "JWT"},
    {"alg": "HS256", "typ": "JWT", "kid": "unexpected"},
])
def test_algorithm_confusion_and_extra_header_are_rejected(header):
    with pytest.raises(InvalidServiceToken):
        verify_kms_token("Bearer " + _signed(header=header), KEY, now_seconds=NOW)


def test_expiry_missing_bearer_and_wrong_secret():
    with pytest.raises(InvalidServiceToken):
        verify_kms_token("Bearer " + FIXTURE, KEY, now_seconds=NOW + 60)
    with pytest.raises(InvalidServiceToken):
        verify_kms_token(FIXTURE, KEY, now_seconds=NOW + 3)
    with pytest.raises(InvalidServiceToken):
        verify_kms_token(None, KEY, now_seconds=NOW + 3)
    with pytest.raises(InvalidServiceToken):
        verify_kms_token("Bearer " + FIXTURE, "f" * 64, now_seconds=NOW + 3)
    with pytest.raises(RuntimeError):
        verify_kms_token("Bearer " + FIXTURE, "bad-secret", now_seconds=NOW + 3)


def test_token_only_mode_rejects_browser_cookie_even_if_auth_mode_disabled(monkeypatch):
    monkeypatch.setenv("KMS_SERVICE_TOKEN_MODE", "required")
    monkeypatch.setenv("AUTH_MODE", "disabled")
    monkeypatch.setenv("SUPERVISOR_KMS_TOKEN_KEY", KEY)
    # Freeze only the verifier module, without modifying system time or other tests.
    monkeypatch.setattr("app.auth.service_tokens.time.time", lambda: NOW + 3)
    app = FastAPI()

    @app.get("/secured")
    async def secured(identity=Depends(requester_identity)):
        require(identity, "knowledge.read")
        return {"subject": str(identity.user_id)}

    @app.get("/delete")
    async def delete_scope(identity=Depends(requester_identity)):
        require(identity, "knowledge.delete")
        return {"ok": True}

    with TestClient(app) as client:
        assert client.get("/secured", cookies={"dk_session": "a" * 64}).status_code == 401
        assert client.get("/secured", headers={"X-User-Id": SUB}).status_code == 401
        authorized = client.get("/secured", headers={"Authorization": "Bearer " + FIXTURE})
        assert authorized.status_code == 200, authorized.text
        assert authorized.json()["subject"] == SUB
        assert client.get("/delete", headers={
            "Authorization": "Bearer " + FIXTURE,
        }).status_code == 403
        assert client.get("/secured", headers={
            "Authorization": "Bearer " + FIXTURE[:-2] + "zz",
        }).status_code == 401
