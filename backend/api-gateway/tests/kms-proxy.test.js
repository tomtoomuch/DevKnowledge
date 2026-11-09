const http = require("node:http");
const request = require("supertest");
const { createApp } = require("../src/app");

let server, origin, app, received, respond;
beforeEach(async () => {
    received = [];
    respond = (req, res) => res.end("{}");
    server = http.createServer((req, res) => {
        const chunks = [];
        req.on("data", chunk => chunks.push(chunk));
        req.on("end", () => {
            received.push({ method: req.method, url: req.url, headers: req.headers,
                body: Buffer.concat(chunks).toString() });
            respond(req, res);
        });
    });
    await new Promise(resolve => server.listen(0, "127.0.0.1", resolve));
    origin = `http://127.0.0.1:${server.address().port}`;
    app = createApp({ kmsBaseUrl: origin, kmsTimeoutMs: 1000 });
});
afterEach(async () => {
    server.closeAllConnections();
    await new Promise(resolve => server.close(resolve));
});

test.each(["get", "post", "patch", "delete"])("relays %s method, query and raw bytes", async method => {
    const path = "/api/v1/knowledges/abc-123?status=DRAFT&skip=2&limit=3";
    const body = method === "post" || method === "patch" ? '{ "title": "café" }' : "";
    await request(app)[method](path).set("Content-Type", "application/json").send(body).expect(200);
    expect(received).toHaveLength(1);
    expect(received[0]).toMatchObject({ method: method.toUpperCase(), url: path, body });
});

test.each([200, 201, 204, 404, 405, 422, 503])("preserves upstream status %s and body", async status => {
    respond = (req, res) => {
        res.writeHead(status, { "content-type": "application/json", "retry-after": "3", "allow": "GET" });
        res.end(status === 204 ? "" : '{"detail":"upstream result"}');
    };
    const response = await request(app).get("/api/v1/knowledges");
    expect(response.status).toBe(status);
    expect(response.text).toBe(status === 204 ? "" : '{"detail":"upstream result"}');
    expect(response.headers["retry-after"]).toBe("3");
    expect(response.headers.allow).toBe("GET");
});

test("leaves JSON validation to KMS", async () => {
    respond = (req, res) => res.writeHead(422).end("invalid JSON from KMS");
    const response = await request(app).post("/api/v1/knowledges")
        .set("Content-Type", "application/json").send('{"broken":');
    expect(response.status).toBe(422);
    expect(received[0].body).toBe('{"broken":');
});

test("relays If-Match and ETag for conditional writes", async () => {
    respond = (req, res) => res.writeHead(412, { "etag": '"2"', "cache-control": "no-store" }).end();
    const response = await request(app).patch("/api/v1/knowledges/abc")
        .set("If-Match", '"1"').send({ title: "stale" }).expect(412);
    expect(received[0].headers["if-match"]).toBe('"1"');
    expect(response.headers.etag).toBe('"2"');
    expect(response.headers["cache-control"]).toBe("no-store");
});

test("does not relay identity, credentials, forwarding or hop-by-hop headers", async () => {
    respond = (req, res) => res.writeHead(200, {
        "content-type": "application/json", "set-cookie": "secret=bad",
        "x-internal-token": "private", "connection": "close",
    }).end("{}");
    const response = await request(app).get("/api/v1/knowledges")
        .set("Authorization", "Bearer untrusted").set("Cookie", "session=untrusted")
        .set("X-User-Id", "spoofed").set("X-Forwarded-Host", "evil.invalid")
        .set("Forwarded", "for=evil").set("Host", "evil.invalid");
    const headers = received[0].headers;
    for (const name of ["authorization", "cookie", "x-user-id", "x-forwarded-host", "forwarded"]) {
        expect(headers[name]).toBeUndefined();
    }
    expect(headers.host).toBe(new URL(origin).host);
    expect(response.headers["set-cookie"]).toBeUndefined();
    expect(response.headers["x-internal-token"]).toBeUndefined();
});

test.each(["/docs", "/openapi.json", "/api/v1/knowledges-other", "/api/v1/knowledges/id/extra",
    "/api/v1/knowledges/%2e%2e/docs", "/api/v1/knowledges/%2F%2Fevil.invalid"])(
    "does not proxy unrelated path %s", async path => {
        await request(app).get(path).expect(404);
        expect(received).toHaveLength(0);
    });

test("normalizes the trailing slash without redirecting to an internal host", async () => {
    await request(app).get("/api/v1/knowledges/?limit=1").expect(200);
    expect(received[0].url).toBe("/api/v1/knowledges?limit=1");
});

