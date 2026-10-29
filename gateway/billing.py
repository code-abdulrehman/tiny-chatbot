"""Stripe billing webhooks, signature verification, and entitlement state."""

import hashlib
import hmac
import time
from typing import Optional

from gateway import config, errors

STRIPE_SIGNATURE_HEADER = "stripe-signature"
SIGNATURE_TOLERANCE_SECONDS = 300


def verify_signature(payload: bytes, header: str, secret: str, tolerance: int = SIGNATURE_TOLERANCE_SECONDS) -> bool:
    parts = {}
    for chunk in header.split(","):
        key, separator, value = chunk.partition("=")
        if key and separator:
            parts[key.strip()] = value.strip()
    try:
        timestamp = int(parts.get("t", "0"))
        signature = parts.get("v1", "")
    except (TypeError, ValueError):
        return False
    if abs(time.time() - timestamp) > tolerance:
        return False
    signed_payload = f"{timestamp}.{payload.decode('utf-8')}"
    expected = hmac.new(secret.encode("utf-8"), signed_payload.encode("utf-8"), hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)


class BillingState:
    """In-memory subscription/entitlement state; durable store comes with the database tier."""

    def __init__(self):
        self._subscriptions = {}

    def apply(self, event: dict) -> dict:
        event_type = event.get("type")
        obj = (event.get("data") or {}).get("object") or {}
        result = {"ok": True, "event": event_type, "subscription": obj.get("id")}
        if event_type in ("customer.subscription.created", "customer.subscription.updated"):
            items = obj.get("items") or [{}]
            price = (items[0] or {}).get("price") or {}
            self._subscriptions[obj.get("id")] = {"status": obj.get("status"), "plan_id": price.get("id")}
        elif event_type == "customer.subscription.deleted":
            self._subscriptions[obj.get("id")] = {"status": "cancelled"}
        return result

    def subscription(self, subscription_id: str) -> Optional[dict]:
        return self._subscriptions.get(subscription_id)


BILLING = BillingState()


def process_event(event: dict) -> dict:
    return BILLING.apply(event)
