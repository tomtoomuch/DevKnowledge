const app = require("./app");

const PORT = process.env.GATEWAY_PORT || 3000;
const HOST = process.env.GATEWAY_HOST || "0.0.0.0";

const server = app.listen(PORT, HOST, () => {
    console.log(
        `API Gateway démarrée sur http://${HOST}:${PORT}`
    );
});

function shutdown() {
    server.close((error) => {
        if (error) {
            console.error("Erreur lors de l'arrêt du serveur :", error);
            process.exitCode = 1;
            return;
        }
        
        process.exit(0);
    });
}

process.on("SIGINT", shutdown);
process.on("SIGTERM", shutdown);