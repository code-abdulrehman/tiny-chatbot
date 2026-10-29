"""Real PostgreSQL integration tests for the gateway stores."""
import asyncio
import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import asyncpg

from gateway import stores

DATABASE_URL = "postgresql://postgres:postgres@127.0.0.1:5432/gateway"


async def _connect():
    return await asyncpg.connect(DATABASE_URL)


async def _truncate(conn):
    await conn.execute(
        "TRUNCATE TABLE quota_holds, usage_ledger, audit_events, subscriptions, requests, entitlements, deployments, model_hosts, memberships, users, organizations, plans, api_keys, idempotency_keys, guardrail_events, webhook_events RESTART IDENTITY CASCADE"
    )


class PostgresStoreTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.conn = await _connect()
        await _truncate(self.conn)

    async def asyncTearDown(self):
        await self.conn.close()

    async def test_quota_hold_lifecycle(self):
        await stores.ensure_request_context(self.conn, "org-1", "u1", "req_hold_1", model="org-model", input_tokens=1, max_output_tokens=2)
        holds = stores.PostgresQuotaHolds(self.conn)
        hold = stores.QuotaHold(hold_id="hold_pg_1", org_id="org-1", principal_id="u1", request_id="req_hold_1", model="org-model", credits=10, state="held", created_at=100, expires_at=200)
        await holds.add(hold)
        self.assertTrue(await holds.settle("hold_pg_1", 200))
        self.assertFalse(await holds.release("hold_pg_1", 300))
        listed = await holds.list(org_id="org-1", model="org-model")
        self.assertEqual(len(listed), 1)
        self.assertEqual(listed[0].state, "settled")

    async def test_usage_ledger_appends_entries(self):
        await stores.ensure_request_context(self.conn, "org-1", "u1", "req_led_1", model="org-model", input_tokens=1, max_output_tokens=2)
        ledger = stores.PostgresUsageLedger(self.conn)
        await ledger.append(stores.UsageLedgerEntry(entry_id="led_pg_1", org_id="org-1", principal_id="u1", request_id="req_led_1", model="org-model", phase="settle"))
        self.assertEqual(len(await ledger.list(org_id="org-1")), 1)
        self.assertEqual(len(await ledger.list(org_id="org-2")), 0)

    async def test_audit_events_record_and_filter(self):
        await stores.ensure_org(self.conn, "org-audit")
        audit = stores.PostgresAuditEvents(self.conn)
        await audit.record("auth_failed", "key-1", {"reason": "unknown_key"}, org_id="org-audit")
        self.assertEqual(len(await audit.list()), 1)
        self.assertEqual(len(await audit.list(subject="key-1")), 1)

    async def test_subscriptions_apply_events(self):
        await stores.ensure_org(self.conn, "org_unknown")
        subs = stores.PostgresSubscriptions(self.conn)
        created = await subs.apply({"id": "evt_1", "type": "customer.subscription.created", "data": {"object": {"id": "sub_pg_1", "status": "active", "items": [{"price": {"id": "price_1"}}]}}})
        self.assertTrue(created["ok"])
        self.assertEqual((await subs.get("sub_pg_1"))["status"], "active")
        deleted = await subs.apply({"id": "evt_2", "type": "customer.subscription.deleted", "data": {"object": {"id": "sub_pg_1", "status": "canceled"}}})
        self.assertTrue(deleted["ok"])
        self.assertEqual((await subs.get("sub_pg_1"))["status"], "cancelled")

    async def test_hold_release_lifecycle(self):
        await stores.ensure_request_context(self.conn, "org-2", "u2", "req_hold_2", model="org-model", input_tokens=1, max_output_tokens=2)
        holds = stores.PostgresQuotaHolds(self.conn)
        await holds.add(stores.QuotaHold(hold_id="hold_pg_2", org_id="org-2", principal_id="u2", request_id="req_hold_2", model="org-model", credits=5, state="held", created_at=10, expires_at=20))
        self.assertTrue(await holds.release("hold_pg_2", 20))
        self.assertFalse(await holds.settle("hold_pg_2", 30))

    async def test_requests_create_and_get(self):
        await stores.ensure_request_context(self.conn, "org-3", "u3", "req_3", model="org-model", input_tokens=4, max_output_tokens=8)
        reqs = stores.PostgresRequests(self.conn)
        got = await reqs.get("org-3", "req_3")
        self.assertIsNotNone(got)
        self.assertEqual(got.state, "reserved")
        await reqs.set_state("org-3", "req_3", "completed", 99)
        got2 = await reqs.get("org-3", "req_3")
        self.assertEqual(got2.state, "completed")


if __name__ == "__main__":
    unittest.main()
