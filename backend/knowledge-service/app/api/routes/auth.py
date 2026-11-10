"""Local identity HTTP endpoints; public signup is intentionally absent."""
from typing import Annotated, Literal
from uuid import UUID

from fastapi import Header, Query
from pydantic import model_validator

from app.api.routes.knowledges import expected_revision
from app.auth.user_management import UserManagement

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, ConfigDict, Field, field_validator
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

    @field_validator("password")
    @classmethod
    def require_nonblank_password(cls, value):
        if not value.strip():
            raise ValueError("Password cannot be blank")
        return value

    @model_validator(mode="after")
    def unique_roles(self):
        if len(self.roles) != len(set(self.roles)):
            raise ValueError("Roles must be unique")
        return self


class UserUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    username: str | None = Field(default=None, min_length=3, max_length=40)
    roles: list[Literal["ADMIN", "EDITOR", "READER"]] | None = Field(
        default=None, min_length=1, max_length=3,
    )
    account_status: Literal["ACTIVE", "DISABLED"] | None = None

    @model_validator(mode="after")
    def validate_patch(self):
        if not self.model_fields_set:
            raise ValueError("At least one field is required")
        if any(getattr(self, key) is None for key in self.model_fields_set):
            raise ValueError("Explicit null is not allowed")
        if self.roles is not None and len(self.roles) != len(set(self.roles)):
            raise ValueError("Roles must be unique")
        return self


class UserPasswordReset(BaseModel):
    model_config = ConfigDict(extra="forbid")
    password: str = Field(min_length=12, max_length=256)

    @field_validator("password")
    @classmethod
    def require_nonblank_password(cls, value):
        if not value.strip():
            raise ValueError("Password cannot be blank")
        return value


Revision = Annotated[int, Depends(expected_revision)]


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


def etag_user(data: dict, response: Response):
    response.headers["ETag"] = f'"{data["revision"]}"'
    response.headers["Cache-Control"] = "no-store"
    return data


@router.get("/users")
async def list_users(request: Request, response: Response, requester: Requester,
                     skip: Annotated[int, Query(ge=0)] = 0,
                     limit: Annotated[int, Query(ge=1, le=100)] = 100):
    require(requester, "users.manage")
    response.headers["Cache-Control"] = "no-store"
    return await UserManagement(db_for(request)).list(skip=skip, limit=limit)


@router.post("/users", status_code=status.HTTP_201_CREATED)
async def add_user(payload: UserInput, request: Request, response: Response, requester: Requester):
    require(requester, "users.manage")
    try:
        user = await create_user(db_for(request), payload.username, payload.password, payload.roles)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from None
    except DuplicateKeyError:
        raise HTTPException(409, "Username already exists") from None
    return etag_user(UserManagement.public(user, payload.roles), response)


@router.get("/users/{user_id}")
async def get_user(user_id: UUID, request: Request, response: Response, requester: Requester):
    require(requester, "users.manage")
    return etag_user(await UserManagement(db_for(request)).get(user_id), response)


@router.patch("/users/{user_id}")
async def update_user(user_id: UUID, payload: UserUpdate, request: Request,
                      response: Response, requester: Requester, revision: Revision):
    require(requester, "users.manage")
    try:
        result = await UserManagement(db_for(request)).update(
            user_id, payload, revision, requester.user_id,
        )
    except DuplicateKeyError:
        raise HTTPException(409, "Username already exists") from None
    except ValueError:
        raise HTTPException(422, "Invalid account identifier") from None
    return etag_user(result, response)


@router.post("/users/{user_id}/password", status_code=status.HTTP_204_NO_CONTENT)
async def reset_user_password(user_id: UUID, payload: UserPasswordReset,
                              request: Request, requester: Requester, revision: Revision):
    require(requester, "users.manage")
    await UserManagement(db_for(request)).reset_password(
        user_id, payload.password, revision,
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT,
                    headers={"Cache-Control": "no-store"})


@router.delete("/users/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user(user_id: UUID, request: Request, requester: Requester,
                      revision: Revision):
    require(requester, "users.manage")
    await UserManagement(db_for(request)).delete(user_id, revision, requester.user_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT,
                    headers={"Cache-Control": "no-store"})
