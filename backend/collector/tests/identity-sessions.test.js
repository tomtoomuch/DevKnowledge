"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const { createHash, scrypt: scryptCallback } = require("node:crypto");
const { promisify } = require("node:util");
const { createIdentitySessionStore, verifyLegacyPassword, usernameKey } =
  require("../src/identity-sessions");

const scrypt = promisify(scryptCallback);
const token = "b".repeat(64);
const tokenId = createHash("sha256").update(token).digest("hex");
const userId = "51c22a76-2fee-4820-aa99-22094e0b85df";
const clock = () => new Date("2026-11-10T12:00:00.000Z");
const password = "secure-session-passphrase";

async function hashPassword(value) {
  const salt = Buffer.alloc(16, 5);
  const digest = await scrypt(value, salt, 64, {
    N: 32768, r: 8, p: 3, maxmem: 64 * 1024 * 1024,
  });
  return ["scrypt", 32768, 8, 3, salt.toString("hex"), digest.toString("hex")].join("$");
}

function fakeDb(user, {failInsert = false, failFind = false} = {}) {
  const sessions = new Map();
  const calls = [];
  return {
    sessions, calls,
    collection(name) {
      if (name === "users") return {
        async findOne(query) {
          if (failFind) throw new Error("db unavailable");
          if (query.username_key) return query.username_key === user?.username_key ? user : null;
          return query._id === user?._id && query.account_status === "ACTIVE" &&
            user.account_status === "ACTIVE" ? user : null;
        },
        async updateOne(query, update) {
          calls.push({query, update});
          return {matchedCount: user && query._id === user._id &&
            query.account_status === user.account_status &&
            query.revision === user.revision && query.deleted_at === user.deleted_at ? 1 : 0};
        },
      };
      if (name === "sessions") return {
        async findOne(query) { return sessions.get(query._id) || null; },
        async insertOne(document) {
          if (failInsert) throw new Error("cannot write session");
          sessions.set(document._id, document);
        },
        async deleteOne(query) { sessions.delete(query._id); },
      };
      throw new Error("unexpected collection: " + name);
    },
  };
}

test("accepts Python-compatible scrypt and rejects malformed or wrong credentials", async () => {
  const hash = await hashPassword(password);
  assert.equal(await verifyLegacyPassword(password, hash), true);
  assert.equal(await verifyLegacyPassword("wrong", hash), false);
  assert.equal(await verifyLegacyPassword(password, hash.replace("$32768$", "$16384$")), false);
  assert.equal(await verifyLegacyPassword(password, null), false);
  assert.equal(usernameKey("  Alice.NAME "), "alice.name");
  assert.equal(usernameKey("invalid/name"), null);
});

test("creates legacy-compatible hashed session, verifies principal and revokes on logout", async () => {
  const user = {
    _id: userId, username: "reader", username_key: "reader",
    account_status: "ACTIVE", deleted_at: null, revision: 3,
    role_codes: ["READER"], password_hash: await hashPassword(password),
  };
  const db = fakeDb(user);
  const store = createIdentitySessionStore(db, {now: clock, generateToken: () => token});
  const result = await store.login({username: " READER ", password});
  assert.equal(result.token, token);
  assert.equal(result.principal.user_id, userId);
  assert.deepEqual(result.principal.permissions, ["knowledge.read"]);
  assert.equal(db.sessions.size, 1);
  assert.equal(db.sessions.get(tokenId).identity_revision, 3);
  assert.equal(db.sessions.get(tokenId).expires_at.toISOString(), "2026-11-10T20:00:00.000Z");
  assert.deepEqual(db.calls[0].update.$set, {last_login_at: clock()});
  await store.logout("dk_session=" + token);
  assert.equal(db.sessions.size, 0);
  await store.logout("dk_session=invalid");
});

test("denies invalid, disabled, deleted or missing accounts without issuing sessions", async () => {
  const base = {
    _id: userId, username: "reader", username_key: "reader", revision: 1,
    role_codes: ["READER"], password_hash: await hashPassword(password),
    account_status: "ACTIVE", deleted_at: null,
  };
  for (const user of [
    null,
    {...base, account_status: "DISABLED"},
    {...base, deleted_at: clock()},
    {...base, password_hash: null},
  ]) {
    const db = fakeDb(user);
    const store = createIdentitySessionStore(db, {now: clock});
    assert.equal(await store.login({username: "reader", password}), null);
    assert.equal(db.sessions.size, 0);
  }
  const db = fakeDb(base);
  assert.equal(await createIdentitySessionStore(db, {now: clock}).login({
    username: "reader", password: "not-the-password",
  }), null);
});

test("rejects concurrent account revision changes and invalid session token generation", async () => {
  const user = {
    _id: userId, username: "reader", username_key: "reader",
    account_status: "ACTIVE", deleted_at: null, revision: 2,
    role_codes: ["READER"], password_hash: await hashPassword(password),
  };
  const db = fakeDb(user);
  db.collection = (() => {
    const real = db.collection.bind(db);
    return name => {
      const result = real(name);
      if (name === "users") result.updateOne = async () => ({matchedCount: 0});
      return result;
    };
  })();
  assert.equal(await createIdentitySessionStore(db, {now: clock}).login({
    username: "reader", password,
  }), null);
  const db2 = fakeDb(user);
  await assert.rejects(createIdentitySessionStore(db2, {
    now: clock, generateToken: () => "unsafe",
  }).login({username: "reader", password}), /token generator/);
});

test("propagates MongoDB outage instead of returning an authenticated principal", async () => {
  const db = fakeDb(null, {failFind: true});
  await assert.rejects(createIdentitySessionStore(db, {now: clock}).login({
    username: "reader", password,
  }), /unavailable/);
});
