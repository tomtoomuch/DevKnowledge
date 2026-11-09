"""Local identity HTTP endpoints; public signup is intentionally absent."""
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, ConfigDict, Field
from pymongo.errors import DuplicateKeyError

from app.auth.local import (
    COOKIE_NAME, authenticate, auth_required, cookie, create_session, create_user,
    requester_identity, require, revoke_session, session_principal,
)
from app.services.knowledge_service import RequesterIdentity

router = APIRouter(prefix="/api/v1", tags=["Identity"])
Requester = Annotated[RequesterIdentity, Depends(requester_identity)]


class LoginInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    username: str = Field(min_length=3, max_length=40)
    password: str = Field(min_length=1, max_length=256)


class UserInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    username: str = Field(min_length=3, max_length=40)
    password: str = Field(min_length=12, max_length=256)
    roles: list[Literal["ADMIN", "EDITOR", "READER"]] = Field(min_length=1, max_length=3)


def db_for(request):
    db = getattr(request.app.state, "mongodb_database", None)
    if db is None:
        raise HTTPException(503, "Identity database unavailable")
    return db


def public(principal):
    return {"user_id": principal.user_id, "username": principal.username,
            "roles": list(principal.roles), "permissions": sorted(principal.permissions)}


@router.post("/auth/login")
async def login(payload: LoginInput, request: Request, response: Response):
    if not auth_required():
        raise HTTPException(503, "Authentication disabled in disposable test mode")
    db = db_for(request)
    user = await authenticate(db, payload.username, payload.password)
    if not user:
        raise HTTPException(401, "Invalid username or password")
    token, principal = await create_session(db, user)
    response.headers["Set-Cookie"] = cookie(token)
    response.headers["Cache-Control"] = "no-store"
    return public(principal)


@router.get("/auth/me")
async def me(request: Request):
    db = db_for(request)
    principal = await session_principal(db, request.cookies.get(COOKIE_NAME))
    if not principal:
        raise HTTPException(401, "Authentication required")
    return public(principal)


@router.post("/auth/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(request: Request, response: Response):
    await revoke_session(db_for(request), request.cookies.get(COOKIE_NAME))
    response.headers["Set-Cookie"] = cookie("", clear=True)
    response.headers["Cache-Control"] = "no-store"


@router.get("/users")
async def list_users(request: Request, response: Response, requester: Requester):
    require(requester, "users.manage")
    response.headers["Cache-Control"] = "no-store"
    db = db_for(request)
    users = await db["users"].find(
        {}, {"password_hash": 0, "oidc_subject": 0}
    ).sort("username_key", 1).limit(100).to_list(length=100)
    assignments = await db["user_roles"].find(
        {"user_id": {"$in": [user["_id"] for user in users]}}
    ).to_list(length=300)
    roles = await db["roles"].find({
        "_id": {"$in": list({assignment["role_id"] for assignment in assignments})}
    }).to_list(length=100)
    role_codes = {role["_id"]: role["code"] for role in roles}
    assigned = {}
    for assignment in assignments:
        code = role_codes.get(assignment["role_id"])
        if code is not None:
            assigned.setdefault(assignment["user_id"], []).append(code)
    return [
        {"user_id": user["_id"], "username": user["username"],
         "account_status": user["account_status"],
         "roles": sorted(assigned.get(user["_id"], []))}
        for user in users
    ]


@router.post("/users", status_code=status.HTTP_201_CREATED)
async def add_user(payload: UserInput, request: Request, requester: Requester):
    require(requester, "users.manage")
    try:
        user = await create_user(db_for(request), payload.username, payload.password, payload.roles)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from None
    except DuplicateKeyError:
        raise HTTPException(409, "Username already exists") from None
    return {
        "user_id": user["_id"], "username": user["username"],
        "account_status": user["account_status"], "roles": sorted(set(payload.roles)),
    }
