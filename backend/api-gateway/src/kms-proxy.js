const http = require("node:http");
const https = require("node:https");

const REQUEST_HEADERS = ["accept", "content-type", "accept-language", "if-match"];
const RESPONSE_HEADERS = ["content-type", "content-language", "allow", "retry-after", "etag", "cache-control"];

function createKmsProxy(baseUrl, timeoutMs) {
    let origin;
    try {
        origin = new URL(baseUrl);
    } catch {
        throw new Error("KMS_BASE_URL must be an HTTP(S) origin");
    }
    if (!["http:", "https:"].includes(origin.protocol) || origin.username ||
        origin.password || origin.pathname !== "/" || origin.search || origin.hash) {
        throw new Error("KMS_BASE_URL must be an HTTP(S) origin without credentials or path");
    }
    if (!Number.isInteger(timeoutMs) || timeoutMs < 1 || timeoutMs > 60000) {
        throw new Error("KMS_TIMEOUT_MS must be an integer between 1 and 60000");
    }
    const transport = origin.protocol === "https:" ? https : http;

    return function relay(req, res) {
        const headers = {};
        const connectionHeaders = new Set((req.headers.connection || "").toLowerCase().split(",").map(s => s.trim()));
        // No client identity, cookies, authority or hop-by-hop headers are trusted.
        for (const name of REQUEST_HEADERS) {
            if (req.headers[name] !== undefined && !connectionHeaders.has(name)) headers[name] = req.headers[name];
        }
        const body = Buffer.isBuffer(req.body) ? req.body : Buffer.alloc(0);
        headers["content-length"] = body.length;
        const separator = req.originalUrl.indexOf("?");
        const path = separator < 0 ? req.originalUrl : req.originalUrl.slice(0, separator);
        const query = separator < 0 ? "" : req.originalUrl.slice(separator);
        // Canonicalize a trailing slash locally, avoiding redirects to internal hosts.
        const upstreamPath = path.replace(/\/$/, "") + query;
        let upstreamResponse;
        let failed = false;
        let timer;

        const fail = (status, detail) => {
            if (failed || res.writableEnded || res.destroyed) return;
            failed = true;
            clearTimeout(timer);
            upstreamResponse?.destroy();
            upstream.destroy();
            if (res.headersSent) {
                res.destroy(); // A partial upstream response cannot become valid JSON.
            } else {
                for (const name of RESPONSE_HEADERS) res.removeHeader(name);
                res.status(status).json({ detail });
            }
        };
        const upstream = transport.request(origin, {
            path: upstreamPath, method: req.method, headers,
        }, (response) => {
            upstreamResponse = response;
            // The CRUD contract has no redirects. Never follow them or leak an internal URL.
            if (response.statusCode >= 300 && response.statusCode < 400) {
                fail(502, "Invalid KMS response");
                return;
            }
            res.status(response.statusCode);
            const responseConnectionHeaders = new Set((response.headers.connection || "").toLowerCase().split(",").map(s => s.trim()));
            for (const name of RESPONSE_HEADERS) {
                if (response.headers[name] !== undefined && !responseConnectionHeaders.has(name)) res.setHeader(name, response.headers[name]);
            }
            response.on("error", () => fail(502, "KMS unavailable"));
            response.on("end", () => clearTimeout(timer));
            response.pipe(res);
        });
        upstream.on("error", () => fail(502, "KMS unavailable"));
        // Absolute deadline includes connection establishment and response body transfer.
        timer = setTimeout(() => fail(504, "KMS request timed out"), timeoutMs);
        res.on("close", () => {
            clearTimeout(timer);
            upstreamResponse?.destroy();
            upstream.destroy();
        });
        upstream.end(body);
    };
}

module.exports = { createKmsProxy };
