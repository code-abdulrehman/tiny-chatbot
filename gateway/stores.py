"""Gateway database tier: stores and in-memory implementations."""

import json
from dataclasses import dataclass
from time import time
from typing import Optional

from uuid import uuid4 as _uuid4


def uuid4_hex() -> str:
    return _uuid4().hex


@dataclass
class Organization:
    org_id: str
    name: str = ""
    created_at: int = 0


@dataclass
class Membership:
    org_id: str
    user_id: str
    role: str = "member"
    status: str = "active"


@dataclass
class User:
    user_id: str
    org_id: str
    email: str = ""
    state: str = "active"
    created_at: int = 0


@dataclass
class QuotaHold:
    hold_id: str
    org_id: str
    principal_id: str
    request_id: str = ""
    model: str = ""
    credits: int = 0
    state: str = "held"
    created_at: int = 0
    expires_at: int = 0
    settled_at: Optional[int] = None


@dataclass
class UsageLedgerEntry:
    entry_id: str
    org_id: str
    principal_id: str
    request_id: str
    model: str = ""
    input_tokens: int = 0
    output_tokens: int = 0
    credits: int = 0
    phase: str = "reserve"
    usage_source: str = "model"
    created_at: int = 0


@dataclass
class AuditEventRecord:
    id: str
    org_id: str = ""
    actor_id: Optional[str] = None
    event: str = ""
    subject: str = ""
    detail: Optional[dict] = None
    request_id: Optional[str] = None
    timestamp: int = 0


@dataclass
class Subscription:
    subscription_id: str
    org_id: str
    provider: str = "stripe"
    provider_customer_id: Optional[str] = None
    status: str = "active"
    plan_id: Optional[str] = None
    created_at: int = 0
    updated_at: int = 0


@dataclass
class Request:
    request_id: str
    org_id: str
    principal_id: str
    deployment_id: str = ""
    entitlement_id: str = ""
    key_id: Optional[str] = None
    body_hash: str = ""
    state: str = "reserved"
    input_tokens: int = 0
    max_output_tokens: int = 0
    created_at: int = 0
    settled_at: Optional[int] = None


class Organizations:
    def __init__(self):
        self._items = {}

    def add(self, org_id: str, name: str = "") -> Organization:
        organization = Organization(org_id=org_id, name=name, created_at=1_000)
        self._items[org_id] = organization
        return organization

    def get(self, org_id: str) -> Optional[Organization]:
        return self._items.get(org_id)


class Users:
    def __init__(self):
        self._items = {}

    def add(self, user_id: str, org_id: str, email: str = "") -> User:
        user = User(user_id=user_id, org_id=org_id, email=email, created_at=1_000)
        self._items[(org_id, user_id)] = user
        return user

    def get(self, user_id: str, org_id: str) -> Optional[User]:
        return self._items.get((org_id, user_id))


class Memberships:
    def __init__(self):
        self._items = {}

    def add(self, org_id: str, user_id: str, role: str = "member") -> Membership:
        membership = Membership(org_id=org_id, user_id=user_id, role=role)
        self._items[(org_id, user_id)] = membership
        return membership

    def list_for_user(self, user_id: str, org_id: str) -> list:
        membership = self._items.get((org_id, user_id))
        return [membership] if membership else []


class QuotaHolds:
    def __init__(self):
        self._items = []

    def add(self, hold: QuotaHold) -> QuotaHold:
        self._items.append(hold)
        return hold

    def settle(self, hold_id: str, settled_at: int) -> Optional[QuotaHold]:
        for hold in self._items:
            if hold.hold_id == hold_id and hold.state == "held":
                hold.state = "settled"
                hold.settled_at = settled_at
                return hold
        return None

    def release(self, hold_id: str, released_at: int) -> Optional[QuotaHold]:
        for hold in self._items:
            if hold.hold_id == hold_id and hold.state == "held":
                hold.state = "released"
                hold.settled_at = released_at
                return hold
        return None

    def list(self, org_id: str = "", principal_id: str = "", model: str = "") -> list:
        return [
            hold for hold in self._items
            if (not org_id or hold.org_id == org_id)
            and (not principal_id or hold.principal_id == principal_id)
            and (not model or hold.model == model)
        ]


class UsageLedger:
    def __init__(self):
        self._items = []

    def append(self, entry: UsageLedgerEntry) -> UsageLedgerEntry:
        self._items.append(entry)
        return entry

    def list(self, org_id: str = "") -> list:
        return [entry for entry in self._items if not org_id or entry.org_id == org_id]


