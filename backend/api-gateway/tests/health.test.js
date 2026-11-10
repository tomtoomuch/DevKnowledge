const app = require("../src/app");
const request = require("supertest");


describe("GET /health", () => {
    it("retourne un statut 200 et confirme que la passerelle fonctionne", async () => {
        const response = await request(app).get("/health");

        expect(response.statusCode).toBe(200);
        expect(response.body).toEqual({
            status: "ok",
            service: "api-gateway",
        });
    });

    it("retourne 404 pour une route inexistante", async () => {
        const response = await request(app).get("/api/route-inconnue");

        expect(response.statusCode).toBe(404);
    });
});

describe("Gateway probes Angular only through a fixed DMZ route", () => {
    it("returns 200 when the DMZ frontend health probe succeeds", async () => {
        const { createApp } = require("../src/app");
        const app = createApp({ frontendProbe: async () => true });
        const response = await request(app).get("/health/frontend").expect(200);
        expect(response.body).toEqual({ status: "ok", service: "frontend" });
        expect(response.headers["cache-control"]).toBe("no-store");
    });
    it("returns 503 when Nginx is unreachable instead of inventing health", async () => {
        const { createApp } = require("../src/app");
        const app = createApp({ frontendProbe: async () => false });
        const response = await request(app).get("/health/frontend").expect(503);
        expect(response.body).toEqual({ status: "error", service: "frontend" });
    });
});
