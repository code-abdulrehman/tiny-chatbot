"""Security and audit event trail (architecture doc section 8)."""

from dataclasses import dataclass
from typing import Optional

from gateway import errors

AUTH_FAILED = "auth_failed"
KEY_CREATED = "key_created"
KEY_REVOKED = "key_revoked"
KEY_EXPIRED = "key_expired"
SUSPENDED = "suspended"
ELEVATION_GRANTED = "elevation_granted"


@dataclass(frozen=True)
class AuditEvent:
    id: str
    event: str
    subject: str
    detail: Optional[dict]
    timestamp: int


class AuditLog:
    """In-memory MVP audit trail; durable append-only storage comes with the database tier."""

    def __init__(self):
        self._events = []

    def record(self, event: str, subject: str, detail: Optional[dict] = None) -> AuditEvent:
        import time

        entry = AuditEvent(id=f"evt_{len(self._events) + 1}", event=event, subject=subject, detail=detail, timestamp=int(time.time()))
        self._events.append(entry)
        return entry

    def list(self, subject: Optional[str] = None) -> list:
        if subject is None:
            return list(self._events)
        return [event for event in self._events if event.subject == subject]


AUDIT_LOG = AuditLog()


def record(event: str, subject: str, detail: Optional[dict] = None) -> AuditEvent:
    return AUDIT_LOG.record(event, subject, detail)


def require_role(principal, role: str) -> bool:
    """Role checks resolve against the principal's org-scoped roles."""
    return role in principal.roles
