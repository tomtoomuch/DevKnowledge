"use strict";

const assert = require("node:assert/strict");
const { createSupervisorClient } = require("../src/supervisor-client");

const secret = "a".repeat(64);
const cookie = "dk_session=" + "b".repeat(64);
const userId = "7c3a089d-5076-4832-82d1-472b15e0af4c";
const jwt = "eyJhbGciOiJIUzI1NiJ9.eyJhdWQiOiJhcGkta21zIn0.signature";

function response(status, body) {
  return { status, text: async () => JSON.stringify(body) };
}
function success() {
  return response(200, { principal: {
    user_id: userId, username: "reader", roles: ["READER"],
    permissions: ["knowledge.read"],
  }, kms_token: jwt });
}

test("rejects invalid configuration before any network access", () => {
  assert.throws(() => createSupervisorClient("file:///tmp/untrusted", secret));
  assert.throws(() => createSupervisorClient("http://user:pass@supervisor:9109/", secret));
  assert.throws(() => createSupervisorClient("http://supervisor:9109/api", secret));
  assert.throws(() => createSupervisorClient("http://supervisor:9109/", "unsafe"));
  assert.throws(() => createSupervisorClient("http://supervisor:9109/", secret, 0));
});

test("never contacts Supervisor for malformed cookies or unknown permissions", async () => {
  const client = createSupervisorClient("http://supervisor:9109/", secret, 4000,
    () => { throw new Error("Must not send any request"); });
  assert.equal(await client(null, "knowledge.read"), null);
  assert.equal(await client("dk_session=bad", "knowledge.read"), null);
  assert.equal(await client(cookie, "role.admin"), null);
});

test("authorizes through the internal endpoint with service key and narrow permission", async () => {
  let called = 0;
  const client = createSupervisorClient("http://supervisor:9109/", secret, 4000,
    async (url, options) => {
      called++;
      assert.equal(url.href, "http://supervisor:9109/internal/v1/sessions/authorize");
      assert.equal(options.method, "POST");
      assert.equal(options.redirect, "manual");
      assert.equal(options.headers["x-service-key"], secret);
      assert.match(options.headers["x-request-id"], /^[0-9a-f]{32}$/);
      assert.deepEqual(JSON.parse(options.body),
        { session_cookie: cookie, permission: "knowledge.read" });
      return success();
    });
  const data = await client(cookie, "knowledge.read");
  assert.equal(called, 1);
  assert.equal(data.principal.user_id, userId);
  assert.equal(data.kmsToken, jwt);
});

test("invalid session or insufficient permission is denied", async () => {
  for (const status of [401, 403]) {
    const client = createSupervisorClient("http://supervisor:9109/", secret, 4000,
      async () => response(status, {}));
    assert.equal(await client(cookie, "knowledge.read"), null);
  }
});

test("unavailable Supervisor fails closed", async () => {
  const client = createSupervisorClient("http://supervisor:9109/", secret, 4000,
    async () => response(503, {}));
  await assert.rejects(client(cookie, "knowledge.read"), /unavailable/);
});

test("rejects malformed, oversized, unauthorized and missing-token responses", async () => {
  const examples = [
    { principal: { user_id: "invalid", username: "reader",
      roles: ["READER"], permissions: ["knowledge.read"] }, kms_token: jwt },
    { principal: { user_id: userId, username: "reader",
      roles: ["READER"], permissions: ["knowledge.update"] }, kms_token: jwt },
    { principal: { user_id: userId, username: "reader",
      roles: ["READER"], permissions: ["knowledge.read"] } },
    { principal: { user_id: userId, username: "reader",
      roles: ["SUPERUSER"], permissions: ["knowledge.read"] }, kms_token: jwt },
  ];
  for (const bad of examples) {
    const client = createSupervisorClient("http://supervisor:9109/", secret, 4000,
      async () => response(200, bad));
    await assert.rejects(client(cookie, "knowledge.read"));
  }
  const oversized = createSupervisorClient("http://supervisor:9109/", secret, 4000,
    async () => ({ status: 200, text: async () => "x".repeat(8193) }));
  await assert.rejects(oversized(cookie, "knowledge.read"), /too large/);
});
