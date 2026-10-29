const app = require("./app");

const PORT = process.env.GATEWAY_PORT || 3000;

const server = app.listen(PORT, "127.0.0.1", () => {
    console.log(`API Gateway démarrée sur http://127.0.0.1:${PORT}`);
});

function shutdown() {
    server.close(() => {
        process.exit(0);
    });
}

process.on("SIGINT", shutdown);
process.on("SIGTERM", shutdown);