"""OpenRouter-style model router.

Maps a requested model ID to an approved host adapter and supports fallback chains.
Implements the routing decisions from docs/model-gateway-architecture.md section 2.
"""

from typing import Optional, Sequence

from gateway import errors


class Router:
    """Resolves requested model IDs to approved adapters with optional fallbacks."""

    def __init__(self, approved_hosts: Optional[Sequence[str]] = None):
        self._entries: dict = {}
        self._approved_hosts: frozenset = frozenset(approved_hosts or ())

    def register(self, adapter, host_id: str):
        deployment = adapter.describe()
        self._entries[deployment.model] = {"host_id": host_id, "adapter": adapter}
        return adapter

    def hosts(self) -> frozenset:
        return self._approved_hosts

    def deployments(self) -> list:
        deployments = []
        for model, entry in sorted(self._entries.items()):
            deployment = entry["adapter"].describe()
            deployments.append({
                "model": model,
                "host_id": entry["host_id"],
                "context_window": deployment.context_window,
                "capabilities": sorted(deployment.capabilities),
            })
        return deployments

    def resolve(self, model: str):
        entry = self._entries.get(model)
        if entry is None:
            raise errors.GatewayError("model_not_found", f"No approved deployment for model '{model}'.")
        host_id = entry["host_id"]
        adapter = entry["adapter"]
        if self._approved_hosts and host_id not in self._approved_hosts:
            raise errors.GatewayError("forbidden", f"Host {host_id} is not approved for this gateway.", {"host_id": host_id})
        return adapter

    def resolve_with_fallback(self, model: str, fallbacks: Optional[Sequence[str]] = None):
        """Return (adapter, resolved_model) trying the requested model then fallbacks."""
        adapter = self.resolve(model)
        for fallback in fallbacks or ():
            try:
                fallback_adapter = self.resolve(fallback)
            except errors.GatewayError:
                continue
            return fallback_adapter, fallback
        return adapter, model
