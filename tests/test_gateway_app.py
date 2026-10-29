"""HTTP surface of the model gateway."""
from pathlib import Path
import sys
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from fastapi.testclient import TestClient

from gateway import adapters, app as gateway_app, auth, config, errors, quota, router as router_module


class FakeAdapter(adapters.Adapter):
    def __init__(self, model="org-model", version="7", context_window=256, capabilities=frozenset({adapters.CHAT})):
        self.model = model
        self.version = version
        self.context_window = context_window
        self.capabilities = frozenset(capabilities)

    def describe(self):
        return adapters.Deployment(model=self.model, version=self.version, context_window=self.context_window, capabilities=self.capabilities)

    def count_input(self, messages):
        return sum(adapters.estimate_tokens(adapters.message_text(m)) for m in messages or [] if isinstance(m, dict))

    def generate(self, request, cancellation=None):
        return iter([{"content": f"Reply to {request.messages[-1].get('content')}", "finish_reason": "stop", "usage": {"prompt_tokens": 3, "completion_tokens": 5}}])

    def cancel(self, request_id):
        return False

    def normalize_usage(self, result):
        return adapters.Usage(input_tokens=result["usage"]["prompt_tokens"], output_tokens=result["usage"]["completion_tokens"], source="model")

    def health(self):
        return {"status": "healthy"}


class GatewayAppTests(unittest.TestCase):
    def setUp(self):
        self.key_store = auth.InMemoryKeyStore()
        self.router = router_module.Router()
        self.router.register(FakeAdapter(), host_id="host-org-model")
        self.app = gateway_app.create_app(self.key_store, dev_api_key="dev-key", router=self.router)
        self.client = TestClient(self.app)
        self.headers = {"Authorization": "Bearer dev-key"}

    def test_health(self):
        response = self.client.get("/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok"})

    def test_missing_api_key_returns_unauthenticated_envelope(self):
        response = self.client.post("/v1/chat/completions", json={"model": "org-model", "messages": [{"role": "user", "content": "Hello"}]})
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json()["error"]["code"], "unauthenticated")

    def test_unknown_model_returns_model_not_found(self):
        response = self.client.post("/v1/chat/completions", json={"model": "missing", "messages": [{"role": "user", "content": "Hello"}]}, headers=self.headers)
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["error"]["code"], "model_not_found")

    def test_empty_messages_return_invalid_request(self):
        response = self.client.post("/v1/chat/completions", json={"model": "org-model", "messages": []}, headers=self.headers)
        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()["error"]["code"], "invalid_request")

    def test_happy_path_returns_completion_shape(self):
        response = self.client.post("/v1/chat/completions", json={"model": "org-model", "messages": [{"role": "user", "content": "Hello"}], "max_output_tokens": 64}, headers=self.headers)
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertTrue(body["id"])
        self.assertEqual(body["model"], "org-model@7")
        self.assertEqual(body["choices"][0]["message"]["content"], "Reply to Hello")
        self.assertEqual(body["usage"]["source"], "model")
        self.assertEqual(body["usage"]["input_tokens"], 3)
        self.assertEqual(body["usage"]["output_tokens"], 5)
        self.assertEqual(body["quota"]["reserved_credits"], 0)

    def test_context_limit_exceeded(self):
        self.app.state.router.register(FakeAdapter(context_window=8), host_id="host-org-model")
        response = self.client.post("/v1/chat/completions", json={"model": "org-model", "messages": [{"role": "user", "content": "Hello"}], "max_output_tokens": 64}, headers=self.headers)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"]["code"], "context_limit_exceeded")

    def test_unsupported_capability(self):
        self.app.state.router.register(FakeAdapter(capabilities=frozenset()), host_id="host-org-model")
        response = self.client.post("/v1/chat/completions", json={"model": "org-model", "messages": [{"role": "user", "content": "Hello"}]}, headers=self.headers)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"]["code"], "unsupported_capability")

    def test_model_error_maps_to_gateway_error(self):
        self.app.state.router.register(FakeAdapter(), host_id="host-org-model")
        adapter = self.app.state.router.resolve("org-model")
        adapter.generate = lambda request, cancellation=None: (_ for _ in ()).throw(errors.GatewayError("model_error", "Upstream failed."))
        response = self.client.post("/v1/chat/completions", json={"model": "org-model", "messages": [{"role": "user", "content": "Hello"}], "max_output_tokens": 64}, headers=self.headers)
        self.assertEqual(response.status_code, 502)
        self.assertEqual(response.json()["error"]["code"], "model_error")

    def test_quota_exceeded_after_limit_is_reached(self):
        self.app = gateway_app.create_app(self.key_store, dev_api_key="dev-key", router=self.router)
        client = TestClient(self.app)
        first = client.post("/v1/chat/completions", json={"model": "org-model", "messages": [{"role": "user", "content": "Hello"}], "max_output_tokens": 64}, headers={"Authorization": "Bearer dev-key"})
        self.assertEqual(first.status_code, 200)
        with mock.patch.object(config, "FREE_CREDITS", 10):
            second = client.post("/v1/chat/completions", json={"model": "org-model", "messages": [{"role": "user", "content": "Hello"}], "max_output_tokens": 64}, headers={"Authorization": "Bearer dev-key"})
        self.assertEqual(second.status_code, 429)
        self.assertEqual(second.json()["error"]["code"], "quota_exceeded")

    def test_streaming_response_is_sse(self):
        response = self.client.post("/v1/chat/completions", json={"model": "org-model", "messages": [{"role": "user", "content": "Hello"}], "max_output_tokens": 64, "stream": True}, headers=self.headers)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.headers["content-type"].startswith("text/event-stream"))


if __name__ == "__main__":
    unittest.main()
