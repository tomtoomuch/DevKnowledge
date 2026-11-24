"use strict";
const { sessionCookie, validPrincipal } = require("./session-auth");

function createIdentityProxy(baseUrl, sharedSecret, timeoutMs, secureCookie = false) {
  const origin = new URL(baseUrl);
  if (!["http:", "https:"].includes(origin.protocol) || origin.username || origin.password || origin.pathname !== "/" || origin.search || origin.hash ||
      !/^[0-9a-f]{64}$/i.test(sharedSecret || "")) throw new Error("Invalid Supervisor configuration");
  const cookie = (token, clear = false) => `dk_session=${token}; Path=/api/v1; Max-Age=${clear ? 0 : 28800}; HttpOnly; SameSite=Strict${secureCookie ? "; Secure" : ""}`;
  return async (req, res) => {
    res.setHeader("cache-control", "no-store");
    const path = req.path.replace(/\/$/, "");
    const session = sessionCookie(req.headers.cookie);
    let target = path.replace(/^\/api\/v1\//, "/internal/v1/");
    let body = Buffer.isBuffer(req.body) ? req.body : undefined;
    const headers = { "x-service-key": sharedSecret, "accept": "application/json" };
    if (req.headers["content-type"]) headers["content-type"] = req.headers["content-type"];
    if (req.headers["if-match"]) headers["if-match"] = req.headers["if-match"];
    if (session) headers["x-session-cookie"] = session;
    if (path === "/api/v1/auth/logout") {
      if (!session) { res.setHeader("set-cookie", cookie("", true)); return res.status(204).end(); }
      headers["content-type"] = "application/json";
      body = JSON.stringify({ session_cookie: session });
    } else if (path !== "/api/v1/auth/login" && !session) return res.status(401).json({ detail: "Authentication required" });
    const separator = req.originalUrl.indexOf("?");
    if (separator >= 0) target += req.originalUrl.slice(separator);
    try {
      const response = await fetch(new URL(target, origin), { method: req.method, headers,
        body: ["GET", "HEAD"].includes(req.method) ? undefined : body,
        redirect: "manual", signal: AbortSignal.timeout(timeoutMs) });
      if (![200, 201, 204, 400, 401, 403, 404, 409, 412, 413, 415, 422, 428, 429, 503].includes(response.status)) throw new Error("Invalid upstream response");
      const text = await response.text();
      if (text.length > 262144) throw new Error("Response too large");
      let payload = text ? JSON.parse(text) : null;
      if (path === "/api/v1/auth/login" && response.status === 200) {
        if (!/^[0-9a-f]{64}$/.test(payload?.session_token || "") || !validPrincipal(payload.principal)) throw new Error("Invalid identity response");
        res.setHeader("set-cookie", cookie(payload.session_token));
        payload = payload.principal; // No opaque token in the response body.
      }
      if (path === "/api/v1/auth/logout" && response.status === 204) res.setHeader("set-cookie", cookie("", true));
      if (response.headers.has("etag")) res.setHeader("etag", response.headers.get("etag"));
      return res.status(response.status).send(response.status === 204 ? undefined : payload);
    } catch { return res.status(503).json({ detail: "Identity unavailable" }); }
  };
}
module.exports = { createIdentityProxy };
