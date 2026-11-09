"""Actual MongoDB identity, RBAC and knowledge endpoints in a disposable test DB."""
import asyncio

import pytest
from fastapi import FastAPI
from httpx2 import ASGITransport, AsyncClient

from app.api.routes.auth import router as auth_router
from app.api.routes.knowledges import router as knowledge_router
from app.auth.local import bootstrap_admin, initialize_identity

pytestmark = pytest.mark.integration


def test_local_identity_rbac_session_revocation_on_real_mongodb(isolated_database, monkeypatch):
    monkeypatch.setenv("AUTH_MODE", "required")

    async def scenario():
        async with isolated_database() as database:
            await initialize_identity(database)
            await initialize_identity(database)
            admin = await bootstrap_admin(database, "AdMiN", "strong-admin-password-2026")
            stored = await database["users"].find_one({"_id": admin["_id"]})
            assert stored["username"] == "admin"
            assert "strong-admin-password-2026" not in stored["password_hash"]
            assert await database["roles"].count_documents({}) == 3
            assert await database["permissions"].count_documents({}) == 5
            assert await database["user_roles"].count_documents({}) == 1
            with pytest.raises(RuntimeError):
                await bootstrap_admin(database, "another", "another-strong-password")

            application = FastAPI()
            application.state.mongodb_database = database
            application.include_router(auth_router)
            application.include_router(knowledge_router)

            async with AsyncClient(transport=ASGITransport(app=application), base_url="http://test") as client:
                assert (await client.get("/api/v1/knowledges")).status_code == 401
                assert (await client.get("/api/v1/auth/me")).status_code == 401
                bad = await client.post("/api/v1/auth/login", json={
                    "username": "admin", "password": "not-the-right-password",
                })
                assert bad.status_code == 401 and "dk_session" not in bad.headers.get("set-cookie", "")
                logged = await client.post("/api/v1/auth/login", json={
                    "username": "ADMIN", "password": "strong-admin-password-2026",
                })
                assert logged.status_code == 200, logged.text
                assert logged.json()["roles"] == ["ADMIN"]
                assert "knowledge.delete" in logged.json()["permissions"]
                assert "HttpOnly" in logged.headers["set-cookie"]
                token = logged.cookies.get("dk_session")
                assert token is not None and len(token) == 64
                me = await client.get("/api/v1/auth/me")
                assert me.status_code == 200 and me.json()["username"] == "admin"
                created = await client.post("/api/v1/users", json={
                    "username": "reader", "password": "strong-reader-password-2026", "roles": ["READER"],
                })
                assert created.status_code == 201, created.text
                assert created.json()["roles"] == ["READER"]
                listed = await client.get("/api/v1/users")
                assert listed.status_code == 200
                assert listed.headers["cache-control"] == "no-store"
                summary = {entry["username"]: entry for entry in listed.json()}
                assert set(summary) == {"admin", "reader"}
                assert summary["admin"]["roles"] == ["ADMIN"]
                assert summary["reader"]["roles"] == ["READER"]
                assert "password_hash" not in str(listed.json())
                duplicate = await client.post("/api/v1/users", json={
                    "username": "READER", "password": "some-strong-password-2026", "roles": ["EDITOR"],
                })
                assert duplicate.status_code == 409
                created_knowledge = await client.post("/api/v1/knowledges", json={
                    "title": "Restricted", "content": "Knowledge kept private",
                    "knowledge_type": "CODE_SNIPPET",
                })
                assert created_knowledge.status_code == 201
                assert created_knowledge.json()["created_by_user_id"] == admin["_id"]
                logout = await client.post("/api/v1/auth/logout")
                assert logout.status_code == 204
                assert (await client.get("/api/v1/knowledges")).status_code == 401
                assert await database["sessions"].count_documents({}) == 0

                reader_login = await client.post("/api/v1/auth/login", json={
                    "username": "reader", "password": "strong-reader-password-2026",
                })
                assert reader_login.status_code == 200
                assert reader_login.json()["permissions"] == ["knowledge.read"]
                assert (await client.get("/api/v1/knowledges")).status_code == 200
                assert (await client.get("/api/v1/users")).status_code == 403
                assert (await client.post("/api/v1/knowledges", json={
                    "title": "Forbidden", "content": "Not authorized",
                    "knowledge_type": "COURSE_NOTE",
                })).status_code == 403
                assert (await client.patch(
                    "/api/v1/knowledges/" + created_knowledge.json()["knowledge_id"],
                    headers={"If-Match": '"1"'}, json={"title": "Forbidden"},
                )).status_code == 403
                assert (await client.delete(
                    "/api/v1/knowledges/" + created_knowledge.json()["knowledge_id"],
                    headers={"If-Match": '"1"'},
                )).status_code == 403
                assert (await database["knowledge_items"].count_documents({})) == 1
    asyncio.run(scenario())
