"""Authentication and authorization primitives (architecture doc section 3)."""

from dataclasses import dataclass
from hashlib import sha256
from typing import Optional

from gateway import errors

INFERENCE_CHAT = "inference:chat"
USAGE_READ = "usage:read"
KEYS_WRITE = "keys:write"


@dataclass(frozen=True)
class Principal:
    org_id: str
    principal_id: str
    roles: frozenset
    scopes: frozenset
    state: str  # active | suspended
    key_id: Optional[str] = None


@dataclass
class APIKeyRecord:
    key_hash: str
    key_id: str
    org_id: str
    principal_id: str
    scopes: frozenset
    state: str  # active | suspended | revoked


def hash_api_key(api_key: str) -> str:
    return sha256(api_key.encode("utf-8")).hexdigest()


class InMemoryKeyStore:
    """MVP key store; replaced by the database-backed key/tenant tier."""

    def __init__(self):
        self._keys = {}

    def add(self, key_id: str, api_key: str, org_id: str, principal_id: str, scopes, state: str = "active") -> APIKeyRecord:
        record = APIKeyRecord(
            key_hash=hash_api_key(api_key),
            key_id=key_id,
            org_id=org_id,
            principal_id=principal_id,
            scopes=frozenset(scopes),
            state=state,
        )
        self._keys[record.key_hash] = record
        return record

    def verify(self, api_key: str) -> Optional[APIKeyRecord]:
        return self._keys.get(hash_api_key(api_key))


def resolve_principal(api_key: str, store: InMemoryKeyStore, dev_api_key: str = "") -> Principal:
    if dev_api_key and api_key == dev_api_key:
        return Principal(org_id="local-dev", principal_id="dev-owner", roles=frozenset({"owner"}), scopes=frozenset({"inference:chat", "usage:read", "keys:write", "admin"}), state="active", key_id="dev")
    record = store.verify(api_key)
    if record is None:
        raise errors.unauthenticated("Unknown API key.")
    if record.state == "revoked":
        raise errors.key_revoked("This API key has been revoked.")
    if record.state == "suspended":
        raise errors.account_suspended("This API key is suspended.")
    return Principal(org_id=record.org_id, principal_id=record.principal_id, roles=frozenset({"member"}), scopes=record.scopes, state="active", key_id=record.key_id)
