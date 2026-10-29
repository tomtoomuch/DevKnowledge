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
        const response = await request(app).get("/route-inconnue");

        expect(response.statusCode).toBe(404);
    });
});