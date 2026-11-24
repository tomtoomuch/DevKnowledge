"use strict";
const { describe, before, after, beforeEach, test } = require("node:test");
const assert = require("node:assert/strict");
const { randomUUID } = require("node:crypto");
const { createUserManagement, initializeIdentity, bootstrapAdmin, uid } = require("../../src/identity-users");
const { createIdentitySessionStore } = require("../../src/identity-sessions");
const uri = process.env.SUPERVISOR_TEST_MONGODB_URI;
const password = "identity-test-password-only";

describe("Identity account mutations on MongoDB", { skip: !uri }, () => {
  let client, db, users, sessions, admin;
  before(async () => {
    const { MongoClient } = require("mongodb");
    client = new MongoClient(uri);
    await client.connect();
    db = client.db("supervisor_users_test_" + randomUUID().replaceAll("-", ""));
    users = createUserManagement(db);
    sessions = createIdentitySessionStore(db);
    await initializeIdentity(db);
  });
  after(async () => { try { if (db) await db.dropDatabase(); } finally { await client?.close(); } });
  beforeEach(async () => {
    for (const name of ["users", "sessions", "user_roles", "auth_bootstrap", "identity_admin_mutex"]) await db.collection(name).deleteMany({});
    admin = await bootstrapAdmin(db, "admin", password);
  });
  test("stable UUIDs preserve KMS RBAC records and bootstrap refuses a second account", async () => {
    const role = await db.collection("roles").findOne({ code: "ADMIN" });
    // Python uuid5(NAMESPACE_URL, 'devknowledge:role:ADMIN').
    assert.equal(role._id, "0816dddf-c89f-54be-87f8-102f6dd0d894");
    await assert.rejects(bootstrapAdmin(db, "admin2", password), error => error.status === 409);
    assert.equal(await db.collection("users").countDocuments({}), 1);
  });
  test("last ADMIN cannot be removed, including legacy role assignments", async () => {
    await db.collection("users").updateOne({ _id: admin.user_id }, { $unset: { role_codes: "", revision: "" } });
    await assert.rejects(users.mutate(admin.user_id, 1, randomUUID(), {}, "delete"), error => error.status === 409);
    assert.deepEqual((await users.get(admin.user_id)).roles, ["ADMIN"]);
  });
  test("parallel demotions leave an active ADMIN and reject stale or busy writes", async () => {
    const second = await users.create({ username: "admin2", password, roles: ["ADMIN"] });
    const result = await Promise.allSettled([
      users.mutate(admin.user_id, 1, randomUUID(), { roles: ["READER"] }, "patch"),
      users.mutate(second.user_id, 1, randomUUID(), { roles: ["READER"] }, "patch"),
    ]);
    assert.equal(result.filter(r => r.status === "fulfilled").length, 1);
    assert.equal(result.filter(r => r.status === "rejected" && r.reason.status === 409).length, 1);
    assert.equal(await db.collection("users").countDocuments({ role_codes: "ADMIN", account_status: "ACTIVE" }), 1);
  });
  test("roles, password and soft deletion invalidate sessions while preserving history", async () => {
    const user = await users.create({ username: "editor", password, roles: ["EDITOR"] });
    const session = await sessions.login({ username: "editor", password });
    const changed = await users.mutate(user.user_id, 1, admin.user_id, { roles: ["READER"] }, "patch");
    assert.equal(changed.revision, 2);
    assert.equal(await sessions.lookupSession("dk_session=" + session.token), null);
    const roleLinks = await db.collection("user_roles").find({ user_id: user.user_id }).toArray();
    assert.deepEqual(roleLinks.map(link => link.role_id), [uid("role", "READER")]);
    await assert.rejects(users.mutate(user.user_id, 1, admin.user_id, {}, "delete"), error => error.status === 412);
    await users.mutate(user.user_id, 2, admin.user_id, { password: "changed-identity-password" }, "password");
    assert.equal(await sessions.login({ username: "editor", password }), null);
    assert.ok(await sessions.login({ username: "editor", password: "changed-identity-password" }));
    await users.mutate(user.user_id, 3, admin.user_id, {}, "delete");
    const stored = await db.collection("users").findOne({ _id: user.user_id });
    assert.equal(stored.account_status, "DELETED");
    assert.equal(stored.password_hash, null);
    assert.ok(stored.created_at);
    assert.equal(await db.collection("sessions").countDocuments({ user_id: user.user_id }), 0);
  });
  test("a crashed writer mutex fails closed without automatic lock stealing", async () => {
    await db.collection("identity_admin_mutex").updateOne({ _id: "admin" }, { $set: {
      owner: "stale-process", expires_at: new Date("2000-01-01"),
    } });
    await assert.rejects(users.mutate(admin.user_id, 1, randomUUID(), {}, "delete"), error => error.status === 409);
    assert.equal((await users.get(admin.user_id)).account_status, "ACTIVE");
  });
});