test("removes headers nominated by Connection in both directions", async () => {
    respond = (req, res) => res.writeHead(200, {
        connection: "retry-after", "retry-after": "5", "content-type": "application/json",
    }).end("{}");
    const response = await request(app).get("/api/v1/knowledges")
        .set("Connection", "accept-language").set("Accept-Language", "fr");
    expect(received[0].headers["accept-language"]).toBeUndefined();
    expect(response.headers["retry-after"]).toBeUndefined();
});

test("does not follow upstream redirects or disclose their location", async () => {
    respond = (req, res) => res.writeHead(307, { location: "http://private.internal/secret" }).end();
    const response = await request(app).get("/api/v1/knowledges").expect(502);
    expect(response.body).toEqual({ detail: "Invalid KMS response" });
    expect(response.headers.location).toBeUndefined();
    expect(received).toHaveLength(1);
});

test("rejects oversized requests before contacting KMS", async () => {
    const response = await request(app).post("/api/v1/knowledges")
        .set("Content-Type", "application/json").send("x".repeat(1024 * 1024 + 1)).expect(413);
    expect(response.body).toEqual({ detail: "Request body too large" });
    expect(received).toHaveLength(0);
});

test("rejects compressed requests explicitly", async () => {
    await request(app).post("/api/v1/knowledges").set("Content-Encoding", "gzip").send("x").expect(415);
    expect(received).toHaveLength(0);
});

test("unavailable KMS returns 502 without connection details; liveness still works", async () => {
    await new Promise(resolve => server.close(resolve));
    const response = await request(app).get("/api/v1/knowledges").expect(502);
    expect(response.body).toEqual({ detail: "KMS unavailable" });
    expect(response.text).not.toContain(origin);
    await request(app).get("/health").expect(200);
    await request(app).get("/health/ready").expect(502);
});

test("a hanging KMS times out with no retry of a write", async () => {
    respond = () => {}; // Leave headers pending until the proxy destroys the request.
    const fastApp = createApp({ kmsBaseUrl: origin, kmsTimeoutMs: 50 });
    const response = await request(fastApp).post("/api/v1/knowledges").send({ title: "test" }).expect(504);
    expect(response.body).toEqual({ detail: "KMS request timed out" });
    expect(received).toHaveLength(1);
});

test("readiness follows KMS status independently of Gateway liveness", async () => {
    respond = (req, res) => res.writeHead(503, { "content-type": "application/json" })
        .end('{"dependency":"mongodb"}');
    await request(app).get("/health").expect(200);
    const response = await request(app).get("/health/ready").expect(503);
    expect(response.body).toEqual({ dependency: "mongodb" });
    expect(received[0].url).toBe("/health/ready");
});

test("client disconnection closes the upstream request", async () => {
    let disconnected;
    const closed = new Promise(resolve => { disconnected = resolve; });
    respond = (req, res) => res.on("close", disconnected);
    const gateway = app.listen(0, "127.0.0.1");
    await new Promise(resolve => gateway.once("listening", resolve));
    try {
        const client = http.get(`http://127.0.0.1:${gateway.address().port}/api/v1/knowledges`);
        client.on("error", () => {});
        while (!received.length) await new Promise(resolve => setTimeout(resolve, 5));
        client.destroy();
        await closed;
    } finally {
        gateway.closeAllConnections();
        await new Promise(resolve => gateway.close(resolve));
    }
});

test("a stalled response body is interrupted at the absolute deadline", async () => {
    respond = (req, res) => {
        res.writeHead(200, { "content-type": "application/json" });
        res.write('{"partial":');
    };
    const fastApp = createApp({ kmsBaseUrl: origin, kmsTimeoutMs: 50 });
    await expect(request(fastApp).get("/api/v1/knowledges")).rejects.toThrow();
});

test("an upstream connection reset returns 502", async () => {
    respond = req => req.socket.destroy();
    const response = await request(app).get("/api/v1/knowledges").expect(502);
    expect(response.body).toEqual({ detail: "KMS unavailable" });
});

test.each(["not-a-url", "ftp://localhost", "http://user:password@localhost", "http://localhost/path",
    "http://localhost?target=evil", "http://localhost/#fragment"])("rejects unsafe upstream configuration %s", url => {
    expect(() => createApp({ kmsBaseUrl: url })).toThrow(/KMS_BASE_URL/);
});
test.each([0, -1, NaN, 1.5, 60001])("rejects invalid timeout %s", timeout => {
    expect(() => createApp({ kmsTimeoutMs: timeout })).toThrow(/KMS_TIMEOUT_MS/);
});