class AuditEvents:
    def __init__(self):
        self._items = []

    def record(self, event: str, subject: str, detail=None, org_id: str = "", actor_id=None, request_id=None) -> AuditEventRecord:
        from time import time

        entry = AuditEventRecord(id=f"evt_{len(self._items) + 1}", org_id=org_id, actor_id=actor_id, event=event, subject=subject, detail=detail, request_id=request_id, timestamp=int(time()))
        self._items.append(entry)
        return entry

    def list(self, subject: Optional[str] = None) -> list:
        if subject is None:
            return list(self._items)
        return [entry for entry in self._items if entry.subject == subject]


class Subscriptions:
    """Subscription/entitlement state as used by billing webhook events."""

    def __init__(self):
        self._items = {}

    def apply(self, event: dict) -> dict:
        event_type = event.get("type")
        obj = (event.get("data") or {}).get("object") or {}
        result = {"ok": True, "event": event_type, "subscription": obj.get("id")}
        if event_type in ("customer.subscription.created", "customer.subscription.updated"):
            items = obj.get("items") or [{}]
            price = (items[0] or {}).get("price") or {}
            self._items[obj.get("id")] = {"status": obj.get("status"), "plan_id": price.get("id")}
        elif event_type == "customer.subscription.deleted":
            self._items[obj.get("id")] = {"status": "cancelled"}
        return result

    def get(self, subscription_id: str) -> Optional[dict]:
        return self._items.get(subscription_id)


class GatewayStore:
    """Composes the database-tier stores."""

    def __init__(self):
        from gateway import auth as auth_module

        self.keys = auth_module.InMemoryKeyStore()
        self.organizations = Organizations()
        self.users = Users()
        self.memberships = Memberships()
        self.holds = QuotaHolds()
        self.ledger = UsageLedger()
        self.audit = AuditEvents()
        self.subscriptions = Subscriptions()


class PostgresQuotaHolds:
    """Async PostgreSQL quota holds (backend for `backend = postgres`)."""

    def __init__(self, connection):
        self.connection = connection

    async def add(self, hold: QuotaHold) -> QuotaHold:
        await self.connection.execute(
            "INSERT INTO quota_holds (hold_id, org_id, principal_id, request_id, model, credits, state, created_at, expires_at, settled_at) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)",
            hold.hold_id, hold.org_id, hold.principal_id, hold.request_id, hold.model, hold.credits, hold.state, hold.created_at, hold.expires_at, hold.settled_at,
        )
        return hold

    async def settle(self, hold_id: str, settled_at: int) -> bool:
        result = await self.connection.execute(
            "UPDATE quota_holds SET state = 'settled', settled_at = $2 WHERE hold_id = $1 AND state = 'held'",
            hold_id, settled_at,
        )
        try:
            return int(str(result).split()[-1]) > 0
        except (ValueError, IndexError):
            return False

    async def release(self, hold_id: str, released_at: int) -> bool:
        result = await self.connection.execute(
            "UPDATE quota_holds SET state = 'released', settled_at = $2 WHERE hold_id = $1 AND state = 'held'",
            hold_id, released_at,
        )
        try:
            return int(str(result).split()[-1]) > 0
        except (ValueError, IndexError):
            return False

    async def list(self, org_id: str = "", principal_id: str = "", model: str = "") -> list:
        rows = await self.connection.fetch("SELECT hold_id, org_id, principal_id, model, credits, state, created_at, settled_at FROM quota_holds")
        return [
            QuotaHold(
                hold_id=row["hold_id"], org_id=row["org_id"], principal_id=row["principal_id"],
                model=row["model"], credits=row["credits"], state=row["state"],
                created_at=row["created_at"], settled_at=row["settled_at"],
            )
            for row in rows
            if (not org_id or row["org_id"] == org_id) and (not principal_id or row["principal_id"] == principal_id) and (not model or row["model"] == model)
        ]


class PostgresUsageLedger:
    """Async PostgreSQL append-only usage ledger."""

    def __init__(self, connection):
        self.connection = connection

    async def append(self, entry: UsageLedgerEntry) -> UsageLedgerEntry:
        await self.connection.execute(
            "INSERT INTO usage_ledger (entry_id, org_id, principal_id, request_id, model, input_tokens, output_tokens, credits, phase, usage_source, created_at) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)",
            entry.entry_id, entry.org_id, entry.principal_id, entry.request_id, entry.model, entry.input_tokens, entry.output_tokens, entry.credits, entry.phase, entry.usage_source, entry.created_at,
        )
        return entry

    async def list(self, org_id: str = "") -> list:
        rows = await self.connection.fetch("SELECT entry_id, org_id, principal_id, request_id, model, input_tokens, output_tokens, credits, phase, created_at FROM usage_ledger")
        return [
            UsageLedgerEntry(
                entry_id=row["entry_id"], org_id=row["org_id"], principal_id=row["principal_id"], request_id=row["request_id"],
                model=row["model"], input_tokens=row["input_tokens"], output_tokens=row["output_tokens"],
                credits=row["credits"], phase=row["phase"], created_at=row["created_at"],
            )
            for row in rows
            if not org_id or row["org_id"] == org_id
        ]


