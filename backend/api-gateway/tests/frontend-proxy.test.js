"use strict";

const http = require("node:http");
const request = require("supertest");
const { createApp } = require("../src/app");

let server;
let app;
let requests;
let responder;

const authenticated = async () => ({
    user_id: "fixture", username: "admin", roles: ["ADMIN"],
    permissions: ["knowledge.read", "users.manage"],
});

beforeEach(async () => {
    requests = [];
    responder = (req, res) => {
        if (req.url === "/main.js") {
            res.writeHead(200, {
                "Content-Type": "application/javascript", "Cache-Control": "public, max-age=600",
            });
            return res.end("console.log('frontend');");
        }
        if (req.url === "/cached.js") {
            res.writeHead(304, { ETag: '"abc123"' });
            return res.end();
        }
        if (req.url === "/redirect") {
            res.writeHead(302, { Location: "https://example.invalid/" });
            return res.end();
        }
        if (req.url === "/unavailable") return req.socket.destroy();
        if (req.url === "/delayed") return;
        res.writeHead(200, { "Content-Type": "text/html; charset=utf-8" });
        return res.end("<!doctype html><html><body>DevKnowledge</body></html>");
    };
    server = http.createServer((req, res) => {
        requests.push({ method: req.method, url: req.url, headers: req.headers });
        responder(req, res);
    });
    await new Promise(resolve => server.listen(0, "127.0.0.1", resolve));
    app = createApp({
        frontendBaseUrl: "http://127.0.0.1:" + server.address().port,
        kmsBaseUrl: "http://127.0.0.1:65535",
        kmsTimeoutMs: 150,
        sessionLookup: authenticated,
    });
});

afterEach(async () => {
    server.closeAllConnections();
    await new Promise(resolve => server.close(resolve));
});

test("Gateway serves Angular root, SPA navigation and JS assets from private Nginx", async () => {
    const root = await request(app).get("/").expect(200);
    expect(root.text).toContain("DevKnowledge");
    const navigation = await request(app).get("/knowledge/123?tab=details").expect(200);
    expect(navigation.text).toContain("DevKnowledge");
    const asset = await request(app).get("/main.js").expect(200);
    expect(asset.headers["content-type"]).toBe("application/javascript");
    expect(asset.headers["cache-control"]).toBe("public, max-age=600");
    expect(requests.map(r => r.url)).toEqual(["/", "/knowledge/123?tab=details", "/main.js"]);
});

test("Gateway never leaks browser cookies, Authorization, Host or injected identity to Nginx", async () => {
    await request(app).get("/main.js")
        .set("Cookie", "dk_session=" + "a".repeat(64))
        .set("Authorization", "Bearer secret")
        .set("X-User-Id", "spoofed")
        .set("X-Forwarded-Host", "attacker.invalid")
        .set("Host", "attacker.invalid")
        .expect(200);
    const headers = requests[0].headers;
    for (const name of ["cookie", "authorization", "x-user-id", "x-forwarded-host"]) {
        expect(headers[name]).toBeUndefined();
    }
    expect(headers.host).toBe("127.0.0.1:" + server.address().port);
});

test("Gateway forwards safe caching headers and preserves 304 not-modified", async () => {
    await request(app).get("/cached.js").set("If-None-Match", '"abc123"')
        .expect(304);
    expect(requests[0].headers["if-none-match"]).toBe('"abc123"');
});

test("Unknown API and health paths never reach Nginx", async () => {
    await request(app).get("/api/not-a-real-api").expect(404);
    await request(app).get("/health/unknown").expect(404);
    await request(app).post("/some-angular-route").send({value: 1}).expect(404);
    expect(requests).toHaveLength(0);
});

test("Frontend redirects cannot bypass Gateway", async () => {
    const response = await request(app).get("/redirect").expect(502);
    expect(response.headers.location).toBeUndefined();
});

test("Frontend failures and timeouts return 502/504 without redirect", async () => {
    await request(app).get("/unavailable").expect(502);
    await request(app).get("/delayed").expect(504);
});

test("Private frontend is not permitted to set browser cookies", async () => {
    responder = (req, res) => {
        res.writeHead(200, { "Set-Cookie": "evil=1; Path=/", "Content-Type": "text/html" });
        res.end("<html></html>");
    };
    const response = await request(app).get("/").expect(200);
    expect(response.headers["set-cookie"]).toBeUndefined();
});
