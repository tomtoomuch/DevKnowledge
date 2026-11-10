"use strict";
const test = require("node:test");
const assert = require("node:assert/strict");
const { createServer } = require("../src/server");
const { createAuthorizationHandler } = require("../src/supervisor-authorization");

const key = "a".repeat(64);
const kmsKey = "b".repeat(64);
const cookie = "dk_session=" + "c".repeat(64);

async function withServer(handler, fn) {
  const server = createServer(async () => ({ services: [], gpu: { status: "disabled" } }),
    async () => true, null, handler);
  await new Promise(resolve => server.listen(0, "127.0.0.1", resolve));
  try { await fn("http://127.0.0.1:" + server.address().port); }
  finally { await new Promise(resolve => server.close(resolve)); }
}

test("Supervisor endpoint is absent unless a verified identity handler is explicitly provided", async () => {
  await withServer(null, async url => {
    const response = await fetch(url + "/internal/v1/sessions/authorize", {
      method: "POST", headers: { "content-type": "application/json" },
      body: JSON.stringify({ session_cookie: cookie, permission: "knowledge.read" }),
    });
    assert.equal(response.status, 404);
  });
});

test("An explicitly wired internal handler authenticates the Gateway before issuing a KMS token", async () => {
  const handler = createAuthorizationHandler({
    gatewayKey: key, kmsKey,
    lookupSession: async () => ({
      user_id: "7b03e9f5-e35f-4f3d-9784-875b87f3a252",
      username: "reader", roles: ["READER"], permissions: ["knowledge.read"],
    }),
  });
  await withServer(handler, async url => {
    const response = await fetch(url + "/internal/v1/sessions/authorize", {
      method: "POST",
      headers: { "content-type": "application/json", "x-service-key": key },
      body: JSON.stringify({ session_cookie: cookie, permission: "knowledge.read" }),
    });
    assert.equal(response.status, 200);
    assert.equal((await response.json()).kms_token.split(".").length, 3);
  });
});
