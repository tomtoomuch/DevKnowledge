"""The normal token-only service cannot accidentally mount identity routes."""
import json
import os
import subprocess
import sys


def test_token_only_app_removes_all_account_and_session_routes():
    environment = dict(os.environ, KMS_SERVICE_TOKEN_MODE="required", SUPERVISOR_KMS_TOKEN_KEY="b" * 64)
    result = subprocess.run([sys.executable, "-c",
        "import json; from app.main import app; print(json.dumps(list(app.openapi()['paths'])))"],
        env=environment, capture_output=True, text=True, check=True)
    paths = json.loads(result.stdout)
    assert not any(path.startswith(("/api/v1/auth", "/api/v1/users")) for path in paths)
    assert "/api/v1/knowledges" in paths


def test_token_only_app_refuses_missing_key_instead_of_falling_back():
    environment = dict(os.environ, KMS_SERVICE_TOKEN_MODE="required", SUPERVISOR_KMS_TOKEN_KEY="")
    result = subprocess.run([sys.executable, "-c", "from app.main import app"],
        env=environment, capture_output=True, text=True)
    assert result.returncode != 0
    assert "KMS service signing key is required" in result.stderr
