"use strict";
const test = require("node:test");
const assert = require("node:assert/strict");
const { createHash } = require("node:crypto");
const { createMongoSessionLookup } = require("../src/mongo-session-lookup");

const raw = "c".repeat(64);
const cookie = "dk_session=" + raw;
const key = createHash("sha256").update(raw).digest("hex");
const userId = "79f21b3c-d3ec-4420-a045-1e2b0cdeaf91";
const baseUser = {
  _id: userId, username: "reader", account_status: "ACTIVE",
  role_codes: ["READER"], revision: 2, deleted_at: null,
};

function database({ user = baseUser, session = {
  _id: key, user_id: userId, identity_revision: 2,
  expires_at: new Date("2026-12-01T00:00:00Z"),
}, legacy = {} } = {}) {
  const collections = {
    sessions: { findOne: async query => query._id === key ? session : null },
    users: { findOne: async query => query._id === userId && query.account_status === "ACTIVE" ? user : null },
    user_roles: { find: () => ({ limit: () => ({ toArray: async () => legacy.user_roles || [] }) }) },
    roles: { find: () => ({ limit: () => ({ toArray: async () => legacy.roles || [] }) }) },
    role_permissions: { find: () => ({ limit: () => ({ toArray: async () => legacy.role_permissions || [] }) }) },
    permissions: { find: () => ({ limit: () => ({ toArray: async () => legacy.permissions || [] }) }) },
  };
  return { collection: name => collections[name] };
}

const clock = () => new Date("2026-11-10T10:00:00Z");

test("requires an injected MongoDB database", () => {
  assert.throws(() => createMongoSessionLookup(null), /MongoDB database/);
});

test("looks up only SHA-256 session ids and returns the authorized account", async () => {
  const result = await createMongoSessionLookup(database(), clock)(cookie);
  assert.equal(result.user_id, userId);
  assert.deepEqual(result.roles, ["READER"]);
  assert.deepEqual(result.permissions, ["knowledge.read"]);
  assert.equal(JSON.stringify(result).includes(raw), false);
});

test("rejects malformed, revoked, expired and revision-stale sessions", async () => {
  assert.equal(await createMongoSessionLookup(database(), clock)("dk_session=invalid"), null);
  assert.equal(await createMongoSessionLookup(database({ session: null }), clock)(cookie), null);
  assert.equal(await createMongoSessionLookup(database({
    session: { user_id: userId, expires_at: new Date("2026-11-09T00:00:00Z"),
      identity_revision: 2 },
  }), clock)(cookie), null);
  assert.equal(await createMongoSessionLookup(database({
    session: { user_id: userId, expires_at: new Date("2026-12-01T00:00:00Z"),
      identity_revision: 1 },
  }), clock)(cookie), null);
  assert.equal(await createMongoSessionLookup(database({
    user: { ...baseUser, account_status: "DISABLED" },
  }), clock)(cookie), null);
  assert.equal(await createMongoSessionLookup(database({
    user: { ...baseUser, deleted_at: new Date("2026-11-09T00:00:00Z") },
  }), clock)(cookie), null);
});

test("legacy account resolves only permissions explicitly granted in RBAC records", async () => {
  const lookup = createMongoSessionLookup(database({
    user: { _id: userId, username: "legacy", account_status: "ACTIVE" },
    session: { user_id: userId, expires_at: new Date("2026-12-01T00:00:00Z") },
    legacy: {
      user_roles: [{ role_id: "r" }],
      roles: [{ _id: "r", code: "ADMIN" }],
      role_permissions: [{ permission_id: "p" }],
      permissions: [{ _id: "p", code: "knowledge.read" }],
    },
  }), clock);
  const result = await lookup(cookie);
  assert.deepEqual(result.roles, ["ADMIN"]);
  assert.deepEqual(result.permissions, ["knowledge.read"]);
});

test("database errors propagate so authorization fails closed upstream", async () => {
  const db = database();
  db.collection = () => ({ findOne: async () => { throw new Error("MongoDB unavailable"); } });
  await assert.rejects(createMongoSessionLookup(db, clock)(cookie), /MongoDB unavailable/);
});
