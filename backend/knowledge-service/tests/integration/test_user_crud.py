"""Admin account lifecycle, roles, revocation and historical links on disposable Mongo."""
import asyncio
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from httpx2 import ASGITransport, AsyncClient

from app.api.routes.auth import router as auth_router
from app.api.routes.knowledges import router as knowledge_router
from app.auth.local import bootstrap_admin, initialize_identity
from app.auth.user_management import (
    AdminMutationBusy, LastAdminError, SelfLockoutError,
    UserManagement, UserNotFound, UserRevisionConflict,
)
from app.main import admin_lockout, user_conflict, user_not_found

pytestmark = pytest.mark.integration


def test_admin_user_lifecycle_and_session_revocation(isolated_database, monkeypatch):
    monkeypatch.setenv("AUTH_MODE", "required")

    async def scenario():
        async with isolated_database() as db:
            await initialize_identity(db)
            admin = await bootstrap_admin(db, "admin", "strong-admin-password-2026")
            app = FastAPI()
            app.state.mongodb_database = db
            app.include_router(auth_router)
            app.include_router(knowledge_router)
            app.add_exception_handler(UserNotFound, user_not_found)
            app.add_exception_handler(UserRevisionConflict, user_conflict)
            app.add_exception_handler(LastAdminError, admin_lockout)
            app.add_exception_handler(SelfLockoutError, admin_lockout)
            app.add_exception_handler(AdminMutationBusy, admin_lockout)
            async with (
                AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as manager,
                AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as member,
            ):
                login = await manager.post("/api/v1/auth/login", json={
                    "username": "admin", "password": "strong-admin-password-2026",
                })
                assert login.status_code == 200, login.text
                users = "/api/v1/users"
                person = await manager.post(users, json={
                    "username": "reader", "password": "strong-reader-password-2026",
                    "roles": ["READER"],
                })
                assert person.status_code == 201, person.text
                obj = person.json()
                assert person.headers["etag"] == '"1"'
                ident = obj["user_id"]
                path = f"{users}/{ident}"
                assert obj["revision"] == 1
                assert "password_hash" not in str(obj)
                assert (await manager.get(path)).headers["etag"] == '"1"'
                assert {u["username"] for u in (await manager.get(users)).json()} == {
                    "admin", "reader",
                }
                assert (await manager.get(users, params={"skip": 1, "limit": 1})).json()[0]["username"] == "reader"
                assert (await manager.get(users, params={"limit": 101})).status_code == 422

                # An ordinary member may neither read nor modify account data.
                reader = await member.post("/api/v1/auth/login", json={
                    "username": "reader", "password": "strong-reader-password-2026",
                })
                assert reader.status_code == 200
                assert (await member.get(users)).status_code == 403
                assert (await member.get(path)).status_code == 403
                assert (await member.patch(path, headers={"If-Match": '"1"'},
                                           json={"account_status": "DISABLED"})).status_code == 403
                assert (await member.delete(path, headers={"If-Match": '"1"'})).status_code == 403
                assert (await member.post(path + "/password", headers={"If-Match": '"1"'},
                                          json={"password": "another-strong-password-2026"})).status_code == 403

                # Knowledge attribution survives account deletion.
                knowledge = await manager.post("/api/v1/knowledges", json={
                    "title": "Auteur conservé", "knowledge_type": "COURSE_NOTE",
                    "content": "historique à préserver",
                })
                assert knowledge.status_code == 201
                kid = knowledge.json()["knowledge_id"]
                assert knowledge.json()["created_by_user_id"] == admin["_id"]

                missing_etag = await manager.patch(path, json={"roles": ["EDITOR"]})
                assert missing_etag.status_code == 428
                for invalid in [
                    {}, {"roles": []}, {"roles": ["EDITOR", "EDITOR"]},
                    {"username": "bad/name"}, {"account_status": "DELETED"},
                    {"username": None}, {"extra": "not allowed"},
                ]:
                    response = await manager.patch(path, headers={"If-Match": '"1"'}, json=invalid)
                    assert response.status_code == 422, (invalid, response.text)
                changed = await manager.patch(path, headers={"If-Match": '"1"'}, json={
                    "username": "renamed_reader", "roles": ["EDITOR"],
                })
                assert changed.status_code == 200, changed.text
                assert changed.headers["etag"] == '"2"'
                assert changed.json()["roles"] == ["EDITOR"]
                assert changed.json()["username"] == "renamed_reader"
                assert (await member.get("/api/v1/auth/me")).status_code == 401
                assert await db["sessions"].count_documents({"user_id": ident}) == 0
                assert (await manager.patch(path, headers={"If-Match": '"1"'},
                                            json={"username": "stale"})).status_code == 412
                assert (await manager.patch(path, headers={"If-Match": '"2"'},
                                            json={"username": "admin"})).status_code == 409
                assert (await manager.get(path)).json()["revision"] == 2

                new_login = await member.post("/api/v1/auth/login", json={
                    "username": "renamed_reader", "password": "strong-reader-password-2026",
                })
                assert new_login.status_code == 200
                assert new_login.json()["roles"] == ["EDITOR"]
                changed_status = await manager.patch(path, headers={"If-Match": '"2"'},
                                                     json={"account_status": "DISABLED"})
                assert changed_status.status_code == 200
                assert (await member.get("/api/v1/auth/me")).status_code == 401
                assert (await member.post("/api/v1/auth/login", json={
                    "username": "renamed_reader", "password": "strong-reader-password-2026",
                })).status_code == 401
                enabled = await manager.patch(path, headers={"If-Match": '"3"'},
                                              json={"account_status": "ACTIVE"})
                assert enabled.status_code == 200 and enabled.json()["revision"] == 4

                blank_password = await manager.post(path + "/password",
                    headers={"If-Match": '"4"'}, json={"password": " " * 18})
                assert blank_password.status_code == 422
                rotated = await manager.post(path + "/password",
                    headers={"If-Match": '"4"'},
                    json={"password": "new-strong-password-2026"})
                assert rotated.status_code == 204
                assert (await manager.post(path + "/password", headers={"If-Match": '"4"'},
                                           json={"password": "next-strong-password-2026"})).status_code == 412
                assert (await member.post("/api/v1/auth/login", json={
                    "username": "renamed_reader", "password": "strong-reader-password-2026",
                })).status_code == 401
                assert (await member.post("/api/v1/auth/login", json={
                    "username": "renamed_reader", "password": "new-strong-password-2026",
                })).status_code == 200

                # Self-demotion, self-disable and deleting the sole ADMIN must fail.
                own = f"{users}/{admin['_id']}"
                assert (await manager.patch(own, headers={"If-Match": '"1"'},
                                            json={"roles": ["READER"]})).status_code == 409
                assert (await manager.patch(own, headers={"If-Match": '"1"'},
                                            json={"account_status": "DISABLED"})).status_code == 409
                assert (await manager.delete(own, headers={"If-Match": '"1"'})).status_code == 409

                deletion = await manager.delete(path, headers={"If-Match": '"5"'})
                assert deletion.status_code == 204, deletion.text
                assert (await manager.get(path)).status_code == 404
                assert (await manager.get(users)).json()[0]["username"] == "admin"
                assert (await member.get("/api/v1/auth/me")).status_code == 401
                assert (await manager.post(users, json={
                    "username": "renamed_reader", "password": "strong-new-password-2026",
                    "roles": ["READER"],
                })).status_code == 409
                stored = await db["users"].find_one({"_id": ident})
                assert stored["account_status"] == "DELETED"
                assert stored["password_hash"] is None
                assert await db["user_roles"].count_documents({"user_id": ident}) == 0
                assert (await manager.get(f"/api/v1/knowledges/{kid}")).json()[
                    "created_by_user_id"] == admin["_id"]
                assert await db["identity_admin_mutex"].count_documents({"owner": {"$exists": True}}) == 0
    asyncio.run(scenario())


