const http = require("node:http");
const request = require("supertest");
const { createApp } = require("../src/app");
const { permissionFor } = require("../src/session-auth");

const UUID = "40000000-0000-0000-0000-000000000002";
const COOKIE = "dk_session=" + "a".repeat(64);

test("RNCP scope follows KMS read/create permission mapping", () => {
    expect(permissionFor("/rncp/frameworks/RNCP-TEST/versions/v1", "GET"))
        .toBe("knowledge.read");
    expect(permissionFor("/rncp/competencies/" + UUID + "/evidence", "POST"))
        .toBe("knowledge.create");
    expect(permissionFor("/rncp/competencies/" + UUID + "/knowledge-links", "POST"))
        .toBe("knowledge.create");
});

test("RNCP only relays registered routes after session RBAC checks", async () => {
    const seen = [];
    const upstream = http.createServer((req, res) => {
        seen.push(req.url);
        res.writeHead(req.method === "POST" ? 201 : 200, {"Content-Type": "application/json"});
        res.end("{}");
    });
    await new Promise(resolve => upstream.listen(0, "127.0.0.1", resolve));
    try {
        const base = "http://127.0.0.1:" + upstream.address().port;
        const lookup = async cookie => cookie === COOKIE ? {
            user_id: "40000000-0000-0000-0000-000000000099",
            username: "reader", roles: ["READER"], permissions: ["knowledge.read"],
        } : null;
        const app = createApp({kmsBaseUrl: base, kmsTimeoutMs: 1000, sessionLookup: lookup});
        const url = "/api/v1/rncp/competencies/" + UUID + "/evidence";
        await request(app).get(url).expect(401);
        await request(app).get(url).set("Cookie", COOKIE).expect(200);
        await request(app).post(url).set("Cookie", COOKIE).send({title:"bad"}).expect(403);
        await request(app).get(url.replace("/evidence","/unlisted")).set("Cookie", COOKIE).expect(404);
        expect(seen).toEqual([url]);
        const writer = createApp({kmsBaseUrl: base, kmsTimeoutMs: 1000,
            sessionLookup: async cookie => cookie === COOKIE ? {
                user_id: "40000000-0000-0000-0000-000000000099",
                username: "editor", roles: ["EDITOR"],
                permissions: ["knowledge.read","knowledge.create"],
            } : null,
        });
        await request(writer).post(url).set("Cookie",COOKIE)
            .send({title:"fake"}).expect(201);
        await request(writer).post("/api/v1/rncp/competencies/" + UUID + "/knowledge-links")
            .set("Cookie",COOKIE).send({knowledge_id: UUID}).expect(201);
        expect(seen).toEqual([url, url,
            "/api/v1/rncp/competencies/" + UUID + "/knowledge-links"]);
    } finally {
        upstream.closeAllConnections();
        await new Promise(resolve => upstream.close(resolve));
    }
});
