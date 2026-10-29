"""Security, audit, roles, and API key expiry behavior."""
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from gateway import auth, audit, errors


class AuthExpiryTests(unittest.TestCase):
    def test_expired_key_is_rejected(self):
        store = auth.InMemoryKeyStore()
        store.add("key-1", "secret-key", "org-1", "user-1", {"inference:chat"}, expires_at=50)
        self.assertRaises(errors.GatewayError, auth.resolve_principal, "secret-key", store, dev_api_key="")

    def test_active_key_is_accepted(self):
        store = auth.InMemoryKeyStore()
        store.add("key-1", "secret-key", "org-1", "user-1", {"inference:chat"}, expires_at=1000)
        principal = auth.resolve_principal("secret-key", store, dev_api_key="")
        self.assertEqual(principal.org_id, "org-1")
        self.assertEqual(principal.state, "active")


class AuditTests(unittest.TestCase):
    def test_audit_log_records_and_lists_events(self):
        audit.AUDIT_LOG = audit.AuditLog()
        audit.record(audit.AUTH_FAILED, "key-abc", {"reason": "unknown_key"})
        audit.record(audit.KEY_REVOKED, "key-abc")
        events = audit.AUDIT_LOG.list()
        self.assertEqual(len(events), 2)
        self.assertEqual(events[0].event, audit.AUTH_FAILED)


class RoleTests(unittest.TestCase):
    def test_admin_role_check(self):
        principal = auth.Principal(org_id="org-1", principal_id="u1", roles=frozenset({"admin"}), scopes=frozenset({"admin"}), state="active")
        self.assertTrue(auth.is_admin(principal))
        self.assertFalse(auth.is_admin(auth.Principal(org_id="org-1", principal_id="u2", roles=frozenset({"member"}), scopes=frozenset({"inference:chat"}), state="active")))


if __name__ == "__main__":
    unittest.main()
