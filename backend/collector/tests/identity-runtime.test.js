"use strict";
const test = require("node:test");
const assert = require("node:assert/strict");
const { createHash } = require("node:crypto");
const http = require("node:http");
const { startIdentityAuthority } = require("../src/identity-runtime");
const { createServer } = require("../src/server");

const rawSession = "a".repeat(64);
const tokenId = createHash("sha256").update(rawSession).digest("hex");
const userId = "9337c5fe-74b9-4ef0-86c5-a872519d45b2";
const key = "b".repeat(64);
const jwtKey = "c".repeat(64);
const settings = {
  SUPERVISOR_GATEWAY_KEY: key, SUPERVISOR_KMS_TOKEN_KEY: jwtKey,
  MONGODB_USERNAME: "supervisor-reader", MONGODB_PASSWORD: "not-the-real-password",
  MONGODB_HOST: "mongodb", MONGODB_PORT: "27017",
  MONGODB_DATABASE: "devknowledge", MONGODB_AUTH_SOURCE: "devknowledge",
};
const original = process.env.COLLECTOR_NETWORK_GUARD;

function fakeDriver({ failure = null, expired = false } = {}) {
  const calls = { closed: 0, connected: 0, dbName: null, options: null };
  class Client {
    constructor(uri, options) {
      assert.equal(uri, "mongodb://mongodb:27017/");
      calls.options = options;
    }
    async connect() {
      calls.connected++;
      if (failure === "connect") throw new Error("SECRET_CONNECTION_DETAILS");
    }
    db(name) {
      calls.dbName = name;
      return {
        command: async command => {
          assert.deepEqual(command, { ping: 1 });
          if (failure === "ping") throw new Error("SECRET_CONNECTION_DETAILS");
        },
        collection: collection => ({
          findOne: async query => {
            if (failure === "read") throw new Error("SECRET_CONNECTION_DETAILS");
            if (collection === "sessions" && query._id === tokenId) return {
              _id: tokenId, user_id: userId, identity_revision: 3,
              expires_at: new Date(expired ? "2020-01-01" : "2099-01-01"),
            };
            if (collection === "users" && query._id === userId) return {
              _id: userId, username: "reader", account_status: "ACTIVE",
              role_codes: ["READER"], revision: 3, deleted_at: null,
            };
            return null;
          },
        }),
      };
    }
    async close() { calls.closed++; }
  }
  return { Client, calls };
}
async function withServer(handler, fn) {
  const server = createServer(async () => ({}), async () => true, null, handler);
  await new Promise(resolve => server.listen(0, "127.0.0.1", resolve));
  try {
    return await fn("http://127.0.0.1:" + server.address().port);
  } finally {
    await new Promise(resolve => server.close(resolve));
  }
}
function authorize(url, serviceKey = key) {
  return fetch(url + "/internal/v1/sessions/authorize", {
    method: "POST",
    headers: { "x-service-key": serviceKey, "content-type": "application/json" },
    body: JSON.stringify({
      session_cookie: "dk_session=" + rawSession, permission: "knowledge.read",
    }),
  });
}

test.after(() => {
  if (original === undefined) delete process.env.COLLECTOR_NETWORK_GUARD;
  else process.env.COLLECTOR_NETWORK_GUARD = original;
});

test("disabled mode never constructs Mongo client or mounts identity handler", async () => {
  const runtime = await startIdentityAuthority({ mode: "disabled", config: {} });
  assert.equal(runtime.authorizationHandler, null);
  await runtime.close();
  await assert.rejects(startIdentityAuthority({ mode: "invalid", config: {} }), /Unsupported/);
});

test("requires a restricted Mongo account, service keys and network guard before connecting", async () => {
  const { Client, calls } = fakeDriver();
  await assert.rejects(startIdentityAuthority({
    mode: "shadow", config: { ...settings, SUPERVISOR_GATEWAY_KEY: "" },
    MongoClient: Client, peerGuard: async () => true,
  }));
  await assert.rejects(startIdentityAuthority({
    mode: "shadow", config: { ...settings, MONGODB_PORT: "99999" },
    MongoClient: Client, peerGuard: async () => true,
  }), /configuration is invalid/);
  await assert.rejects(startIdentityAuthority({
    mode: "shadow", config: settings, MongoClient: Client,
  }), /peer guard required/);
  assert.equal(calls.connected, 0);
});

test("shadow mode checks Mongo readiness and returns real scoped JWT through guarded internal route", async () => {
  const { Client, calls } = fakeDriver();
  const runtime = await startIdentityAuthority({
    mode: "shadow", config: settings, MongoClient: Client,
    peerGuard: async () => true,
  });
  assert.equal(calls.dbName, "devknowledge");
  assert.equal(calls.options.auth.username, "supervisor-reader");
  assert.equal(calls.connected, 1);
  await withServer(runtime.authorizationHandler, async url => {
    assert.equal((await authorize(url, "d".repeat(64))).status, 401);
    const response = await authorize(url);
    assert.equal(response.status, 200);
    const result = await response.json();
    assert.equal(result.principal.user_id, userId);
    assert.equal(result.principal.permissions.join(","), "knowledge.read");
    assert.equal(result.kms_token.split(".").length, 3);
  });
  await runtime.close();
  assert.equal(calls.closed, 1);
});

test("network guard and revoked session fail closed", async () => {
  const { Client } = fakeDriver({ expired: true });
  const runtime = await startIdentityAuthority({
    mode: "shadow", config: settings, MongoClient: Client,
    peerGuard: async () => true,
  });
  await withServer(runtime.authorizationHandler, async url => {
    assert.equal((await authorize(url)).status, 403);
  });
  await runtime.close();
  const second = await startIdentityAuthority({
    mode: "shadow", config: settings, MongoClient: Client,
    peerGuard: async () => false,
  });
  await withServer(second.authorizationHandler, async url => {
    assert.equal((await authorize(url)).status, 404);
  });
  await second.close();
});

test("Mongo failure never leaks driver messages, and always closes client", async () => {
  for (const failure of ["connect", "ping"]) {
    const { Client, calls } = fakeDriver({ failure });
    await assert.rejects(startIdentityAuthority({
      mode: "shadow", config: settings, MongoClient: Client,
      peerGuard: async () => true,
    }), error => error.message === "Supervisor identity database unavailable");
    assert.equal(calls.closed, 1);
  }
  const { Client } = fakeDriver({ failure: "read" });
  const runtime = await startIdentityAuthority({
    mode: "shadow", config: settings, MongoClient: Client,
    peerGuard: async () => true,
  });
  await withServer(runtime.authorizationHandler, async url => {
    const response = await authorize(url);
    assert.equal(response.status, 503);
    assert.equal(JSON.stringify(await response.json()).includes("SECRET_CONNECTION_DETAILS"), false);
  });
  await runtime.close();
});
