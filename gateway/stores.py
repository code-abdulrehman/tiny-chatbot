"""Gateway database tier: stores and in-memory implementations."""

from dataclasses import dataclass
from typing import Optional


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
