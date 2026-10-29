"""OpenRouter-style model router tests."""
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from gateway import adapters, errors, router as router_module


class FakeAdapter(adapters.Adapter):
    def __init__(self, model="org-model"):
        self.model = model

    def describe(self):
        return adapters.Deployment(model=self.model, version="1", context_window=1024, capabilities=frozenset({adapters.CHAT}))

    def count_input(self, messages):
        return 0

    def generate(self, request, cancellation=None):
        return iter([{"content": "ok", "finish_reason": "stop", "usage": {"prompt_tokens": 1, "completion_tokens": 1}}])

    def cancel(self, request_id):
        return False

    def normalize_usage(self, result):
        return adapters.Usage(input_tokens=1, output_tokens=1, source="model")

    def health(self):
        return {"status": "healthy"}


class RouterTests(unittest.TestCase):
    def setUp(self):
        self.router = router_module.Router(approved_hosts=["host-org-model"])

    def test_register_and_resolve_returns_adapter(self):
        adapter = FakeAdapter("org-model")
        self.router.register(adapter, host_id="host-org-model")
        self.assertIs(self.router.resolve("org-model"), adapter)

    def test_resolve_unknown_model_raises_model_not_found(self):
        self.assertRaises(errors.GatewayError, self.router.resolve, "missing-model")

    def test_resolve_rejects_unapproved_host(self):
        self.router.register(FakeAdapter("org-model"), host_id="host-evil")
        self.assertRaises(errors.GatewayError, self.router.resolve, "org-model")

    def test_resolve_allows_approved_host(self):
        self.router.register(FakeAdapter("org-model"), host_id="host-org-model")
        self.assertIsNotNone(self.router.resolve("org-model"))

    def test_resolve_with_fallback_uses_fallback_when_available(self):
        router = router_module.Router()
        router.register(FakeAdapter("org-model"), host_id="host-org-model")
        router.register(FakeAdapter("org-model-2"), host_id="host-org-model-2")
        adapter, resolved = router.resolve_with_fallback("org-model", fallbacks=["org-model-2"])
        self.assertEqual(resolved, "org-model-2")
        self.assertIs(adapter, router.resolve("org-model-2"))

    def test_resolve_with_fallback_keeps_primary_when_no_fallback_exists(self):
        router = router_module.Router()
        router.register(FakeAdapter("org-model"), host_id="host-org-model")
        adapter, resolved = router.resolve_with_fallback("org-model", fallbacks=["missing-model"])
        self.assertEqual(resolved, "org-model")
        self.assertIs(adapter, router.resolve("org-model"))

    def test_deployments_lists_registered_models(self):
        self.router.register(FakeAdapter("org-model"), host_id="host-org-model")
        self.router.register(FakeAdapter("org-model-2"), host_id="host-org-model-2")
        deployments = self.router.deployments()
        self.assertEqual(len(deployments), 2)
        self.assertEqual(deployments[0]["model"], "org-model")


if __name__ == "__main__":
    unittest.main()
