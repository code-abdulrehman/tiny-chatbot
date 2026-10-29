"""Gateway database tier: stores and in-memory implementations."""

import json
from dataclasses import dataclass
from hashlib import sha256
from time import time
from typing import Optional

import asyncpg
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
    model: str
    credits: int = 0
    state: str = "held"
    created_at: int = 0
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


@dataclass
class AuditEventRecord:
    id: str
    event: str
    subject: str
    detail: Optional[dict] = None
    timestamp: int = 0


@dataclass
class Subscription:
    subscription_id: str
    org_id: str
    status: str = "active"
    plan_id: Optional[str] = None
    created_at: int = 0


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

    def record(self, event: str, subject: str, detail=None) -> AuditEventRecord:
        from time import time

        entry = AuditEventRecord(id=f"evt_{len(self._items) + 1}", event=event, subject=subject, detail=detail, timestamp=int(time()))
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
            "INSERT INTO quota_holds (hold_id, org_id, principal_id, model, credits, state, created_at, settled_at) VALUES ($1, $2, $3, $4, $5, $6, $7, $8)",
            hold.hold_id, hold.org_id, hold.principal_id, hold.model, hold.credits, hold.state, hold.created_at, hold.settled_at,
        )
        return hold

    async def settle(self, hold_id: str, settled_at: int) -> bool:
        result = await self.connection.execute(
            "UPDATE quota_holds SET state = 'settled', settled_at = $2 WHERE hold_id = $1 AND state = 'held'",
            hold_id, settled_at,
        )
        return (result or 0) > 0

    async def release(self, hold_id: str, released_at: int) -> bool:
        result = await self.connection.execute(
            "UPDATE quota_holds SET state = 'released', settled_at = $2 WHERE hold_id = $1 AND state = 'held'",
            hold_id, released_at,
        )
        return (result or 0) > 0

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
            "INSERT INTO usage_ledger (entry_id, org_id, principal_id, request_id, model, input_tokens, output_tokens, credits, phase, created_at) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)",
            entry.entry_id, entry.org_id, entry.principal_id, entry.request_id, entry.model, entry.input_tokens, entry.output_tokens, entry.credits, entry.phase, entry.created_at,
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

    async def record(self, event: str, subject: str, detail=None) -> AuditEventRecord:
        entry = AuditEventRecord(id=f"evt_{uuid4_hex()}", event=event, subject=subject, detail=detail, timestamp=int(time()))
        await self.connection.execute(
            "INSERT INTO audit_events (event_id, event, subject, detail, created_at) VALUES ($1, $2, $3, $4, $5)",
            entry.id, event, subject, json.dumps(detail or {}), entry.timestamp,
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
                "INSERT INTO subscriptions (subscription_id, org_id, status, plan_id, created_at) VALUES ($1, $2, $3, $4, $5) ON CONFLICT (subscription_id) DO UPDATE SET status = EXCLUDED.status, plan_id = EXCLUDED.plan_id",
                obj.get("id"), obj.get("org_id") or "org_unknown", obj.get("status") or "active", price.get("id"), int(time()),
            )
        elif event_type == "customer.subscription.deleted":
            await self.connection.execute(
                "INSERT INTO subscriptions (subscription_id, org_id, status, plan_id, created_at) VALUES ($1, $2, 'cancelled', $3, $4) ON CONFLICT (subscription_id) DO UPDATE SET status = EXCLUDED.status, plan_id = EXCLUDED.plan_id",
                obj.get("id"), obj.get("org_id") or "org_unknown", obj.get("plan_id"), int(time()),
            )
        return result

    async def get(self, subscription_id: str):
        row = await self.connection.fetchrow("SELECT subscription_id, org_id, status, plan_id, created_at FROM subscriptions WHERE subscription_id = $1", subscription_id)
        if row is None:
            return None
        return {"subscription_id": row["subscription_id"], "org_id": row["org_id"], "status": row["status"], "plan_id": row["plan_id"], "created_at": row["created_at"]}


def uuid4_hex() -> str:
    return _uuid4().hex
