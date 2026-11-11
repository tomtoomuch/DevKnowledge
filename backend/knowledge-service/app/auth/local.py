"""Offline local authentication and MongoDB-backed roles/permissions."""
import asyncio
import hashlib
import hmac
import os
import re
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID, NAMESPACE_URL, uuid4, uuid5

from fastapi import HTTPException, Request
from pymongo.errors import DuplicateKeyError

from app.services.knowledge_service import RequesterIdentity

COOKIE_NAME = "dk_session"
HOURS = 8
ROLES = {
    "ADMIN": ("knowledge.read", "knowledge.create", "knowledge.update", "knowledge.delete", "users.manage"),
    "EDITOR": ("knowledge.read", "knowledge.create", "knowledge.update"),
    "READER": ("knowledge.read",),
}
PERMISSIONS = frozenset(p for values in ROLES.values() for p in values)
SC_N, SC_R, SC_P = 2**15, 8, 3
MAXMEM = 64 * 1024 * 1024
USER_PATTERN = re.compile(r"[a-z0-9_.-]{3,40}")


def utcnow():
    return datetime.now(UTC).replace(microsecond=0)


def uid(kind, code):
    return str(uuid5(NAMESPACE_URL, f"devknowledge:{kind}:{code}"))


def username_key(name):
    name = name.strip().lower()
    if not USER_PATTERN.fullmatch(name):
        raise ValueError("Username must use 3–40 ASCII letters, digits, dots, dashes or underscores")
    return name


def hash_password(password, salt=None):
    if not 12 <= len(password) <= 256 or not password.strip():
        raise ValueError("Password must have 12 to 256 characters")
    salt = salt if salt is not None else secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=SC_N, r=SC_R, p=SC_P, maxmem=MAXMEM)
    return "scrypt$" + "$".join([str(SC_N), str(SC_R), str(SC_P), salt.hex(), digest.hex()])


DUMMY_HASH = hash_password("unused-dummy-password", b"\x00" * 16)


def verify_password(password, encoded):
    try:
        algorithm, n, r, p, salt, digest = encoded.split("$")
        if (algorithm, int(n), int(r), int(p)) != ("scrypt", SC_N, SC_R, SC_P):
            return False
        candidate = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt),
                                   n=SC_N, r=SC_R, p=SC_P, maxmem=MAXMEM)
        return hmac.compare_digest(candidate, bytes.fromhex(digest))
    except (ValueError, UnicodeError, OverflowError):
        return False


async def initialize_identity(db):
    await db["users"].create_index("username_key", unique=True, name="username_unique")
    await db["user_roles"].create_index([("user_id", 1), ("role_id", 1)], unique=True)
    await db["role_permissions"].create_index([("role_id", 1), ("permission_id", 1)], unique=True)
    await db["sessions"].create_index("expires_at", expireAfterSeconds=0, name="expiry")
    for code, permissions in ROLES.items():
        role_id = uid("role", code)
        await db["roles"].update_one({"_id": role_id}, {"$setOnInsert": {
            "code": code, "name": code.title(), "description": "Built-in local role",
        }}, upsert=True)
        for permission in permissions:
            pid = uid("permission", permission)
            resource, action = permission.split(".")
            await db["permissions"].update_one({"_id": pid}, {"$setOnInsert": {
                "code": permission, "resource": resource, "action": action,
            }}, upsert=True)
            await db["role_permissions"].update_one(
                {"_id": role_id + ":" + pid},
                {"$setOnInsert": {"role_id": role_id, "permission_id": pid}}, upsert=True)


async def create_user(db, username, password, roles):
    key = username_key(username)
    if not roles or any(code not in ROLES for code in roles):
        raise ValueError("Invalid roles")
    encoded = await asyncio.to_thread(hash_password, password)
    ident = str(uuid4())
    user = {
        "_id": ident, "username": key, "username_key": key,
        "email": None, "password_hash": encoded,
        "oidc_issuer": None, "oidc_subject": None,
        "account_status": "ACTIVE", "created_at": utcnow(), "updated_at": utcnow(),
        "last_login_at": None, "revision": 1,
        # Atomic authorization projection for mutable roles; user_roles is kept in sync.
        "role_codes": sorted(set(roles)), "deleted_at": None,
    }
    await db["users"].insert_one(user)
    for code in set(roles):
        rid = uid("role", code)
        await db["user_roles"].insert_one({
            "_id": ident + ":" + rid, "user_id": ident,
            "role_id": rid, "assigned_at": utcnow(),
        })
    return user


async def bootstrap_admin(db, username, password):
    # Validate before acquiring the one-time lock to prevent accidental lockout.
    username_key(username)
    if not 12 <= len(password) <= 256 or not password.strip():
        raise ValueError("Password must have 12 to 256 characters")
    # A terminal inside the container is required. Unique marker is fail-closed.
    if await db["users"].count_documents({}) != 0:
        raise RuntimeError("An account already exists: bootstrap forbidden")
    try:
        await db["auth_bootstrap"].insert_one({"_id": "initial-admin", "created_at": utcnow()})
    except DuplicateKeyError:
        raise RuntimeError("Bootstrap already used or locked") from None
    return await create_user(db, username, password, ["ADMIN"])


