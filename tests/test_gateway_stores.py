"""Gateway database-tier store tests."""
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from gateway import stores


class StoreTests(unittest.TestCase):
    def test_quota_hold_lifecycle(self):
        holds = stores.QuotaHolds()
        hold = holds.add(stores.QuotaHold(hold_id="hold_1", org_id="org-1", principal_id="u1", model="org-model", credits=10, state="held", created_at=100))
        self.assertEqual(holds.settle("hold_1", 200).state, "settled")
        self.assertEqual(holds.release("hold_1", 300), None)
        self.assertEqual(len(holds.list(org_id="org-1", model="org-model")), 1)

    def test_usage_ledger_appends_entries(self):
        ledger = stores.UsageLedger()
        ledger.append(stores.UsageLedgerEntry(entry_id="led_1", org_id="org-1", principal_id="u1", request_id="req_1", model="org-model", phase="settle"))
        self.assertEqual(len(ledger.list(org_id="org-1")), 1)
        self.assertEqual(ledger.list(org_id="org-2"), [])

    def test_audit_events_record_and_filter(self):
        audit_log = stores.AuditEvents()
        audit_log.record("auth_failed", "key-1", {"reason": "unknown_key"})
        self.assertEqual(len(audit_log.list()), 1)
        self.assertEqual(len(audit_log.list(subject="key-1")), 1)

    def test_subscriptions_apply_events(self):
        subscriptions = stores.Subscriptions()
        created = subscriptions.apply({"id": "evt_1", "type": "customer.subscription.created", "data": {"object": {"id": "sub_1", "status": "active", "items": [{"price": {"id": "price_1"}}]}}})
        self.assertTrue(created["ok"])
        self.assertEqual(subscriptions.get("sub_1")["status"], "active")
        deleted = subscriptions.apply({"id": "evt_2", "type": "customer.subscription.deleted", "data": {"object": {"id": "sub_1", "status": "canceled"}}})
        self.assertTrue(deleted["ok"])
        self.assertEqual(subscriptions.get("sub_1")["status"], "cancelled")

    def test_gateway_store_composes_substores(self):
        gateway_store = stores.GatewayStore()
        for attribute in ("organizations", "users", "memberships", "keys", "holds", "ledger", "audit", "subscriptions"):
            self.assertIsNotNone(getattr(gateway_store, attribute))


if __name__ == "__main__":
    unittest.main()
