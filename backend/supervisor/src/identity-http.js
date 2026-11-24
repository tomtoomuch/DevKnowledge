"use strict";

const { constantTimeKeyMatch } = require("./supervisor-authorization");
const { createSessionHandler } = require("./supervisor-session-handler");
const { createUserManagement, revision, fail } = require("./identity-users");

async function readBody(req) {
  let size = 0;
  const parts = [];
  for await (const part of req) {
    size += part.length;
    if (size <= 8192) parts.push(part);
  }
  if (size > 8192) fail(413, "Request too large");
  try { return JSON.parse(Buffer.concat(parts).toString("utf8")); }
  catch { fail(422, "Invalid JSON"); }
}

function createIdentityHandler({ gatewayKey, sessionStore, db }) {
  const sessionHandler = createSessionHandler({ gatewayKey, sessionStore });
  const users = createUserManagement(db);
  return async (req, res) => {
    const send = (status, body) => res.writeHead(status).end(body === undefined ? undefined : JSON.stringify(body));
    res.setHeader("content-type", "application/json; charset=utf-8");
    res.setHeader("cache-control", "no-store");
    try {
      if (!constantTimeKeyMatch(req.headers["x-service-key"], gatewayKey)) return send(401, { detail: "Invalid service credential" });
      const url = new URL(req.url, "http://localhost");
      if (["/internal/v1/auth/login", "/internal/v1/auth/logout"].includes(url.pathname)) return sessionHandler(req, res);
      const principal = await sessionStore.lookupSession(req.headers["x-session-cookie"]);
      if (!principal) return send(401, { detail: "Authentication required" });
      if (req.method === "GET" && url.pathname === "/internal/v1/auth/me" && !url.search) return send(200, principal);
      const match = /^\/internal\/v1\/users(?:\/([0-9a-fA-F-]{36})(\/password)?)?$/.exec(url.pathname);
      if (!match) return send(404, { detail: "Not found" });
      const authorize = async () => {
        const actor = await sessionStore.lookupSession(req.headers["x-session-cookie"]);
        if (!actor) fail(401, "Authentication required");
        if (!actor.permissions.includes("users.manage")) fail(403, "Insufficient permissions");
      };
      await authorize();
      let result;
      const id = match[1]?.toLowerCase();
      if (req.method === "GET" && !match[2]) {
        if (id) {
          if (url.search) fail(422, "Unexpected query");
          result = await users.get(id);
        } else {
          if ([...url.searchParams.keys()].some(key => !["skip", "limit"].includes(key)) ||
              ["skip", "limit"].some(key => url.searchParams.getAll(key).length > 1)) fail(422, "Invalid pagination");
          const skip = url.searchParams.get("skip") ?? "0";
          const limit = url.searchParams.get("limit") ?? "100";
          if (!/^\d{1,9}$/.test(skip) || !/^\d{1,3}$/.test(limit) || Number(limit) < 1 || Number(limit) > 100) fail(422, "Invalid pagination");
          result = await users.list(Number(skip), Number(limit));
        }
      } else {
        if (url.search) fail(422, "Unexpected query");
        if (!["POST", "PATCH", "DELETE"].includes(req.method)) return send(404, { detail: "Not found" });
        if (req.method !== "DELETE" && !/^application\/json(?:;\s*charset=utf-8)?$/i.test(req.headers["content-type"] || "")) fail(415, "JSON required");
        const expected = id ? revision(req.headers["if-match"]) : null;
        const payload = req.method === "DELETE" ? {} : await readBody(req);
        if (!id && req.method === "POST") {
          // Account creation also serializes with revocation of the actor.
          result = await users.guarded(async () => { await authorize(); return users.create(payload); });
          res.setHeader("etag", `"${result.revision}"`);
          return send(201, result);
        }
        const kind = id && !match[2] && req.method === "PATCH" ? "patch"
          : id && !match[2] && req.method === "DELETE" ? "delete"
          : id && match[2] && req.method === "POST" ? "password" : null;
        if (!kind) return send(404, { detail: "Not found" });
        result = await users.mutate(id, expected, principal.user_id, payload, kind, authorize);
        if (kind !== "patch") return send(204);
      }
      if (!Array.isArray(result)) res.setHeader("etag", `"${result.revision}"`);
      return send(200, result);
    } catch (error) {
      if (error.code === 11000) return send(409, { detail: "Username already exists" });
      const status = [400, 401, 403, 404, 409, 412, 413, 415, 422, 428].includes(error.status) ? error.status : 503;
      return send(status, { detail: status === 503 ? "Identity unavailable" : error.message });
    }
  };
}
module.exports = { createIdentityHandler };
