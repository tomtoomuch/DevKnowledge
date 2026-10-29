from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)

def test_health_returns_200() -> None:
# La route doit répondre avec un statut 200
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {
        "status":"ok",
        "service":"api-kms",
    }

def test_unknown_route_returns_404() -> None:
# Une route inexistante doit répondre avec le statut 404
    response = client.get("/route-inconnue")

    assert response.status_code == 404