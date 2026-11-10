"use strict";

const { constantTimeKeyMatch } = require("./supervisor-authorization");
const { signingKey } = require("./service-tokens");

const PREFIX = "/internal/v1/auth/";
const COOKIE = /^dk_session=[0-9a-f]{64}$/;
const SESSION_TOKEN = /^[0-9a-f]{64}$/;
const MAX_BODY = 4096;

function readPayload(req) {
  return new Promise((resolve, reject) => {
    let size = 0;
    const chunks = [];
    req.on("data", chunk => {
      size += chunk.length;
      if (size <= MAX_BODY) chunks.push(chunk);
    });
    req.on("end", () => {
      if (size > MAX_BODY) return reject({ status: 413 });
      try {
        resolve(JSON.parse(Buffer.concat(chunks).toString("utf8")));
      } catch {
        reject({ status: 400 });
      }
    });
    req.on("error", () => reject({ status: 400 }));
  });
}

function hasKeys(value, keys) {
  return value && typeof value === "object" && !Array.isArray(value) &&
    Object.keys(value).sort().join(",") === [...keys].sort().join(",");
}

/**
 * Private Gateway-to-Supervisor protocol for a future write-enabled identity
 * mode. Not mounted in normal Compose or "shadow" mode. Never call from a
 * browser directly. A separate network peer guard is required when mounted.
 */
function createSessionHandler({gatewayKey, sessionStore}) {
  signingKey(gatewayKey);
  if (!sessionStore || typeof sessionStore.login !== "function" ||
      typeof sessionStore.logout !== "function") {
    throw new TypeError("A verified MongoDB identity session store is required");
  }

  return async function handleSession(req, res) {
    res.setHeader("cache-control", "no-store");
    res.setHeader("content-type", "application/json; charset=utf-8");
    res.setHeader("x-content-type-options", "nosniff");
    let pathname;
    try {
      const url = new URL(req.url, "http://localhost");
      if (url.search || url.hash) throw new Error("Unexpected query");
      pathname = url.pathname;
    } catch {
      return res.writeHead(404).end(JSON.stringify({detail: "Not found"}));
    }
    if (req.method !== "POST" || ![PREFIX + "login", PREFIX + "logout"].includes(pathname)) {
      return res.writeHead(404).end(JSON.stringify({detail: "Not found"}));
    }
    if (!constantTimeKeyMatch(req.headers["x-service-key"], gatewayKey)) {
      return res.writeHead(401).end(JSON.stringify({detail: "Invalid service credential"}));
    }
    if (!/^application\/json(?:;\s*charset=utf-8)?$/i.test(req.headers["content-type"] || "")) {
      return res.writeHead(415).end(JSON.stringify({detail: "JSON required"}));
    }
    let payload;
    try {
      payload = await readPayload(req);
    } catch (error) {
      return res.writeHead(error.status || 400).end(JSON.stringify({detail: "Invalid request"}));
    }

    if (pathname === PREFIX + "login") {
      if (!hasKeys(payload, ["username", "password"]) ||
          typeof payload.username !== "string" || payload.username.length < 3 ||
          payload.username.length > 40 || typeof payload.password !== "string" ||
          payload.password.length < 1 || payload.password.length > 256) {
        return res.writeHead(422).end(JSON.stringify({detail: "Invalid credentials payload"}));
      }
      try {
        const session = await sessionStore.login(payload);
        if (!session) return res.writeHead(401).end(JSON.stringify({detail: "Invalid credentials"}));
        if (!SESSION_TOKEN.test(session.token || "") || !session.principal ||
            typeof session.principal.user_id !== "string") {
          return res.writeHead(503).end(JSON.stringify({detail: "Identity unavailable"}));
        }
        return res.writeHead(200).end(JSON.stringify({
          session_token: session.token,
          principal: session.principal,
        }));
      } catch {
        return res.writeHead(503).end(JSON.stringify({detail: "Identity unavailable"}));
      }
    }

    if (!hasKeys(payload, ["session_cookie"]) || !COOKIE.test(payload.session_cookie || "")) {
      return res.writeHead(422).end(JSON.stringify({detail: "Invalid logout payload"}));
    }
    try {
      await sessionStore.logout(payload.session_cookie);
      res.writeHead(204).end();
    } catch {
      res.writeHead(503).end(JSON.stringify({detail: "Identity unavailable"}));
    }
  };
}

module.exports = { createSessionHandler };