class PostgresAuditEvents:
    """Async PostgreSQL audit event trail."""

    def __init__(self, connection):
        self.connection = connection

    async def record(self, event: str, subject: str, detail=None, org_id: str = "local-dev", actor_id: Optional[str] = None, request_id: Optional[str] = None) -> AuditEventRecord:
        entry = AuditEventRecord(id=f"evt_{uuid4_hex()}", org_id=org_id, actor_id=actor_id, event=event, subject=subject, detail=detail, request_id=request_id, timestamp=int(time()))
        await self.connection.execute(
            "INSERT INTO audit_events (event_id, org_id, actor_id, event, subject, detail, request_id, created_at) VALUES ($1, $2, $3, $4, $5, $6, $7, $8)",
            entry.id, org_id, actor_id, event, subject, json.dumps(detail or {}), request_id, entry.timestamp,
        )
        return entry

    async def list(self, subject: Optional[str] = None) -> list:
        rows = await self.connection.fetch("SELECT event_id, event, subject, detail, created_at FROM audit_events")
        events = [
            AuditEventRecord(id=row["event_id"], event=row["event"], subject=row["subject"], detail=row["detail"], timestamp=row["created_at"])
            for row in rows
        ]
        if subject is None:
            return events
        return [entry for entry in events if entry.subject == subject]


class PostgresSubscriptions:
    """Async PostgreSQL subscription/entitlement state."""

    def __init__(self, connection):
        self.connection = connection

    async def apply(self, event: dict) -> dict:
        event_type = event.get("type")
        obj = (event.get("data") or {}).get("object") or {}
        result = {"ok": True, "event": event_type, "subscription": obj.get("id")}
        if event_type in ("customer.subscription.created", "customer.subscription.updated"):
            items = obj.get("items") or [{}]
            price = (items[0] or {}).get("price") or {}
            await self.connection.execute(
                "INSERT INTO subscriptions (subscription_id, org_id, provider, status, plan_id, created_at, updated_at) VALUES ($1, $2, 'stripe', $3, $4, $5, $5) ON CONFLICT (subscription_id) DO UPDATE SET status = EXCLUDED.status, plan_id = EXCLUDED.plan_id, updated_at = EXCLUDED.updated_at",
                obj.get("id"), obj.get("org_id") or "org_unknown", obj.get("status") or "active", price.get("id"), int(time()),
            )
        elif event_type == "customer.subscription.deleted":
            await self.connection.execute(
                "INSERT INTO subscriptions (subscription_id, org_id, provider, status, plan_id, created_at, updated_at) VALUES ($1, $2, 'stripe', 'cancelled', $3, $4, $4) ON CONFLICT (subscription_id) DO UPDATE SET status = EXCLUDED.status, plan_id = EXCLUDED.plan_id, updated_at = EXCLUDED.updated_at",
                obj.get("id"), obj.get("org_id") or "org_unknown", obj.get("plan_id"), int(time()),
            )
        return result

    async def get(self, subscription_id: str):
        row = await self.connection.fetchrow("SELECT subscription_id, org_id, status, plan_id, created_at FROM subscriptions WHERE subscription_id = $1", subscription_id)
        if row is None:
            return None
        return {"subscription_id": row["subscription_id"], "org_id": row["org_id"], "status": row["status"], "plan_id": row["plan_id"], "created_at": row["created_at"]}


class PostgresRequests:

    def __init__(self, connection):
        self.connection = connection

    async def create(self, request: Request) -> Request:
        await self.connection.execute(
            "INSERT INTO requests (request_id, org_id, principal_id, key_id, deployment_id, entitlement_id, body_hash, state, input_tokens, max_output_tokens, created_at, settled_at) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12) ON CONFLICT (org_id, request_id) DO NOTHING",
            request.request_id, request.org_id, request.principal_id, request.key_id, request.deployment_id, request.entitlement_id, request.body_hash, request.state, request.input_tokens, request.max_output_tokens, request.created_at, request.settled_at,
        )
        return request

    async def get(self, org_id: str, request_id: str):
        row = await self.connection.fetchrow("SELECT request_id, org_id, principal_id, key_id, deployment_id, entitlement_id, body_hash, state, input_tokens, max_output_tokens, created_at, settled_at FROM requests WHERE org_id = $1 AND request_id = $2", org_id, request_id)
        if row is None:
            return None
        return Request(request_id=row["request_id"], org_id=row["org_id"], principal_id=row["principal_id"], key_id=row["key_id"], deployment_id=row["deployment_id"], entitlement_id=row["entitlement_id"], body_hash=row["body_hash"], state=row["state"], input_tokens=row["input_tokens"], max_output_tokens=row["max_output_tokens"], created_at=row["created_at"], settled_at=row["settled_at"])

    async def set_state(self, org_id: str, request_id: str, state: str, settled_at: Optional[int] = None) -> bool:
        await self.connection.execute(
            "UPDATE requests SET state = $3, settled_at = COALESCE($4, settled_at) WHERE org_id = $1 AND request_id = $2",
            org_id, request_id, state, settled_at,
        )
        return True


