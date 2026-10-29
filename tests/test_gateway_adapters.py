"""Model adapter contract, token estimation, and usage normalization."""
from pathlib import Path
import sys
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from gateway import adapters, errors


class FakeUpstream:
    def __init__(self, status_code=200, payload=None):
        self.status_code = status_code
        self._payload = payload or {}

    def json(self):
        return self._payload


class AdapterTests(unittest.TestCase):
    def test_estimate_tokens_uses_four_chars_per_token(self):
        self.assertEqual(adapters.estimate_tokens(""), 0)
        self.assertEqual(adapters.estimate_tokens("abcd"), 1)
        self.assertEqual(adapters.estimate_tokens("abcde"), 2)

    def test_message_text_handles_strings_lists_and_none(self):
        self.assertEqual(adapters.message_text({"role": "user", "content": "Hello"}), "Hello")
        self.assertEqual(adapters.message_text({"role": "user", "content": [{"type": "text", "text": "Hi"}]}), "Hi")
        self.assertEqual(adapters.message_text({"role": "assistant", "content": None}), "")

    def test_openai_compatible_adapter_describes_deployment(self):
        adapter = adapters.OpenAICompatibleAdapter("vllm", "http://localhost:8000", "key", "org-model", version="3", context_window=8192)
        deployment = adapter.describe()
        self.assertEqual(deployment.model, "org-model")
        self.assertEqual(deployment.version, "3")
        self.assertEqual(deployment.context_window, 8192)
        self.assertIn(adapters.CHAT, deployment.capabilities)
        self.assertIn(adapters.STREAMING, deployment.capabilities)

    def test_openai_compatible_adapter_counts_input_tokens(self):
        adapter = adapters.OpenAICompatibleAdapter("vllm", "http://localhost:8000", "key", "org-model", context_window=1024)
        messages = [
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": "Hello there."},
        ]
        self.assertGreater(adapter.count_input(messages), 0)

    def test_openai_compatible_adapter_normalizes_usage(self):
        adapter = adapters.OpenAICompatibleAdapter("vllm", "http://localhost:8000", "key", "org-model")
        usage = adapter.normalize_usage({"usage": {"prompt_tokens": 12, "completion_tokens": 3}})
        self.assertEqual(usage.input_tokens, 12)
        self.assertEqual(usage.output_tokens, 3)
        self.assertEqual(usage.source, "model")

    def test_ollama_adapter_normalizes_prompt_and_eval_counts(self):
        adapter = adapters.OllamaAdapter("ollama", "http://localhost:11434", "", "smollm")
        usage = adapter.normalize_usage({"usage": {"prompt_eval_count": 9, "eval_count": 4}})
        self.assertEqual(usage.input_tokens, 9)
        self.assertEqual(usage.output_tokens, 4)
        self.assertEqual(usage.source, "model")

    def test_ollama_adapter_generate_returns_content_and_usage(self):
        adapter = adapters.OllamaAdapter("ollama", "http://localhost:11434", "", "smollm")
        with mock.patch("httpx.post", return_value=FakeUpstream(payload={"message": {"content": "Hi there"}, "usage": {"prompt_eval_count": 7, "eval_count": 2}})) as post:
            events = list(adapter.generate(adapters.GenerateRequest(model="smollm", messages=[{"role": "user", "content": "Hi"}], max_output_tokens=64)))
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["content"], "Hi there")
        self.assertEqual(post.call_args.kwargs["json"]["options"]["num_predict"], 64)

    def test_ollama_adapter_generate_raises_model_error_on_failure(self):
        adapter = adapters.OllamaAdapter("ollama", "http://localhost:11434", "", "smollm")
        with mock.patch("httpx.post", return_value=FakeUpstream(status_code=500)):
            self.assertRaises(errors.GatewayError, lambda: list(adapter.generate(adapters.GenerateRequest(model="smollm", messages=[], max_output_tokens=8))))


if __name__ == "__main__":
    unittest.main()
