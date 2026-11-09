const express = require("express");
const { createKmsProxy } = require("./kms-proxy");

function createApp({
    kmsBaseUrl = process.env.KMS_BASE_URL || "http://127.0.0.1:8000",
    kmsTimeoutMs = Number(process.env.KMS_TIMEOUT_MS || 10000),
} = {}) {
    const app = express();
    app.disable("x-powered-by");
    const relay = createKmsProxy(kmsBaseUrl, kmsTimeoutMs);

    app.get("/health", (req, res) => {
        res.status(200).json({ status: "ok", service: "api-gateway" });
    });
    app.get("/health/ready", relay);

    // Enforce same-origin browser writes even though session cookies are SameSite=Strict.
    function rejectCrossOrigin(req, res, next) {
        if (!["POST", "PUT", "PATCH", "DELETE"].includes(req.method)) return next();
        if (req.headers["sec-fetch-site"] === "cross-site") {
            return res.status(403).json({ detail: "Cross-origin write rejected" });
        }
        if (req.headers.origin) {
            try {
                const actual = new URL(req.headers.origin);
                if (!["http:", "https:"].includes(actual.protocol) ||
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
    app.post("/api/v1/auth/login", throttleLogin, rawJson, relay);
    app.all(/^\/api\/v1\/auth\/(?:me|logout)\/?$/, rawJson, relay);
    app.all(/^\/api\/v1\/users\/?$/, rawJson, relay);
    // Raw bytes preserve KMS validation (including malformed JSON -> 422).
    // Only the collection and one identifier segment can reach the fixed upstream.
    app.all(/^\/api\/v1\/knowledges(?:\/[a-zA-Z0-9-]+)?\/?$/,
        rawJson, relay);
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