def test_legacy_user_without_revision_remains_editable(isolated_database, monkeypatch):
    monkeypatch.setenv("AUTH_MODE", "required")

    async def scenario():
        async with isolated_database() as db:
            await initialize_identity(db)
            admin = await bootstrap_admin(db, "admin", "strong-admin-password-2026")
            from app.auth.local import uid, utcnow
            legacy_id = str(uuid4())
            await db["users"].insert_one({
                "_id": legacy_id, "username": "legacy", "username_key": "legacy",
                "password_hash": "invalid", "account_status": "ACTIVE",
                "created_at": utcnow(), "updated_at": utcnow(), "last_login_at": None,
            })
            rid = uid("role", "READER")
            await db["user_roles"].insert_one({
                "_id": legacy_id + ":" + rid, "user_id": legacy_id,
                "role_id": rid, "assigned_at": utcnow(),
            })
            manager = UserManagement(db)
            before = await manager.get(UUID(legacy_id))
            assert before["revision"] == 1 and before["roles"] == ["READER"]
            from app.api.routes.auth import UserUpdate
            new = await manager.update(UUID(legacy_id), UserUpdate(roles=["EDITOR"]), 1, UUID(admin["_id"]))
            assert new["revision"] == 2 and new["roles"] == ["EDITOR"]
            assert await db["user_roles"].count_documents({"user_id": legacy_id}) == 1
    asyncio.run(scenario())
