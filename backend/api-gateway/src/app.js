const express = require("express");
const { createKmsProxy } = require("./kms-proxy");
const { sessionCookie, permissionFor, validPrincipal, createSessionLookup } = require("./session-auth");
const { checkFrontend } = require("./frontend-health");
const { createFrontendProxy } = require("./frontend-proxy");
const { createSupervisorClient } = require("./supervisor-client");
const { createIdentityProxy } = require("./identity-proxy");

function createApp({
    kmsBaseUrl = process.env.KMS_BASE_URL || "http://127.0.0.1:8000",
    kmsTimeoutMs = Number(process.env.KMS_TIMEOUT_MS || 10000),
    sessionLookup = null,
    authEnabled = process.env.AUTH_MODE !== "disabled",
    frontendProbe = checkFrontend,
    frontendBaseUrl = process.env.FRONTEND_BASE_URL || "http://frontend:80",
    identityAuthority = process.env.GATEWAY_IDENTITY_AUTHORITY || "legacy",
    supervisorBaseUrl = process.env.SUPERVISOR_BASE_URL || "http://supervisor:9109",
    supervisorKey = process.env.SUPERVISOR_GATEWAY_KEY,
    cookieSecure = process.env.AUTH_COOKIE_SECURE === "true",
} = {}) {
    const app = express();
    app.disable("x-powered-by");
    if (!["legacy", "supervisor"].includes(identityAuthority)) throw new Error("Invalid identity authority");
    const migrated = identityAuthority === "supervisor";
    if (migrated && !authEnabled) throw new Error("Supervisor routing requires authentication");
    const relay = createKmsProxy(kmsBaseUrl, kmsTimeoutMs, { tokenOnly: migrated });
    const identityRelay = migrated ? createIdentityProxy(supervisorBaseUrl, supervisorKey, Math.min(kmsTimeoutMs, 4000), cookieSecure) : relay;
    const authorize = migrated ? createSupervisorClient(supervisorBaseUrl, supervisorKey, Math.min(kmsTimeoutMs, 4000)) : null;
    const serveFrontend = createFrontendProxy(frontendBaseUrl, kmsTimeoutMs);
    const lookup = sessionLookup || createSessionLookup(kmsBaseUrl, kmsTimeoutMs);
    const publicScheme = process.env.GATEWAY_PUBLIC_SCHEME || "http";
    if (!["http", "https"].includes(publicScheme)) {
        throw new Error("GATEWAY_PUBLIC_SCHEME must be http or https");
    }

    app.get("/health", (req, res) => {
        res.status(200).json({ status: "ok", service: "api-gateway" });
    });
    app.get("/health/ready", relay);
    // Supervisor reaches this route through the internal network; Gateway probes Nginx via DMZ.
    app.get("/health/frontend", async (req, res) => {
        res.setHeader("Cache-Control", "no-store");
        if (await frontendProbe()) {
            res.status(200).json({ status: "ok", service: "frontend" });
        } else {
            res.status(503).json({ status: "error", service: "frontend" });
        }
    });

    // Enforce same-origin browser writes even though session cookies are SameSite=Strict.
    function rejectCrossOrigin(req, res, next) {
        if (!["POST", "PUT", "PATCH", "DELETE"].includes(req.method)) return next();
        if (req.headers["sec-fetch-site"] === "cross-site") {
            return res.status(403).json({ detail: "Cross-origin write rejected" });
        }
        if (req.headers.origin) {
            try {
                const actual = new URL(req.headers.origin);
                if (actual.protocol !== publicScheme + ":" ||
                    actual.host.toLowerCase() !== (req.headers.host || "").toLowerCase()) {
                    return res.status(403).json({ detail: "Cross-origin write rejected" });
                }
            } catch {
                return res.status(403).json({ detail: "Invalid Origin" });
            }
        }
        next();
    }
    app.use("/api/v1", rejectCrossOrigin);
    // The Gateway validates every authenticated browser session before relaying an API call.
    // KMS also enforces its own permissions, independently of this external boundary.
    app.use("/api/v1", async (req, res, next) => {
        res.setHeader("Cache-Control", "no-store");
        // Only disposable test Compose explicitly sets AUTH_MODE=disabled.
        if (!authEnabled) return next();
        if (req.method === "POST" && /^\/auth\/(?:login|logout)\/?$/.test(req.path)) {
            return next();
        }
        if (migrated && (req.path.replace(/\/$/, "") === "/auth/me" || /^\/users(?:\/|$)/.test(req.path))) return next();
        const cookie = sessionCookie(req.headers.cookie);
        if (!cookie && !sessionLookup) {
            return res.status(401).json({ detail: "Authentication required" });
        }
        try {
            const permission = permissionFor(req.path, req.method);
            const authorization = migrated ? await authorize(cookie, permission) : null;
            const principal = migrated ? authorization?.principal : await lookup(cookie);
            if (!validPrincipal(principal)) {
                return res.status(401).json({ detail: "Authentication required" });
            }
            if (!principal.permissions.includes(permission)) {
                return res.status(403).json({ detail: "Insufficient permissions" });
            }
            if (req.method === "GET" && /^\/auth\/me\/?$/.test(req.path)) {
                return res.status(200).json(principal);
            }
            req.principal = principal;
            if (migrated) req.kmsToken = authorization.kmsToken;
            return next();
        } catch (error) {
            if (error.status === 403) return res.status(403).json({ detail: "Insufficient permissions" });
            return res.status(503).json({ detail: "Session verification unavailable" });
        }
    });
    // Basic local login throttle; not a substitute for multi-instance rate limiting.
    const attempts = new Map();
    function throttleLogin(req, res, next) {
        const key = req.socket.remoteAddress || "unknown";
        const now = Date.now();
        const item = attempts.get(key);
        const count = item && item.expires > now ? item.count : 0;
        if (count >= 10) {
            res.setHeader("Retry-After", "60");
            return res.status(429).json({ detail: "Too many login requests" });
        }
        attempts.set(key, { count: count + 1, expires: item && item.expires > now ? item.expires : now + 60000 });
        next();
    }
    const rawJson = express.raw({ type: () => true, limit: "1mb", inflate: false });
    app.post("/api/v1/auth/login", throttleLogin, rawJson, identityRelay);
    app.post(/^\/api\/v1\/auth\/logout\/?$/, rawJson, identityRelay);
    if (migrated) app.get(/^\/api\/v1\/auth\/me\/?$/, identityRelay);
    app.get(/^\/api\/v1\/users\/?$/, identityRelay);
    app.post(/^\/api\/v1\/users\/?$/, rawJson, identityRelay);
    app.get(/^\/api\/v1\/users\/[0-9a-fA-F-]+\/?$/, identityRelay);
    app.patch(/^\/api\/v1\/users\/[0-9a-fA-F-]+\/?$/, rawJson, identityRelay);
    app.delete(/^\/api\/v1\/users\/[0-9a-fA-F-]+\/?$/, identityRelay);
    app.post(/^\/api\/v1\/users\/[0-9a-fA-F-]+\/password\/?$/, rawJson, identityRelay);
    app.get("/api/v1/knowledge-types", relay);
    app.get(/^\/api\/v1\/tags\/?$/, relay);
    app.post(/^\/api\/v1\/tags\/?$/, rawJson, relay);
    app.get(/^\/api\/v1\/tags\/[a-zA-Z0-9-]+\/?$/, relay);
    app.get(/^\/api\/v1\/(?:technologies|technology-versions)\/?$/, relay);
    app.post(/^\/api\/v1\/(?:technologies|technology-versions)\/?$/, rawJson, relay);
    app.get(/^\/api\/v1\/(?:technologies|technology-versions)\/[a-zA-Z0-9-]+\/?$/, relay);
    app.get(/^\/api\/v1\/relation-types\/?$/, relay);
    app.get(/^\/api\/v1\/knowledge-relations\/?$/, relay);
    app.post(/^\/api\/v1\/knowledge-relations\/?$/, rawJson, relay);
    app.get(/^\/api\/v1\/knowledge-relations\/[a-zA-Z0-9-]+\/?$/, relay);
    app.patch(/^\/api\/v1\/knowledge-relations\/[a-zA-Z0-9-]+\/?$/, rawJson, relay);
    app.delete(/^\/api\/v1\/knowledge-relations\/[a-zA-Z0-9-]+\/?$/, relay);
    // Opt-in RNCP API: strict path/method allowlist; Gateway RBAC precedes relay.
    app.get(/^\/api\/v1\/rncp\/frameworks\/[A-Za-z0-9_-]{1,50}\/versions\/[A-Za-z0-9._-]{1,50}\/?$/, relay);
    app.get(/^\/api\/v1\/rncp\/competencies\/[0-9a-fA-F-]{36}\/evidence\/?$/, relay);
    app.post(/^\/api\/v1\/rncp\/competencies\/[0-9a-fA-F-]{36}\/evidence\/?$/, rawJson, relay);
    app.post(/^\/api\/v1\/rncp\/competencies\/[0-9a-fA-F-]{36}\/knowledge-links\/?$/, rawJson, relay);

    // Monitoring is authenticated by KMS and always traverses the Gateway.
    // Monitoring authentication is enforced at the Gateway and again at KMS.
    app.get("/api/v1/monitoring/services", relay);
    // Raw bytes preserve KMS validation (including malformed JSON -> 422).
    // Only the collection and one identifier segment can reach the fixed upstream.
    app.all(/^\/api\/v1\/knowledges(?:\/[a-zA-Z0-9-]+)?\/?$/,
        rawJson, relay);
    // Fail closed for unregistered API/health paths: never serve Angular for them.
    app.use((req, res, next) => {
        // Internal FastAPI/OpenAPI paths are deliberately NOT SPA routes.
        const reserved = new Set(["/docs", "/redoc", "/openapi.json",
            "/metrics", "/internal"]);
        if (reserved.has(req.path.toLowerCase()) ||
            req.path === "/api" || req.path.startsWith("/api/") ||
            req.path === "/health" || req.path.startsWith("/health/")) {
            return res.status(404).json({ detail: "Route not found" });
        }
        if (req.method !== "GET" && req.method !== "HEAD") {
            return res.status(404).json({ detail: "Route not found" });
        }
        return serveFrontend(req, res);
    });

    app.use((error, req, res, next) => {
        if (res.headersSent) return next(error);
        const status = error.status === 413 ? 413 : error.status === 415 ? 415 : 400;
        res.status(status).json({ detail: status === 413 ? "Request body too large" :
            status === 415 ? "Unsupported content encoding" : "Invalid request body" });
    });
    return app;
}

module.exports = createApp();
module.exports.createApp = createApp;
