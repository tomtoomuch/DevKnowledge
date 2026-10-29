const express = require("express");
const app = express();

app.use(express.json());

// Vérification de santé de l'API
app.get("/health", (req, res) => {
    res.status(200).json({
        status: "ok",
        service: "api-gateway",
    });
});

module.exports = app;