from fastapi import FastAPI
app = FastAPI(
    title="Knowledge Management System",
    description="Service local de gestion des connaissances de DevKnowledge/BrainBlox",
    version="0.1.0",
)

@app.get("/health", tags=["Health"])
def health_check() -> dict[str, str]:
    return {
        "status":"ok",
        "service":"api-kms"
    }