async def ensure_org(conn, org_id: str, name: str = "auto") -> None:
    await conn.execute(
        "INSERT INTO organizations (org_id, name, status, created_at) VALUES ($1, $2, 'active', $3) ON CONFLICT (org_id) DO NOTHING",
        org_id, name, int(time()),
    )


async def ensure_user(conn, user_id: str, email: str = "") -> None:
    await conn.execute(
        "INSERT INTO users (user_id, email, state, created_at) VALUES ($1, $2, 'active', $3) ON CONFLICT (user_id) DO NOTHING",
        user_id, email or f"{user_id}@local", int(time()),
    )


async def ensure_membership(conn, org_id: str, user_id: str, role: str = "member") -> None:
    await ensure_org(conn, org_id)
    await ensure_user(conn, user_id)
    await conn.execute(
        "INSERT INTO memberships (org_id, user_id, role, status, created_at) VALUES ($1, $2, $3, 'active', $4) ON CONFLICT (org_id, user_id) DO NOTHING",
        org_id, user_id, role, int(time()),
    )


async def ensure_plan(conn, plan_id: str = "free", version: int = 1) -> None:
    await conn.execute(
        "INSERT INTO plans (plan_id, version, name, rolling_credits, monthly_credits, requests_per_minute, concurrent_generations, max_output_tokens, input_credit_weight, output_credit_weight, created_at) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11) ON CONFLICT (plan_id, version) DO NOTHING",
        plan_id, version, plan_id, 100000, 100000, 60, 1, 256, 1, 2, int(time()),
    )


async def ensure_entitlement(conn, entitlement_id: str, org_id: str, user_id: str, plan_id: str = "free", plan_version: int = 1) -> None:
    await ensure_membership(conn, org_id, user_id)
    await ensure_plan(conn, plan_id, plan_version)
    await conn.execute(
        "INSERT INTO entitlements (entitlement_id, org_id, user_id, plan_id, plan_version, status, effective_from, billing_anchor) VALUES ($1, $2, $3, $4, $5, 'active', $6, $6) ON CONFLICT (entitlement_id) DO NOTHING",
        entitlement_id, org_id, user_id, plan_id, plan_version, int(time()),
    )


async def ensure_host(conn, org_id: str, host_id: str = "host_default") -> None:
    await ensure_org(conn, org_id)
    await conn.execute(
        "INSERT INTO model_hosts (host_id, org_id, status, created_at) VALUES ($1, $2, 'active', $3) ON CONFLICT (host_id) DO NOTHING",
        host_id, org_id, int(time()),
    )


async def ensure_deployment(conn, org_id: str, deployment_id: str = "dep_default", host_id: str = "host_default", model: str = "org-model") -> None:
    await ensure_host(conn, org_id, host_id)
    await conn.execute(
        "INSERT INTO deployments (deployment_id, org_id, host_id, model, version, model_digest, tokenizer_revision, context_window, capabilities, max_output_tokens, concurrent_slots, status, created_at) VALUES ($1, $2, $3, $4, '1', 'digest', 'tok', 4096, 'chat', 256, 1, 'active', $5) ON CONFLICT (org_id, deployment_id) DO NOTHING",
        deployment_id, org_id, host_id, model, int(time()),
    )


async def ensure_request_context(conn, org_id: str, principal_id: str, request_id: str, model: str = "org-model", input_tokens: int = 0, max_output_tokens: int = 256, key_id = None, deployment_id: str = "dep_default", entitlement_id: str = "ent_default") -> None:
    await ensure_membership(conn, org_id, principal_id)
    await ensure_entitlement(conn, entitlement_id, org_id, principal_id)
    await ensure_deployment(conn, org_id, deployment_id, model=model)
    await conn.execute(
        "INSERT INTO requests (request_id, org_id, principal_id, key_id, deployment_id, entitlement_id, body_hash, state, input_tokens, max_output_tokens, created_at) VALUES ($1, $2, $3, $4, $5, $6, '', 'reserved', $7, $8, $9) ON CONFLICT (org_id, request_id) DO NOTHING",
        request_id, org_id, principal_id, key_id, deployment_id, entitlement_id, input_tokens, max_output_tokens, int(time()),
    )
