"""Security-critical local authentication primitives."""
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.auth.local import (
    COOKIE_NAME, ROLES, PERMISSIONS, cookie, hash_password, require, username_key,
    verify_password,
)
from app.services.knowledge_service import RequesterIdentity


def test_scrypt_hash_is_salted_and_never_returns_plaintext():
    password = "strong passphrase for a local account"
    first = hash_password(password)
    second = hash_password(password)
    assert first != second
    assert password not in first
    assert first.startswith("scrypt$")
    assert verify_password(password, first)
    assert not verify_password("different passphrase", first)
    assert not verify_password(password, "invalid")
    assert not verify_password(password, "pbkdf2$10$8$1$00$00")


@pytest.mark.parametrize("password", ["", "short", " " * 20, "x" * 257])
def test_weak_or_oversized_password_is_rejected(password):
    with pytest.raises(ValueError):
        hash_password(password)


@pytest.mark.parametrize("username", ["", "ab", "../admin", "a@b.com", "a" * 41])
def test_invalid_local_usernames_are_rejected(username):
    with pytest.raises(ValueError):
        username_key(username)


def test_username_normalization_is_case_insensitive():
    assert username_key("  AdMin_01  ") == "admin_01"


def test_default_permissions_apply_least_privilege():
    assert set(ROLES["READER"]) == {"knowledge.read"}
    assert "knowledge.delete" not in ROLES["EDITOR"]
    assert "users.manage" in ROLES["ADMIN"]
    assert set(ROLES["ADMIN"]) == PERMISSIONS


def test_permission_denial_never_depends_on_untrusted_identity_headers():
    reader = RequesterIdentity(user_id=uuid4(), permissions=frozenset(ROLES["READER"]))
    require(reader, "knowledge.read")
    with pytest.raises(HTTPException) as exc:
        require(reader, "knowledge.create")
    assert exc.value.status_code == 403


def test_session_cookie_is_http_only_same_site_and_path_scoped(monkeypatch):
    monkeypatch.delenv("AUTH_COOKIE_SECURE", raising=False)
    session = cookie("a" * 64)
    assert session.startswith(COOKIE_NAME + "=")
    for marker in ("HttpOnly", "SameSite=Strict", "Path=/api/v1", "Max-Age=28800"):
        assert marker in session
    monkeypatch.setenv("AUTH_COOKIE_SECURE", "true")
    assert "; Secure" in cookie("a" * 64)
    assert "Max-Age=0" in cookie("", clear=True)
