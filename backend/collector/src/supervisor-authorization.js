"use strict";

const { timingSafeEqual } = require("node:crypto");
const { issueKmsToken, signingKey } = require("./service-tokens");

const COOKIE = /^dk_session=[0-9a-f]{64}$/;
const PERMISSIONS = new Set(["knowledge.read", "knowledge.create", "knowledge.update", "knowledge.delete"]);
const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const MAX_BODY = 4096;

function constantTimeKeyMatch(actual, expected) {
  if (typeof actual !== "string" || !/^[0-9a-f]{64}$/i.test(actual)) return false;
  const received = Buffer.from(actual, "hex");
  const known = Buffer.from(expected, "hex");
  return received.length === known.length && timingSafeEqual(received, known);
}

function readJson(req) {
  return new Promise((resolve, reject) => {
    let size = 0;
    const parts = [];
    req.on("data", chunk => {
      size += chunk.length;
      if (size > MAX_BODY) {
        reject(Object.assign(new Error("Request too large"), { status: 413 }));
        req.destroy();
        return;
      }
      parts.push(chunk);
    });
    req.on("end", () => {
      try {
        resolve(JSON.parse(Buffer.concat(parts).toString("utf8")));
      } catch {
        reject(Object.assign(new Error("Invalid JSON"), { status: 400 }));
      }
    });
    req.on("error", reject);
  });
}

/**
 * A narrow internal endpoint intended to be bound to the Supervisor's own
 * MongoDB-backed session introspector. Until that dependency exists, do not
 * enable the endpoint in Compose or production.
 *
 * @param {Object} options
 * @param {(cookie: string) => Promise<Object|null>} options.lookupSession
 *   Must verify hashed session id, account ACTIVE, identity revision and RBAC.
 */
function createAuthorizationHandler({ gatewayKey, kmsKey, lookupSession }) {
  signingKey(gatewayKey);
  signingKey(kmsKey);
  if (typeof lookupSession !== "function") {
    throw new Error("A verified Supervisor session lookup is mandatory");
  }

  return async (req, res) => {
    res.setHeader("cache-control", "no-store");
    res.setHeader("content-type", "application/json; charset=utf-8");
    res.setHeader("x-content-type-options", "nosniff");
    if (req.method !== "POST" || new URL(req.url, "http://localhost").pathname !==
        "/internal/v1/sessions/authorize") {
      return res.writeHead(404).end(JSON.stringify({ detail: "Not found" }));
    }
    if (!constantTimeKeyMatch(req.headers["x-service-key"], gatewayKey)) {
      return res.writeHead(401).end(JSON.stringify({ detail: "Invalid service credential" }));
    }
    if (!/^application\/json(?:;\s*charset=utf-8)?$/i.test(req.headers["content-type"] || "")) {
      return res.writeHead(415).end(JSON.stringify({ detail: "JSON required" }));
    }

    let input;
    try {
      input = await readJson(req);
    } catch (error) {
      if (!res.writableEnded && !res.destroyed) {
        return res.writeHead(error.status || 400).end(JSON.stringify({ detail: "Invalid request" }));
      }
      return;
    }
    if (!input || typeof input !== "object" || Array.isArray(input) ||
        Object.keys(input).sort().join(",") !== "permission,session_cookie" ||
        !COOKIE.test(input.session_cookie || "") || !PERMISSIONS.has(input.permission)) {
      return res.writeHead(422).end(JSON.stringify({ detail: "Invalid authorization request" }));
    }

    try {
      const principal = await lookupSession(input.session_cookie);
      if (!principal || !UUID.test(principal.user_id || "") ||
          !Array.isArray(principal.permissions) ||
          !principal.permissions.includes(input.permission)) {
        return res.writeHead(403).end(JSON.stringify({ detail: "Access denied" }));
      }
      const token = issueKmsToken(principal, input.permission, kmsKey);
      const output = {
        principal: {
          user_id: principal.user_id,
          username: principal.username,
          roles: principal.roles,
          permissions: principal.permissions,
        },
        kms_token: token,
      };
      return res.writeHead(200).end(JSON.stringify(output));
    } catch {
      // No tokens, principal data, database internals or stack traces in errors.
      return res.writeHead(503).end(JSON.stringify({ detail: "Identity unavailable" }));
    }
  };
}

module.exports = { createAuthorizationHandler, constantTimeKeyMatch };
