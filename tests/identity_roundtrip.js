"use strict";
const assert = require("node:assert/strict");
const base = "http://127.0.0.1:" + process.env.GATEWAY_PORT;
const password = "identity-test-password-only";
const oldCookie = "dk_session=" + "c".repeat(64);
const checks = [];
async function call(path, { method = "GET", cookie, body, headers = {}, status = 200, origin = base } = {}) {
  const response = await fetch(origin + path, { method, headers: {
    ...(cookie ? { cookie } : {}), ...(body !== undefined ? { "content-type": "application/json" } : {}), ...headers,
  }, body: body === undefined ? undefined : JSON.stringify(body), signal: AbortSignal.timeout(12000) });
  assert.equal(response.status, status, `${method} ${path}: expected ${status}, received ${response.status}`);
  const text = await response.text();
  return { data: text && response.headers.get("content-type")?.includes("json") ? JSON.parse(text) : text, headers: response.headers };
}
async function login(username, status = 200, secret = password) {
  const response = await call("/api/v1/auth/login", { method: "POST", body: { username, password: secret }, status });
  if (status !== 200) return response;
  assert.equal(response.data.session_token, undefined);
  assert.equal(response.data.password_hash, undefined);
  const header = response.headers.get("set-cookie");
  assert.match(header, /HttpOnly; SameSite=Strict/);
  assert.match(header, /Path=\/api\/v1/);
  return header.split(";")[0];
}
async function main() {
  const phase = process.env.IDENTITY_TEST_PHASE || "initial";
  if (phase === "outage") {
    await call("/api/v1/knowledges", { cookie: oldCookie, status: 503 });
    await call("/api/v1/auth/me", { cookie: oldCookie, status: 503 });
    checks.push("Supervisor outage denies access without fallback");
    return;
  }
  const historical = await call("/api/v1/auth/me", { cookie: oldCookie });
  assert.equal(historical.data.username, "legacy-reader");
  assert.deepEqual(historical.data.permissions, ["knowledge.read"]);
  await call("/api/v1/knowledges", { cookie: oldCookie });
  checks.push("historical KMS session and RBAC remain readable through Supervisor and token-only KMS");
  if (phase === "recovery") {
    const items = await call("/api/v1/knowledges?q=Migration%20identity%20verified", { cookie: oldCookie });
    assert.equal(items.data.total, 1);
    assert.equal(items.data.items[0].content, "Synthetic content");
    checks.push("knowledge content survives restart/restoration alongside historical identity");
    return;
  }
  await call("/api/v1/knowledges", { status: 401 });
  const admin = await login("admin");
  const me = (await call("/api/v1/auth/me", { cookie: admin })).data;
  const page = await call("/", { cookie: admin });
  assert.match(page.data, /<app-root/);
  await call("/api/v1/users", { cookie: oldCookie, status: 403 });
  await call("/api/v1/users", { cookie: admin, headers: { "x-user-id": "forged", authorization: "Bearer forged" } });
  await call("/api/v1/users", { method: "POST", cookie: admin, body: {}, headers: { origin: "https://evil.invalid" }, status: 403 });
  checks.push("frontend via Gateway, sessions, RBAC, forged headers and cross-origin refusal");
  const created = await call("/api/v1/users", { method: "POST", cookie: admin, body: { username: "editor", password, roles: ["EDITOR"] }, status: 201 });
  const id = created.data.user_id;
  const userPath = "/api/v1/users/" + id;
  assert.equal(created.data.password_hash, undefined);
  await call("/api/v1/users", { method: "POST", cookie: admin, body: { username: "editor", password, roles: ["READER"] }, status: 409 });
  const editor = await login("editor");
  const item = await call("/api/v1/knowledges", { method: "POST", cookie: editor, body: {
    title: "Migration identity evidence", content: "Synthetic content", knowledge_type: "COURSE_NOTE",
  }, status: 201 });
  const knowledgePath = "/api/v1/knowledges/" + item.data.knowledge_id;
  // API uses knowledge_id; detect contract drift instead of silently skipping.
  assert.ok(item.data.knowledge_id);
  await call(knowledgePath, { method: "PATCH", cookie: editor, body: { title: "Migration identity verified" }, headers: { "if-match": item.headers.get("etag") } });
  await call(knowledgePath, { method: "DELETE", cookie: editor, headers: { "if-match": '"1"' }, status: 403 });
  await call("/api/v1/knowledge-relations", { method: "POST", cookie: oldCookie, body: {}, status: 403 });
  await call(userPath, { method: "PATCH", cookie: admin, body: { roles: ["READER"] }, status: 428 });
  await call(userPath, { method: "PATCH", cookie: admin, body: { roles: ["READER"] }, headers: { "if-match": '"999"' }, status: 412 });
  await call(userPath, { method: "PATCH", cookie: admin, body: { roles: ["READER"] }, headers: { "if-match": created.headers.get("etag") } });
  await call("/api/v1/knowledges", { cookie: editor, status: 401 });
  const reader = await login("editor");
  await call("/api/v1/knowledges", { method: "POST", cookie: reader, body: {}, status: 403 });
  const current = await call(userPath, { cookie: admin });
  await call(userPath + "/password", { method: "POST", cookie: admin, body: { password: "new-test-password-only" }, headers: { "if-match": current.headers.get("etag") }, status: 204 });
  await call("/api/v1/auth/me", { cookie: reader, status: 401 });
  await login("editor", 401);
  const reset = await login("editor", 200, "new-test-password-only");
  const afterReset = await call(userPath, { cookie: admin });
  await call(userPath, { method: "PATCH", cookie: admin, body: { account_status: "DISABLED" }, headers: { "if-match": afterReset.headers.get("etag") } });
  await call("/api/v1/auth/me", { cookie: reset, status: 401 });
  await login("editor", 401, "new-test-password-only");
  const disabled = await call(userPath, { cookie: admin });
  await call(userPath, { method: "DELETE", cookie: admin, headers: { "if-match": disabled.headers.get("etag") }, status: 204 });
  await call(userPath, { cookie: admin, status: 404 });
  const own = await call("/api/v1/users/" + me.user_id, { cookie: admin });
  await call("/api/v1/users/" + me.user_id, { method: "DELETE", cookie: admin, headers: { "if-match": own.headers.get("etag") }, status: 409 });
  await call("/api/v1/users/" + me.user_id, { method: "PATCH", cookie: admin, body: { roles: ["READER"] }, headers: { "if-match": own.headers.get("etag") }, status: 409 });
  checks.push("account CRUD, duplicate, ETags, password reset, role/status revocation and self-lockout");
  await call("/api/v1/auth/me", { origin: "http://api-kms:8000", cookie: admin, status: 404 });
  await call("/api/v1/users", { origin: "http://api-kms:8000", cookie: admin, status: 404 });
  await call("/api/v1/knowledges", { origin: "http://api-kms:8000", cookie: admin, status: 401 });
  await call("/api/v1/knowledges", { origin: "http://api-kms:8000", headers: { authorization: "Bearer forged" }, status: 401 });
  await call("/internal/v1/sessions/authorize", { origin: "http://supervisor:9109", method: "POST", body: { session_cookie: admin, permission: "knowledge.read" }, status: 401 });
  const scoped = await call("/internal/v1/sessions/authorize", { origin: "http://supervisor:9109", method: "POST", headers: { "x-service-key": process.env.SUPERVISOR_GATEWAY_KEY }, body: { session_cookie: admin, permission: "knowledge.read" } });
  await call("/api/v1/knowledges", { origin: "http://api-kms:8000", method: "POST", headers: { authorization: "Bearer " + scoped.data.kms_token }, body: {}, status: 422 });
  // A valid-shaped body reaches scope validation, which must deny a read-only token.
  await call("/api/v1/knowledges", { origin: "http://api-kms:8000", method: "POST", headers: { authorization: "Bearer " + scoped.data.kms_token }, body: { knowledge_type: "COURSE_NOTE", title: "denied", content: "denied" }, status: 403 });
  checks.push("KMS identity endpoints removed, cookies and forged tokens rejected, JWT scope verified by Python");
  await call("/api/v1/auth/logout", { method: "POST", cookie: admin, body: {}, status: 204 });
  await call("/api/v1/auth/me", { cookie: admin, status: 401 });
  checks.push("logout revokes persisted session");
}
main().then(() => console.log(JSON.stringify({ checks }))).catch(error => {
  console.error(error.message); process.exitCode = 1;
});
