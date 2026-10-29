"""Stable error codes, exception type, and the public error envelope."""
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from fastapi import FastAPI
from fastapi.testclient import TestClient

from gateway import errors


class ErrorTests(unittest.TestCase):
    def test_error_codes_map_to_documented_statuses(self):
        self.assertEqual(errors.GatewayError("context_limit_exceeded", "Too large.").status_code, 400)
        self.assertEqual(errors.GatewayError("quota_exceeded", "Out of credits.").status_code, 429)
        self.assertEqual(errors.GatewayError("model_unavailable", "Offline.").status_code, 503)
        self.assertEqual(errors.GatewayError("model_timeout", "Slow.").status_code, 504)
        self.assertEqual(errors.GatewayError("model_not_found", "Unknown.").status_code, 404)
        self.assertEqual(errors.GatewayError("totally_unknown", "Nope.").status_code, 500)

    def test_error_payload_keeps_code_message_and_details(self):
        failure = errors.context_limit_exceeded("Too large.", {"input_tokens": 40})
        self.assertEqual(failure.code, "context_limit_exceeded")
        self.assertEqual(failure.details, {"input_tokens": 40})

    def test_exception_handler_returns_stable_envelope(self):
        app = FastAPI()
        app.add_exception_handler(errors.GatewayError, errors.gateway_error_handler)

        @app.get("/boom")
        def boom():
            raise errors.quota_exceeded("Out of credits.")

        client = TestClient(app)
        response = client.get("/boom")
        self.assertEqual(response.status_code, 429)
        body = response.json()
        self.assertEqual(body["error"]["code"], "quota_exceeded")
        self.assertEqual(body["error"]["message"], "Out of credits.")
        self.assertNotIn("details", body["error"])
        self.assertIn("request_id", body)

    def test_exception_handler_echoes_request_id(self):
        app = FastAPI()
        app.add_exception_handler(errors.GatewayError, errors.gateway_error_handler)

        @app.get("/boom")
        def boom():
            raise errors.invalid_request("Bad payload.")

        client = TestClient(app)
        response = client.get("/boom", headers={"X-Request-ID": "req-42"})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["request_id"], "req-42")
        self.assertEqual(response.json()["error"]["code"], "invalid_request")


if __name__ == "__main__":
    unittest.main()