test("forwards only the valid dk_session token and not unrelated cookies", async () => {
    const token = "a".repeat(64);
    await request(app).get("/api/v1/knowledges")
        .set("Cookie", "tracking=123; dk_session=" + token + "; another=irrelevant").expect(200);
    expect(received[0].headers.cookie).toBe("dk_session=" + token);
    await request(app).get("/api/v1/knowledges")
        .set("Cookie", "dk_session=" + token + "; dk_session=" + token).expect(200);
    expect(received[1].headers.cookie).toBeUndefined();
});

test("relays auth routes and scoped session Set-Cookie only there", async () => {
    respond = (req, res) => res.writeHead(200, {
        "Content-Type": "application/json",
        "Set-Cookie": "dk_session=" + "b".repeat(64) +
            "; Path=/api/v1; HttpOnly; SameSite=Strict",
    }).end('{"username":"admin"}');
    const login = await request(app).post("/api/v1/auth/login")
        .send({ username: "admin", password: "test" }).expect(200);
    expect(received[0].url).toBe("/api/v1/auth/login");
    expect(login.headers["set-cookie"][0]).toContain("HttpOnly");
    const me = await request(app).get("/api/v1/auth/me").expect(200);
    expect(me.headers["set-cookie"]).toBeUndefined();
    const knowledge = await request(app).get("/api/v1/knowledges").expect(200);
    expect(knowledge.headers["set-cookie"]).toBeUndefined();
});

test("blocks cross-origin writes and allows same-origin writes", async () => {
    await request(app).post("/api/v1/auth/login")
        .set("Origin", "https://evil.example")
        .send({ username: "admin" }).expect(403);
    await request(app).patch("/api/v1/knowledges/abc")
        .set("Sec-Fetch-Site", "cross-site").send({ title: "bad" }).expect(403);
    await request(app).post("/api/v1/auth/login")
        .set("Origin", "https://example.local").set("Host", "example.local")
        .send({ username: "admin" }).expect(403);
    expect(received).toHaveLength(0);
    await request(app).post("/api/v1/auth/login")
        .set("Origin", "http://example.local")
        .set("Host", "example.local").send({ username: "admin" }).expect(200);
    expect(received).toHaveLength(1);
});

test("throttles repeated login attempts", async () => {
    for (let n = 0; n < 10; n++) {
        await request(app).post("/api/v1/auth/login").send({ username: "x" }).expect(200);
    }
    const result = await request(app).post("/api/v1/auth/login")
        .send({ username: "x" }).expect(429);
    expect(result.headers["retry-after"]).toBe("60");
    expect(received).toHaveLength(10);
});


test("forwards only GET on the knowledge type catalog", async () => {
    respond = (req, res) => res.writeHead(200, {"content-type": "application/json"})
        .end('[{"code":"CODE_SNIPPET"}]');
    const response = await request(app).get("/api/v1/knowledge-types").expect(200);
    expect(response.body).toEqual([{code: "CODE_SNIPPET"}]);
    expect(received[0].url).toBe("/api/v1/knowledge-types");
    await request(app).post("/api/v1/knowledge-types").send({code:"EVIL"}).expect(404);
    expect(received).toHaveLength(1);
});


test("relays tag catalog read/create and lookup without exposing unrelated routes", async () => {
    await request(app).get("/api/v1/tags?skip=0&limit=50").expect(200);
    expect(received[0].url).toBe("/api/v1/tags?skip=0&limit=50");
    await request(app).post("/api/v1/tags")
        .set("Content-Type", "application/json").send({ name: "MongoDB" }).expect(200);
    expect(received[1].method).toBe("POST");
    expect(JSON.parse(received[1].body)).toEqual({ name: "MongoDB" });
    await request(app).get("/api/v1/tags/abcd-1234").expect(200);
    expect(received[2].url).toBe("/api/v1/tags/abcd-1234");
    await request(app).put("/api/v1/tags").send({ name: "Non" }).expect(404);
    await request(app).delete("/api/v1/tags/abcd-1234").expect(404);
    expect(received).toHaveLength(3);
});

test("monitoring is a read-only same-origin Gateway route with scoped authentication", async () => {
    respond = (req, res) => res.writeHead(200, {
        "content-type": "application/json", "cache-control": "no-store",
    }).end(JSON.stringify({ checked_at: "2026-11-10T00:00:00Z", services: [] }));
    const session = "c".repeat(64);
    const response = await request(app).get("/api/v1/monitoring/services")
        .set("Cookie", "other=ignored; dk_session=" + session).expect(200);
    expect(response.body.services).toEqual([]);
    expect(response.headers["cache-control"]).toBe("no-store");
    expect(received[0].url).toBe("/api/v1/monitoring/services");
    expect(received[0].headers.cookie).toBe("dk_session=" + session);
    await request(app).post("/api/v1/monitoring/services").send({}).expect(404);
    expect(received).toHaveLength(1);
});
