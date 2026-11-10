"use strict";

// The Gateway is the mandatory browser authentication and authorization boundary.
// KMS remains the private identity/session backing store (defense in depth).
function sessionCookie(header) {
  const found = (header || "").split(";").map(x => x.trim()).filter(x => x.startsWith("dk_session="));
  return found.length === 1 && /^dk_session=[0-9a-f]{64}$/.test(found[0]) ? found[0] : null;
}

function permissionFor(path, method) {
  if (/^\/users\/?$/.test(path)) return "users.manage";
  if (/^\/(?:knowledges)(?:\/[a-zA-Z0-9-]+)?\/?$/.test(path)) {
    return { GET: "knowledge.read", POST: "knowledge.create", PATCH: "knowledge.update",
      PUT: "knowledge.update", DELETE: "knowledge.delete" }[method] || "knowledge.read";
  }
  if (method === "POST" && /^\/(?:tags|technologies|technology-versions)\/?$/.test(path)) {
    return "knowledge.create";
  }
  return "knowledge.read";
}

function validPrincipal(data) {
  if (!data || typeof data !== "object" || typeof data.user_id !== "string" ||
      typeof data.username !== "string" || !Array.isArray(data.roles) ||
      !Array.isArray(data.permissions) || !data.permissions.every(x => typeof x === "string")) {
    return false;
  }
  return true;
}

function createSessionLookup(kmsBaseUrl, timeoutMs) {
  const source = new URL(kmsBaseUrl);
  const url = new URL("/api/v1/auth/me", source);
  return async cookie => {
    if (!cookie) return null;
    const response = await fetch(url, {
      method: "GET", headers: { Cookie: cookie, Accept: "application/json" },
      redirect: "manual", signal: AbortSignal.timeout(Math.min(timeoutMs, 4000)),
    });
    if (response.status === 401) return null;
    if (response.status !== 200) throw new Error("Identity source unavailable");
    const body = await response.text();
    if (body.length > 8192) throw new Error("Invalid identity response");
    const principal = JSON.parse(body);
    if (!validPrincipal(principal)) throw new Error("Invalid identity response");
    return principal;
  };
}

module.exports = { sessionCookie, permissionFor, validPrincipal, createSessionLookup };
