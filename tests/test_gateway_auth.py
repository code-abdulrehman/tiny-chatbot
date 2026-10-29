"""API key storage, hashing, and principal resolution."""
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from gateway import auth, errors


class AuthTests(unittest.TestCase):
    def test_api_key_hash_is_salted_sha256_hex(self):
        from hashlib import sha256

        self.assertEqual(auth.hash_api_key("secret"), sha256(b"secret").hexdigest())
        self.assertNotEqual(auth.hash_api_key("secret"), "secret")
        self.assertEqual(auth.hash_api_key("secret"), auth.hash_api_key("secret"))

    def test_in_memory_key_store_verifies_and_rejects_unknown_keys(self):
        store = auth.InMemoryKeyStore()
        record = store.add("key-1", "secret-key", "org-1", "user-1", {"inference:chat", "usage:read"})
        self.assertEqual(store.verify("secret-key").key_id, "key-1")
        self.assertIsNone(store.verify("wrong-key"))

    def test_resolve_principal_accepts_dev_key(self):
        principal = auth.resolve_principal("dev-key", auth.InMemoryKeyStore(), dev_api_key="dev-key")
        self.assertEqual(principal.org_id, "local-dev")
        self.assertEqual(principal.state, "active")
        self.assertIn("inference:chat", principal.scopes)

    def test_resolve_principal_rejects_unknown_key(self):
        self.assertRaises(errors.GatewayError, auth.resolve_principal, "nope", auth.InMemoryKeyStore(), dev_api_key="")

    def test_resolve_principal_rejects_revoked_key(self):
        store = auth.InMemoryKeyStore()
        store.add("key-1", "secret-key", "org-1", "user-1", {"inference:chat"})
        store._keys[auth.hash_api_key("secret-key")].state = "revoked"
        self.assertRaises(errors.GatewayError, auth.resolve_principal, "secret-key", store, dev_api_key="")

    def test_resolve_principal_rejects_suspended_key(self):
        store = auth.InMemoryKeyStore()
        store.add("key-1", "secret-key", "org-1", "user-1", {"inference:chat"})
        store._keys[auth.hash_api_key("secret-key")].state = "suspended"
        self.assertRaises(errors.GatewayError, auth.resolve_principal, "secret-key", store, dev_api_key="")


if __name__ == "__main__":
    unittest.main()
