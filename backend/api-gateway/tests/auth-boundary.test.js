const http = require("node:http");
const request = require("supertest");
const { createApp } = require("../src/app");

let server, app, calls, result;
beforeEach(async () => {
    calls = [];
    result = (req, res) => res.writeHead(200, { "Content-Type": "application/json" })
        .end(JSON.stringify({ user_id: "abc", username: "admin", roles: ["ADMIN"],
            permissions: ["knowledge.read", "knowledge.create", "users.manage"] }));
    server = http.createServer((req, res) => {
        calls.push(req.url);
        result(req, res);
    });
    await new Promise(resolve => server.listen(0, "127.0.0.1", resolve));
    app = createApp({ kmsBaseUrl: "http://127.0.0.1:" + server.address().port,
        kmsTimeoutMs: 1000 });
});
afterEach(async () => {
    server.closeAllConnections();
    await new Promise(resolve => server.close(resolve));
});

test("Gateway rejects requests without cookies before any call to KMS", async () => {
    await request(app).get("/api/v1/knowledges").expect(401);
    await request(app).get("/api/v1/auth/me").expect(401);
    await request(app).get("/api/v1/monitoring/services").expect(401);
    expect(calls).toEqual([]);
});
test("Gateway introspects a valid session and enforces read permissions", async () => {
    const cookie = "dk_session=" + "a".repeat(64);
    const me = await request(app).get("/api/v1/auth/me").set("Cookie", cookie).expect(200);
    expect(me.body.username).toBe("admin");
    expect(calls).toEqual(["/api/v1/auth/me"]);
    calls = [];
    await request(app).get("/api/v1/monitoring/services").set("Cookie", cookie).expect(200);
    expect(calls).toEqual(["/api/v1/auth/me", "/api/v1/monitoring/services"]);
});
test("Gateway refuses duplicated or malformed cookies", async () => {
    await request(app).get("/api/v1/knowledges")
        .set("Cookie", "dk_session=garbage").expect(401);
    await request(app).get("/api/v1/knowledges")
        .set("Cookie", "dk_session=" + "a".repeat(64) + "; dk_session=" + "b".repeat(64))
        .expect(401);
    expect(calls).toEqual([]);
});
test("Gateway fails closed on an invalid or expired session", async () => {
    result = (req, res) => res.writeHead(401).end(JSON.stringify({detail:"Authentication required"}));
    await request(app).get("/api/v1/knowledges")
        .set("Cookie", "dk_session=" + "a".repeat(64)).expect(401);
    expect(calls).toEqual(["/api/v1/auth/me"]);
});
test("Gateway protects permissions on user management and writes", async () => {
    result = (req, res) => res.writeHead(200, {"Content-Type":"application/json"})
        .end(JSON.stringify({ user_id:"abc", username:"reader", roles:["READER"],
            permissions:["knowledge.read"] }));
    const cookie = "dk_session=" + "c".repeat(64);
    await request(app).post("/api/v1/knowledges").set("Cookie",cookie)
        .send({ title:"denied" }).expect(403);
    await request(app).get("/api/v1/users").set("Cookie", cookie).expect(403);
    expect(calls).toEqual(["/api/v1/auth/me", "/api/v1/auth/me"]);
});
test("Gateway rejects an inaccessible identity backend without allowing access", async () => {
    result = (req, res) => res.writeHead(503).end();
    const response = await request(app).get("/api/v1/knowledges")
        .set("Cookie", "dk_session=" + "a".repeat(64)).expect(503);
    expect(response.body.detail).toBe("Session verification unavailable");
    expect(calls).toEqual(["/api/v1/auth/me"]);
});
test("Gateway allows the public login POST and handles logout without a session", async () => {
    await request(app).post("/api/v1/auth/login").send({username:"admin",password:"secret"}).expect(200);
    await request(app).post("/api/v1/auth/logout").send({}).expect(200);
    expect(calls).toEqual(["/api/v1/auth/login", "/api/v1/auth/logout"]);
});


test("Gateway guards every user CRUD subroute and relays revision preconditions", async () => {
    const cookie = "dk_session=" + "a".repeat(64);
    const id = "a607237e-9050-4992-88b5-34c36b46d044";
    const path = "/api/v1/users/" + id;
    await request(app).get(path).set("Cookie", cookie).expect(200);
    await request(app).patch(path).set("Cookie", cookie).set("If-Match", '"1"')
        .send({roles: ["EDITOR"]}).expect(200);
    await request(app).post(path + "/password").set("Cookie", cookie).set("If-Match", '"2"')
        .send({password: "strong-password-2026"}).expect(200);
    await request(app).delete(path).set("Cookie", cookie).set("If-Match", '"3"').expect(200);
    expect(calls.filter(url => url === "/api/v1/auth/me")).toHaveLength(4);
    expect(calls.filter(url => url.startsWith("/api/v1/users/"))).toEqual([
        path, path, path + "/password", path,
    ]);
    await request(app).put(path).set("Cookie", cookie).send({}).expect(404);
    expect(calls.filter(url => url === path)).toHaveLength(3);
});

test("Gateway blocks reader on all user CRUD operations", async () => {
    result = (req, res) => res.writeHead(200, {"Content-Type":"application/json"})
        .end(JSON.stringify({user_id:"reader",username:"reader",roles:["READER"],
            permissions:["knowledge.read"]}));
    const cookie = "dk_session=" + "b".repeat(64);
    const path = "/api/v1/users/a607237e-9050-4992-88b5-34c36b46d044";
    await request(app).get(path).set("Cookie", cookie).expect(403);
    await request(app).patch(path).set("Cookie", cookie).set("If-Match", '"1"')
        .send({roles:["ADMIN"]}).expect(403);
    await request(app).post(path + "/password").set("Cookie", cookie).set("If-Match", '"1"')
        .send({password:"strong-password-2026"}).expect(403);
    await request(app).delete(path).set("Cookie", cookie).set("If-Match", '"1"')
        .expect(403);
    expect(calls).toEqual(Array(4).fill("/api/v1/auth/me"));
});
