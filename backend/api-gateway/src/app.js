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
    // Raw bytes preserve KMS validation (including malformed JSON -> 422).
    // Only the collection and one identifier segment can reach the fixed upstream.
    app.all(/^\/api\/v1\/knowledges(?:\/[a-zA-Z0-9-]+)?\/?$/,
        express.raw({ type: () => true, limit: "1mb", inflate: false }), relay);
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
