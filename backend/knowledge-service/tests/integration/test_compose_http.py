"""Exercise the actual uvicorn container and its configured lifespan."""

import os
from uuid import UUID

import httpx2 as httpx
import pytest


pytestmark = pytest.mark.integration


def test_running_compose_service_crud():
    url = os.getenv("KMS_TEST_HTTP_URL")
    if not url:
        pytest.skip("Set KMS_TEST_HTTP_URL for the disposable Compose service")
    if url != "http://api-kms-test:8000":
        pytest.fail("KMS_TEST_HTTP_URL must target the disposable Compose service http://api-kms-test:8000")
    with httpx.Client(base_url=url, timeout=10) as client:
        assert client.get("/health").status_code == 200
        assert client.get("/health/ready").status_code == 200
        contract = client.get("/openapi.json").json()
        assert set(contract["paths"]["/api/v1/knowledges"]) == {"get", "post"}
        response = client.post("/api/v1/knowledges", json={
            "knowledge_type": "TERMINAL_COMMAND", "title": "Compose smoke test",
            "content": "docker compose ps", "language_code": "en",
        })
        assert response.status_code == 201, response.text
        item = response.json()
        identifier = item["knowledge_id"]
        assert UUID(identifier).version == 4
        path = f"/api/v1/knowledges/{identifier}"
        try:
            assert client.get(path).json() == item
            assert client.patch(path, headers={"If-Match": '"1"'}, json={"is_favorite": True}).json()["is_favorite"] is True
            page = client.get("/api/v1/knowledges", params={
                "knowledge_type": "TERMINAL_COMMAND", "status": "DRAFT", "limit": 100,
            }).json()
            assert identifier in {entry["knowledge_id"] for entry in page["items"]}
            assert client.delete(path, headers={"If-Match": '"2"'}).status_code == 204
            assert client.get(path).status_code == 404
            assert client.delete(path, headers={"If-Match": '"2"'}).status_code == 404
            assert identifier not in {entry["knowledge_id"] for entry in client.get("/api/v1/knowledges").json()["items"]}
        finally:
            client.delete(path, headers={"If-Match": '"2"'})
