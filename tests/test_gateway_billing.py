"""Stripe billing webhook verification and entitlement events."""
from pathlib import Path
import hashlib
import hmac
import sys
import time
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from gateway import billing


def sign(payload: bytes, secret: str, timestamp: int) -> str:
    signature = hmac.new(secret.encode(), f"{timestamp}.{payload.decode()}".encode(), hashlib.sha256).hexdigest()
    return f"t={timestamp},v1={signature}"


class BillingTests(unittest.TestCase):
    def test_valid_signature_is_accepted(self):
        payload = b'{"id":"evt_1","type":"customer.subscription.created"}'
        timestamp = int(time.time())
        self.assertTrue(billing.verify_signature(payload, sign(payload, "whsec_test", timestamp), "whsec_test"))
        self.assertFalse(billing.verify_signature(payload, sign(payload, "whsec_test", timestamp), "whsec_wrong"))

    def test_expired_signature_is_rejected(self):
        payload = b'{"id":"evt_1","type":"customer.subscription.created"}'
        self.assertFalse(billing.verify_signature(payload, sign(payload, "whsec_test", int(time.time()) - 10_000), "whsec_test"))

    def test_malformed_header_is_rejected(self):
        self.assertFalse(billing.verify_signature(b"{}", "garbage", "whsec_test"))

    def test_subscription_created_grants_entitlement(self):
        result = billing.process_event({"id": "evt_1", "type": "customer.subscription.created", "data": {"object": {"id": "sub_1", "status": "active", "items": [{"price": {"id": "price_1"}}]}}})
        self.assertTrue(result["ok"])
        self.assertEqual(billing.BILLING.subscription("sub_1")["status"], "active")

    def test_subscription_deleted_cancels_entitlement(self):
        billing.BILLING._subscriptions["sub_1"] = {"status": "active", "plan_id": "price_1"}
        result = billing.process_event({"id": "evt_2", "type": "customer.subscription.deleted", "data": {"object": {"id": "sub_1", "status": "canceled"}}})
        self.assertTrue(result["ok"])
        self.assertEqual(billing.BILLING.subscription("sub_1")["status"], "cancelled")


if __name__ == "__main__":
    unittest.main()
