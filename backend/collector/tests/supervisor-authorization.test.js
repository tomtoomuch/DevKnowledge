"use strict";
const test = require("node:test");
const assert = require("node:assert/strict");
const http = require("node:http");
const { createAuthorizationHandler, constantTimeKeyMatch } = require("../src/supervisor-authorization");

const gatewayKey = "a".repeat(64);
const kmsKey = "b".repeat(64);
const cookie = "dk_session=" + "c".repeat(64);
const principal = {
  user_id: "f888626f-cbbc-45c5-8505-a3308f289e56",
  username: "reader",
  roles: ["READER"],
  permissions: ["knowledge.read"],
};

async function withHandler(lookupSession, fn) {
  const handler = createAuthorizationHandler({ gatewayKey, kmsKey, lookupSession });
  const server = http.createServer(handler);
  await new Promise(resolve => server.listen(0, "127.0.0.1", resolve));
  try { await fn("http://127.0.0.1:" + server.address().port); }
  finally { await new Promise(resolve => server.close(resolve)); }
}

function request(url, { key = gatewayKey, permission = "knowledge.read", session = cookie } = {}) {
  return fetch(url + "/internal/v1/sessions/authorize", {
    method: "POST",
    headers: { "content-type": "application/json", "x-service-key": key },
    body: JSON.stringify({ session_cookie: session, permission }),
  });
}

test("rejects missing identity dependency or unsafe keys", () => {
  assert.throws(() => createAuthorizationHandler({ gatewayKey, kmsKey }), /lookup/);
  assert.throws(() => createAuthorizationHandler({
    gatewayKey: "bad", kmsKey, lookupSession: async () => principal,
  }), /secret/);
  assert.equal(constantTimeKeyMatch(gatewayKey, gatewayKey), true);
  assert.equal(constantTimeKeyMatch("f".repeat(64), gatewayKey), false);
  assert.equal(constantTimeKeyMatch(null, gatewayKey), false);
});

test("authenticated internal request produces scoped KMS token", async () => {
  let count = 0;
  await withHandler(async () => { count++; return principal; }, async url => {
    const result = await request(url);
    assert.equal(result.status, 200);
    assert.equal(result.headers.get("cache-control"), "no-store");
    const body = await result.json();
    assert.equal(body.principal.user_id, principal.user_id);
    assert.deepEqual(body.principal.permissions, ["knowledge.read"]);
    assert.equal(body.kms_token.split(".").length, 3);
  });
  assert.equal(count, 1);
});

test("untrusted internal caller never reaches identity database", async () => {
  await withHandler(() => { throw new Error("Must not lookup"); }, async url => {
    assert.equal((await request(url, { key: "f".repeat(64) })).status, 401);
    assert.equal((await fetch(url + "/internal/v1/sessions/authorize")).status, 404);
  });
});

test("rejects invalid permission, session and malformed body", async () => {
  let count = 0;
  await withHandler(async () => { count++; return principal; }, async url => {
    assert.equal((await request(url, { permission: "users.manage" })).status, 422);
    assert.equal((await request(url, { session: "dk_session=invalid" })).status, 422);
    const invalid = await fetch(url + "/internal/v1/sessions/authorize", {
      method: "POST", headers: {
        "content-type": "application/json", "x-service-key": gatewayKey,
      }, body: "{bad",
    });
    assert.equal(invalid.status, 400);
    const missingType = await fetch(url + "/internal/v1/sessions/authorize", {
      method: "POST", headers: { "x-service-key": gatewayKey },
      body: JSON.stringify({ session_cookie: cookie, permission: "knowledge.read" }),
    });
    assert.equal(missingType.status, 415);
  });
  assert.equal(count, 0);
});

test("denies revoked sessions, missing RBAC rights and fails closed on DB outage", async () => {
  await withHandler(async () => null, async url => {
    assert.equal((await request(url)).status, 403);
  });
  await withHandler(async () => ({ ...principal, permissions: [] }), async url => {
    assert.equal((await request(url)).status, 403);
  });
  await withHandler(async () => { throw new Error("Database offline"); }, async url => {
    const result = await request(url);
    assert.equal(result.status, 503);
    assert.deepEqual(await result.json(), { detail: "Identity unavailable" });
  });
});
