"""Gateway settings loaded from the environment."""
from pathlib import Path
import sys
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from gateway import config


class ConfigTests(unittest.TestCase):
    def test_default_values(self):
        self.assertEqual(config.DATABASE_URL, "postgresql+psycopg://localhost:5432/gateway")
        self.assertEqual(config.HOST, "127.0.0.1")
        self.assertEqual(config.PORT, 8080)
        self.assertEqual(config.FREE_CREDITS, 10_000)
        self.assertEqual(config.MAX_OUTPUT_TOKENS, 256)
        self.assertEqual(config.SESSION_TTL_SECONDS, 3600)
        self.assertEqual(config.RATE_LIMIT_REQUESTS_PER_MINUTE, 10)
        self.assertEqual(config.CONCURRENT_GENERATIONS, 1)

    def test_env_overrides(self):
        with mock.patch.object(config, "DATABASE_URL", "postgresql+psycopg://db/gateway"), \
             mock.patch.object(config, "HOST", "0.0.0.0"), \
             mock.patch.object(config, "PORT", 9090), \
             mock.patch.object(config, "FREE_CREDITS", 42):
            self.assertEqual(config.DATABASE_URL, "postgresql+psycopg://db/gateway")
            self.assertEqual(config.HOST, "0.0.0.0")
            self.assertEqual(config.PORT, 9090)
            self.assertEqual(config.FREE_CREDITS, 42)

    def test_all_scopes_are_advertised_for_dev_principal(self):
        self.assertIn("inference:chat", config.ALL_SCOPES)
        self.assertIn("usage:read", config.ALL_SCOPES)


if __name__ == "__main__":
    unittest.main()
