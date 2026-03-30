"""
Unit tests for admin API key authentication.
"""

import os
import unittest
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from vhf.api.auth import require_api_key


# Minimal app that uses the dependency — avoids booting the full VHF app
# (which needs a live DB connection).
def _make_test_app() -> FastAPI:
    from fastapi import Depends
    app = FastAPI()

    @app.get("/protected")
    def protected(key: str = Depends(require_api_key)):
        return {"ok": True}

    return app


class RequireApiKeyTest(unittest.TestCase):

    def setUp(self):
        self.app = _make_test_app()
        self.client = TestClient(self.app, raise_server_exceptions=False)

    @patch.dict(os.environ, {"ADMIN_API_KEY": "secret123"})
    def test_valid_key_returns_200(self):
        resp = self.client.get("/protected", headers={"X-API-Key": "secret123"})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json(), {"ok": True})

    @patch.dict(os.environ, {"ADMIN_API_KEY": "secret123"})
    def test_missing_key_returns_401(self):
        resp = self.client.get("/protected")
        self.assertEqual(resp.status_code, 401)

    @patch.dict(os.environ, {"ADMIN_API_KEY": "secret123"})
    def test_wrong_key_returns_401(self):
        resp = self.client.get("/protected", headers={"X-API-Key": "wrongkey"})
        self.assertEqual(resp.status_code, 401)

    @patch.dict(os.environ, {"ADMIN_API_KEY": "secret123"})
    def test_empty_key_returns_401(self):
        resp = self.client.get("/protected", headers={"X-API-Key": ""})
        self.assertEqual(resp.status_code, 401)

    @patch.dict(os.environ, {}, clear=True)
    def test_no_env_var_returns_503(self):
        os.environ.pop("ADMIN_API_KEY", None)
        resp = self.client.get("/protected", headers={"X-API-Key": "anything"})
        self.assertEqual(resp.status_code, 503)

    @patch.dict(os.environ, {"ADMIN_API_KEY": "  "})
    def test_whitespace_only_env_var_returns_503(self):
        # Blank/whitespace key treated as not configured.
        resp = self.client.get("/protected", headers={"X-API-Key": "  "})
        self.assertEqual(resp.status_code, 503)

    @patch.dict(os.environ, {"ADMIN_API_KEY": "secret123"})
    def test_key_is_case_sensitive(self):
        resp = self.client.get("/protected", headers={"X-API-Key": "Secret123"})
        self.assertEqual(resp.status_code, 401)

    @patch.dict(os.environ, {"ADMIN_API_KEY": "secret123"})
    def test_401_response_has_detail(self):
        resp = self.client.get("/protected")
        body = resp.json()
        self.assertIn("detail", body)


if __name__ == "__main__":
    unittest.main()
