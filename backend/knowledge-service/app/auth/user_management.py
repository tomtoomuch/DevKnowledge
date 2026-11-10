"""Administrative local-account CRUD, with optimistic revisions and soft deletion.

MongoDB standalone cannot transact users + user_roles. user.role_codes is the
atomic authorization source for new/edited users. user_roles remains a logical
projection (best-effort synchronization) for the documented MLD. For legacy
accounts without role_codes, the prior user_roles assignments remain readable.
"""
import asyncio
from contextlib import asynccontextmanager
from datetime import timedelta
from uuid import UUID, uuid4

from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError

from app.auth.local import ROLES, hash_password, uid, username_key, utcnow


class UserNotFound(Exception):
    pass


class UserRevisionConflict(Exception):
    pass


class LastAdminError(Exception):
    pass


class SelfLockoutError(Exception):
    pass


class AdminMutationBusy(Exception):
    pass


class UserManagement:
    def __init__(self, db):
        self.db = db
        self.users = db["users"]

    @staticmethod
    def public(user, roles=None):
        return {
            "user_id": user["_id"],
            "username": user["username"],
            "account_status": user["account_status"],
            "roles": sorted(roles if roles is not None else user.get("role_codes", [])),
            "revision": user.get("revision", 1),
            "created_at": user.get("created_at"),
            "updated_at": user.get("updated_at"),
            "last_login_at": user.get("last_login_at"),
        }

    async def _legacy_roles(self, users):
        legacy = [u["_id"] for u in users if "role_codes" not in u]
        if not legacy:
            return {}
        assignments = await self.db["user_roles"].find(
            {"user_id": {"$in": legacy}},
        ).to_list(length=5000)
        roles = await self.db["roles"].find({
            "_id": {"$in": list({a["role_id"] for a in assignments})}
        }).to_list(length=100)
        lookup = {r["_id"]: r["code"] for r in roles}
        resolved = {}
        for assignment in assignments:
            code = lookup.get(assignment["role_id"])
            if code in ROLES:
                resolved.setdefault(assignment["user_id"], set()).add(code)
        return resolved

    async def list(self, *, skip: int = 0, limit: int = 100):
        users = await self.users.find({
            "account_status": {"$ne": "DELETED"},
        }).sort([("username_key", 1), ("_id", 1)]).skip(skip).limit(limit).to_list(length=limit)
        old_roles = await self._legacy_roles(users)
        return [
            self.public(u, old_roles.get(u["_id"], set()) if "role_codes" not in u else None)
            for u in users
        ]

    async def _get_record(self, user_id: UUID):
        user = await self.users.find_one({
            "_id": str(user_id), "account_status": {"$ne": "DELETED"},
        })
        if user is None:
            raise UserNotFound
        return user

    async def get(self, user_id: UUID):
        user = await self._get_record(user_id)
        old_roles = await self._legacy_roles([user])
        return self.public(user, old_roles.get(user["_id"], set())
                           if "role_codes" not in user else None)

    @staticmethod
    def _check_revision(user, revision):
        if user.get("revision", 1) != revision:
            raise UserRevisionConflict

    @staticmethod
    def _revision_query(user_id: UUID, expected: int):
        # Historical records have no revision; their effective revision is 1.
        rev_filter = ({"$or": [
            {"revision": 1}, {"revision": {"$exists": False}},
        ]} if expected == 1 else {"revision": expected})
        return {
            "_id": str(user_id),
            "account_status": {"$ne": "DELETED"},
            **rev_filter,
        }

    async def _current_roles(self, user):
        if "role_codes" in user:
            return set(user["role_codes"])
        return set((await self._legacy_roles([user])).get(user["_id"], set()))

    async def _active_admin_count(self):
        modern = await self.users.count_documents({
            "account_status": "ACTIVE", "role_codes": "ADMIN",
        })
        assignments = await self.db["user_roles"].find({
            "role_id": uid("role", "ADMIN"),
        }).to_list(length=10000)
        legacy = await self.users.count_documents({
            "_id": {"$in": [a["user_id"] for a in assignments]},
            "account_status": "ACTIVE",
            "role_codes": {"$exists": False},
        }) if assignments else 0
        return modern + legacy

    async def _guard_admin(self, user, roles, status, actor_user_id):
        existing_roles = await self._current_roles(user)
        if user["_id"] == str(actor_user_id) and (
            status != "ACTIVE" or "ADMIN" not in roles
        ):
            raise SelfLockoutError
        dropping_admin = (
            user.get("account_status") == "ACTIVE" and "ADMIN" in existing_roles
            and (status != "ACTIVE" or "ADMIN" not in roles)
        )
        if dropping_admin and await self._active_admin_count() <= 1:
            raise LastAdminError

    @asynccontextmanager
    async def _admin_guard(self):
        """Serialize administrator mutations across workers on standalone MongoDB.

        A stale lease can be reclaimed after a process crash. The guarded
        operations are short MongoDB writes, never password hashing.
        """
        lock = self.db["identity_admin_mutex"]
        owner = str(uuid4())
        now = utcnow()
        try:
            await lock.find_one_and_update(
                {"_id": "admin", "$or": [
                    {"owner": {"$exists": False}},
                    {"expires_at": {"$lte": now}},
                ]},
                {"$set": {
                    "owner": owner, "expires_at": now + timedelta(minutes=2),
                }},
                upsert=True, return_document=ReturnDocument.AFTER,
            )
        except DuplicateKeyError:
            raise AdminMutationBusy from None
        try:
            yield
        finally:
            await lock.update_one(
                {"_id": "admin", "owner": owner},
                {"$unset": {"owner": "", "expires_at": ""}},
            )

    async def _sync_roles(self, user_id: str, roles):
        # Atomic user.role_codes is authoritative even if this projection fails.
        await self.db["user_roles"].delete_many({"user_id": user_id})
        for code in sorted(roles):
            role_id = uid("role", code)
            await self.db["user_roles"].insert_one({
                "_id": user_id + ":" + role_id,
                "user_id": user_id, "role_id": role_id, "assigned_at": utcnow(),
            })

    async def _write_failure(self, user_id: UUID):
        if await self.users.find_one({
            "_id": str(user_id), "account_status": {"$ne": "DELETED"},
        }) is None:
            raise UserNotFound
        raise UserRevisionConflict

    async def update(self, user_id: UUID, payload, revision: int, actor_user_id):
        async with self._admin_guard():
            current = await self._get_record(user_id)
            self._check_revision(current, revision)
            roles = sorted(payload.roles if payload.roles is not None
                           else await self._current_roles(current))
            status = payload.account_status or current["account_status"]
            await self._guard_admin(current, roles, status, actor_user_id)
            changes = {
                "role_codes": roles, "account_status": status,
                "revision": revision + 1, "updated_at": utcnow(),
            }
            if payload.username is not None:
                changes["username"] = changes["username_key"] = username_key(payload.username)
            result = await self.users.find_one_and_update(
                self._revision_query(user_id, revision),
                {"$set": changes},
                return_document=ReturnDocument.AFTER,
            )
            if result is None:
                await self._write_failure(user_id)
            if payload.roles is not None:
                await self._sync_roles(str(user_id), roles)
            # Older cookies fail by identity_revision even before cleanup.
            await self.db["sessions"].delete_many({"user_id": str(user_id)})
            return self.public(result)

    async def reset_password(self, user_id: UUID, password: str, revision: int):
        # Hash before obtaining any lock; password never enters logs/URLs.
        encoded = await asyncio.to_thread(hash_password, password)
        updated = await self.users.find_one_and_update(
            self._revision_query(user_id, revision),
            {"$set": {
                "password_hash": encoded, "revision": revision + 1,
                "updated_at": utcnow(),
            }},
            return_document=ReturnDocument.AFTER,
        )
        if updated is None:
            await self._write_failure(user_id)
        await self.db["sessions"].delete_many({"user_id": str(user_id)})

    async def delete(self, user_id: UUID, revision: int, actor_user_id):
        async with self._admin_guard():
            current = await self._get_record(user_id)
            self._check_revision(current, revision)
            await self._guard_admin(current, [], "DELETED", actor_user_id)
            updated = await self.users.find_one_and_update(
                self._revision_query(user_id, revision),
                {"$set": {
                    "account_status": "DELETED", "deleted_at": utcnow(),
                    "password_hash": None, "role_codes": [],
                    "revision": revision + 1, "updated_at": utcnow(),
                }},
                return_document=ReturnDocument.AFTER,
            )
            if updated is None:
                await self._write_failure(user_id)
            await self.db["sessions"].delete_many({"user_id": str(user_id)})
            await self.db["user_roles"].delete_many({"user_id": str(user_id)})
