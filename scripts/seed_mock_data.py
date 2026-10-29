"""Seed the gateway PostgreSQL database with mock organizations, users, plans,
deployments, and an API key for local development and testing."""

import asyncio
import hashlib
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import asyncpg

from gateway import stores

DATABASE_URL = os.environ.get("GATEWAY_DATABASE_URL", "postgresql://postgres:postgres@127.0.0.1:5432/gateway")
if DATABASE_URL.startswith("postgresql+psycopg://"):
    DATABASE_URL = "postgresql://" + DATABASE_URL[len("postgresql+psycopg://"):]
if DATABASE_URL.startswith("postgresql+asyncpg://"):
    DATABASE_URL = "postgresql://" + DATABASE_URL[len("postgresql+asyncpg://"):]

RAW_API_KEY = os.environ.get("MOCK_API_KEY", "gk_demo_mock_key_for_local_testing")


async def main() -> None:
    conn = await asyncpg.connect(DATABASE_URL)
    try:
        await conn.execute(
            "TRUNCATE TABLE quota_holds, usage_ledger, audit_events, subscriptions, requests, "
            "entitlements, deployments, model_hosts, api_keys, memberships, users, organizations, "
            "plans, idempotency_keys, guardrail_events, webhook_events RESTART IDENTITY CASCADE"
        )

        org_id = "demo-org"
        user_id = "demo-user"
        await stores.ensure_org(conn, org_id, "Demo Organization")
        await stores.ensure_user(conn, user_id, "demo@example.com")
        await stores.ensure_membership(conn, org_id, user_id, "owner")
        await stores.ensure_plan(conn, "free", 1)
        await stores.ensure_plan(conn, "pro", 1)
        await stores.ensure_entitlement(conn, "ent_demo", org_id, user_id, "pro", 1)
        await stores.ensure_host(conn, org_id, "host_demo")
        await stores.ensure_deployment(conn, org_id, "dep_demo", "host_demo", "org-model")

        key_id = "key-demo"
        key_hash = hashlib.sha256(RAW_API_KEY.encode("utf-8")).hexdigest()
        await conn.execute(
            "INSERT INTO api_keys (key_id, org_id, principal_id, key_prefix, key_hash, scopes, state, created_at) "
            "VALUES ($1, $2, $3, $4, $5, $6, 'active', $7) ON CONFLICT (key_hash) DO NOTHING",
            key_id, org_id, user_id, RAW_API_KEY[:8], key_hash, "inference:chat,usage:read,keys:write,admin", int(__import__("time").time()),
        )

        print("Mock data seeded.")
        print(f"  org_id:        {org_id}")
        print(f"  user_id:       {user_id}")
        print(f"  deployment:    org-model (dep_demo)")
        print(f"  API key:       {RAW_API_KEY}")
        print(f"  key_id:        {key_id}")
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
