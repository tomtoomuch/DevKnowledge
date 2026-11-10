"use strict";

const { randomBytes } = require("node:crypto");

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const PERMISSIONS = new Set(["knowledge.read", "knowledge.create", "knowledge.update", "knowledge.delete", "users.manage"]);
const COOKIE = /^dk_session=[0-9a-f]{64}$/;
const TOKEN = /^[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+$/;
const SECRET = /^[0-9a-f]{64}$/i;

/**
 * Contract for the future Supervisor identity authority.
 *
 * The Gateway never trusts browser-supplied identity headers. The Supervisor
 * must introspect the opaque session and produce a KMS-scoped token only when
 * the principal has the requested permission. This client fails closed.
 *
 * This module is intentionally NOT wired into the production routing until
 * Supervisor's authenticated endpoint and integration tests are available.
 */
function createSupervisorClient(baseUrl, sharedSecret, timeoutMs = 4000, fetchImpl = fetch) {
  const origin = new URL(baseUrl);
  if (!["http:", "https:"].includes(origin.protocol) || origin.username || origin.password ||
      origin.pathname !== "/" || origin.search || origin.hash) {
    throw new Error("SUPERVISOR_BASE_URL must be an HTTP(S) origin");
  }
  if (typeof sharedSecret !== "string" || !SECRET.test(sharedSecret)) {
    throw new Error("SUPERVISOR_GATEWAY_KEY must be a 32-byte hex secret");
  }
  if (!Number.isInteger(timeoutMs) || timeoutMs < 1 || timeoutMs > 10000) {
    throw new Error("Invalid Supervisor timeout");
  }
  const endpoint = new URL("/internal/v1/sessions/authorize", origin);

  return async function authorizeSession(cookie, permission) {
    if (!COOKIE.test(cookie || "") || !PERMISSIONS.has(permission)) return null;
    const requestId = randomBytes(16).toString("hex");
    const response = await fetchImpl(endpoint, {
      method: "POST",
      headers: {
        "content-type": "application/json",
        "accept": "application/json",
        "x-service-key": sharedSecret,
        "x-request-id": requestId,
      },
      body: JSON.stringify({ session_cookie: cookie, permission }),
      redirect: "manual",
      signal: AbortSignal.timeout(timeoutMs),
    });
    if (response.status === 401 || response.status === 403) return null;
    if (response.status !== 200) throw new Error("Supervisor authorization unavailable");
    const payload = await response.text();
    if (payload.length > 8192) throw new Error("Supervisor response too large");
    let result;
    try { result = JSON.parse(payload); } catch { throw new Error("Invalid Supervisor response"); }
    const principal = result?.principal;
    if (!principal || typeof principal.username !== "string" ||
        !UUID.test(principal.user_id || "") || !Array.isArray(principal.roles) ||
        !Array.isArray(principal.permissions) ||
        !principal.roles.every(role => ["ADMIN", "EDITOR", "READER"].includes(role)) ||
        !principal.permissions.every(p => PERMISSIONS.has(p)) ||
        !principal.permissions.includes(permission)) {
      throw new Error("Invalid Supervisor principal or permission");
    }
    // The JWT is forwarded to KMS, never inspected as an authority by Gateway.
    // KMS performs the signature, audience, lifetime and scope validation.
    const token = result.kms_token;
    if (permission.startsWith("knowledge.") && (typeof token !== "string" ||
        token.length > 4096 || !TOKEN.test(token))) {
      throw new Error("Invalid Supervisor service token");
    }
    return { principal, kmsToken: permission.startsWith("knowledge.") ? token : null };
  };
}

module.exports = { createSupervisorClient };