async def authenticate(db, username, password):
    try:
        key = username_key(username)
    except ValueError:
        key = ""
    user = await db["users"].find_one({"username_key": key})
    encoded = user.get("password_hash") if user else None
    match = await asyncio.to_thread(verify_password, password, encoded or DUMMY_HASH)
    return user if user and user.get("account_status") == "ACTIVE" and match else None


@dataclass(frozen=True)
class Principal:
    user_id: str
    username: str
    roles: tuple[str, ...]
    permissions: frozenset[str]


async def principal_for(db, user):
    if "role_codes" in user:
        codes = tuple(sorted(code for code in user["role_codes"] if code in ROLES))
        return Principal(
            user_id=user["_id"], username=user["username"], roles=codes,
            permissions=frozenset(
                permission for code in codes for permission in ROLES[code]
            ),
        )
    # Historical accounts created before role_codes existed.
    assignments = await db["user_roles"].find({"user_id": user["_id"]}).to_list(length=100)
    roles = await db["roles"].find({"_id": {"$in": [a["role_id"] for a in assignments]}}).to_list(length=100)
    grants = await db["role_permissions"].find({
        "role_id": {"$in": [r["_id"] for r in roles]}
    }).to_list(length=500)
    permissions = await db["permissions"].find({
        "_id": {"$in": [g["permission_id"] for g in grants]}
    }).to_list(length=500)
    return Principal(user_id=user["_id"], username=user["username"],
                     roles=tuple(sorted(r["code"] for r in roles)),
                     permissions=frozenset(p["code"] for p in permissions))


async def session_principal(db, token):
    if not token or not re.fullmatch(r"[0-9a-f]{64}", token):
        return None
    session = await db["sessions"].find_one({"_id": hashlib.sha256(token.encode()).hexdigest()})
    if session is None or session["expires_at"] <= utcnow():
        return None
    user = await db["users"].find_one({"_id": session["user_id"], "account_status": "ACTIVE"})
    if user is None:
        return None
    if session.get("identity_revision", 1) != user.get("revision", 1):
        return None
    return await principal_for(db, user)


async def create_session(db, user):
    token = secrets.token_hex(32)
    await db["sessions"].insert_one({
        "_id": hashlib.sha256(token.encode()).hexdigest(), "user_id": user["_id"],
        "created_at": utcnow(), "expires_at": utcnow() + timedelta(hours=HOURS),
        "identity_revision": user.get("revision", 1),
    })
    await db["users"].update_one({"_id": user["_id"]}, {"$set": {"last_login_at": utcnow()}})
    return token, await principal_for(db, user)


async def revoke_session(db, token):
    if token and re.fullmatch(r"[0-9a-f]{64}", token):
        await db["sessions"].delete_one({"_id": hashlib.sha256(token.encode()).hexdigest()})


def secure_cookie():
    return os.getenv("AUTH_COOKIE_SECURE", "false").lower() == "true"


def cookie(token, clear=False):
    flags = "; Secure" if secure_cookie() else ""
    value = "" if clear else token
    max_age = 0 if clear else HOURS * 3600
    return f"{COOKIE_NAME}={value}; Path=/api/v1; Max-Age={max_age}; HttpOnly; SameSite=Strict{flags}"


def auth_required():
    # Disabled ONLY in disposable test environments; production Compose requires auth.
    return os.getenv("AUTH_MODE", "required") != "disabled"


async def requester_identity(request: Request):
    if os.getenv("KMS_SERVICE_TOKEN_MODE") == "required":
        # Browser cookies are never an identity authority in token-only mode.
        from app.auth.service_tokens import InvalidServiceToken, verify_kms_token
        try:
            return verify_kms_token(
                request.headers.get("authorization"),
                os.getenv("SUPERVISOR_KMS_TOKEN_KEY"),
            )
        except InvalidServiceToken:
            raise HTTPException(401, "Invalid service credential") from None
        except RuntimeError:
            raise HTTPException(503, "Service token verification unavailable") from None
    if not auth_required():
        return RequesterIdentity(permissions=PERMISSIONS)
    db = getattr(request.app.state, "mongodb_database", None)
    if db is None:
        raise HTTPException(503, "Identity database unavailable")
    principal = await session_principal(db, request.cookies.get(COOKIE_NAME))
    if principal is None:
        raise HTTPException(401, "Authentication required")
    return RequesterIdentity(user_id=UUID(principal.user_id), permissions=principal.permissions)


def require(requester, permission):
    if permission not in requester.permissions:
        raise HTTPException(403, "Insufficient permissions")
