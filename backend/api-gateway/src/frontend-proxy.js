"use strict";

const http = require("node:http");
const https = require("node:https");

// Only static assets/SPA navigation flow through this reverse proxy.
// Never forward browser credentials, identity headers, host or cookies to Nginx.
const REQUEST_HEADERS = [
    "accept", "accept-encoding", "if-none-match", "if-modified-since", "range", "if-range",
];
const RESPONSE_HEADERS = [
    "content-type", "content-length", "content-encoding", "cache-control",
    "etag", "last-modified", "vary", "accept-ranges", "content-range", "expires",
];

function createFrontendProxy(baseUrl, timeoutMs) {
    let origin;
    try {
        origin = new URL(baseUrl);
    } catch {
        throw new Error("FRONTEND_BASE_URL must be a private HTTP(S) origin");
    }
    if (!["http:", "https:"].includes(origin.protocol) || origin.username ||
        origin.password || origin.pathname !== "/" || origin.search || origin.hash ||
        !Number.isInteger(timeoutMs) || timeoutMs < 1 || timeoutMs > 60000) {
        throw new Error("Invalid FRONTEND_BASE_URL or proxy timeout");
    }
    const transport = origin.protocol === "https:" ? https : http;

    return function relayFrontend(req, res) {
        if (!["GET", "HEAD"].includes(req.method)) {
            return res.status(405).json({ detail: "Read-only frontend" });
        }
        const target = req.originalUrl;
        // Do not turn //evil into a protocol-relative destination, and do not
        // allow a malformed authority or request line to leak upstream.
        if (!target.startsWith("/") || target.startsWith("//") || /[\r\n\x00]/.test(target)) {
            return res.status(400).json({ detail: "Invalid frontend path" });
        }
        const headers = { host: origin.host };
        for (const name of REQUEST_HEADERS) {
            if (typeof req.headers[name] === "string") headers[name] = req.headers[name];
        }
        let source;
        let failed = false;
        let timeout;
        const fail = (status) => {
            if (failed || res.destroyed || res.writableEnded) return;
            failed = true;
            clearTimeout(timeout);
            source?.destroy();
            upstream.destroy();
            if (res.headersSent) return res.destroy();
            res.status(status).json({ detail: status === 504
                ? "Frontend timed out" : "Frontend unavailable" });
        };
        const upstream = transport.request(origin, {
            method: req.method, path: target, headers,
        }, response => {
            source = response;
            // Nginx should never redirect the browser off the Gateway.
            if (response.statusCode >= 300 && response.statusCode < 400 && response.statusCode !== 304) {
                response.resume();
                return fail(502);
            }
            res.status(response.statusCode);
            for (const name of RESPONSE_HEADERS) {
                if (response.headers[name] !== undefined) {
                    res.setHeader(name, response.headers[name]);
                }
            }
            response.on("error", () => fail(502));
            response.on("end", () => clearTimeout(timeout));
            response.pipe(res);
        });
        upstream.on("error", () => fail(502));
        timeout = setTimeout(() => fail(504), timeoutMs);
        res.on("close", () => {
            clearTimeout(timeout);
            source?.destroy();
            upstream.destroy();
        });
        upstream.end();
    };
}

module.exports = { createFrontendProxy };
