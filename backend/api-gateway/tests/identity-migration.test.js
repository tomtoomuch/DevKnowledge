const http = require("node:http");
const request = require("supertest");
const { createApp } = require("../src/app");
const principal = { user_id: "51c22a76-2fee-4820-aa99-22094e0b85df", username: "reader",
  roles: ["READER"], permissions: ["knowledge.read"] };
const cookie = "dk_session=" + "c".repeat(64);
const key = "a".repeat(64);
let supervisor, kms, app, kmsCalls, identityCalls;
beforeEach(async () => {
  kmsCalls = []; identityCalls = [];
  kms = http.createServer((req, res) => {
    kmsCalls.push({ path: req.url, headers: req.headers });
    res.writeHead(200, { "content-type": "application/json" }).end('{"items":[]}');
  });
  supervisor = http.createServer((req, res) => {
    identityCalls.push({ path: req.url, headers: req.headers });
    expect(req.headers["x-service-key"]).toBe(key);
    res.setHeader("content-type", "application/json");
    if (req.url === "/internal/v1/auth/login") return res.end(JSON.stringify({ principal, session_token: "c".repeat(64) }));
    if (req.url === "/internal/v1/sessions/authorize") return res.end(JSON.stringify({ principal, kms_token: "header.payload.signature" }));
    if (req.url === "/internal/v1/auth/logout") return res.writeHead(204).end();
    return res.end(JSON.stringify(principal));
  });
  await Promise.all([new Promise(resolve => kms.listen(0, "127.0.0.1", resolve)),
    new Promise(resolve => supervisor.listen(0, "127.0.0.1", resolve))]);
  app = createApp({ kmsBaseUrl: "http://127.0.0.1:" + kms.address().port,
    supervisorBaseUrl: "http://127.0.0.1:" + supervisor.address().port,
    identityAuthority: "supervisor", supervisorKey: key, cookieSecure: true });
});
afterEach(async () => {
  for (const server of [supervisor, kms]) { server.closeAllConnections(); await new Promise(resolve => server.close(resolve)); }
});
test("KMS receives only the Supervisor token, never cookies or browser identity headers", async () => {
  await request(app).get("/api/v1/knowledges").set("Cookie", cookie + "; tracking=private")
    .set("Authorization", "Bearer forged").set("X-Service-Key", "forged").set("X-User-Id", "forged").expect(200);
  expect(kmsCalls).toHaveLength(1);
  expect(kmsCalls[0].headers.authorization).toBe("Bearer header.payload.signature");
  for (const name of ["cookie", "x-service-key", "x-user-id"]) expect(kmsCalls[0].headers[name]).toBeUndefined();
  expect(identityCalls[0].headers.cookie).toBeUndefined();
});
test("login token becomes only a scoped secure HttpOnly cookie; identity routes never reach KMS", async () => {
  const login = await request(app).post("/api/v1/auth/login").send({ username: "reader", password: "password" }).expect(200);
  expect(login.body).toEqual(principal);
  expect(login.headers["set-cookie"][0]).toContain("Path=/api/v1; Max-Age=28800; HttpOnly; SameSite=Strict; Secure");
  await request(app).get("/api/v1/auth/me").set("Cookie", cookie).expect(200);
  await request(app).get("/api/v1/users").set("Cookie", cookie).expect(200);
  await request(app).post("/api/v1/auth/logout").set("Cookie", cookie).send({}).expect(204);
  expect(kmsCalls).toEqual([]);
  expect(identityCalls.map(call => call.path)).toEqual(["/internal/v1/auth/login", "/internal/v1/auth/me", "/internal/v1/users", "/internal/v1/auth/logout"]);
});
test("Supervisor outage never falls back to legacy KMS identity", async () => {
  supervisor.closeAllConnections();
  await new Promise(resolve => supervisor.close(resolve));
  await request(app).get("/api/v1/knowledges").set("Cookie", cookie).expect(503);
  await request(app).get("/api/v1/auth/me").set("Cookie", cookie).expect(503);
  expect(kmsCalls).toEqual([]);
});
