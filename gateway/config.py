"""Gateway settings loaded from the environment."""

import os


def _setting(name, default):
    value = os.environ.get(name)
    return default if value is None or value == "" else value


def _int_setting(name, default):
    try:
        return int(_setting(name, str(default)))
    except (TypeError, ValueError):
        return default


DATABASE_URL = _setting("GATEWAY_DATABASE_URL", "postgresql+psycopg://localhost:5432/gateway")
HOST = _setting("GATEWAY_HOST", "127.0.0.1")
PORT = _int_setting("GATEWAY_PORT", 8080)
DEV_API_KEY = _setting("GATEWAY_DEV_API_KEY", "")
FREE_CREDITS = _int_setting("GATEWAY_FREE_CREDITS", 10_000)
MAX_OUTPUT_TOKENS = _int_setting("GATEWAY_MAX_OUTPUT_TOKENS", 256)
SESSION_TTL_SECONDS = _int_setting("GATEWAY_SESSION_TTL_SECONDS", 3600)
RATE_LIMIT_REQUESTS_PER_MINUTE = _int_setting("GATEWAY_RATE_LIMIT_REQUESTS_PER_MINUTE", 10)
CONCURRENT_GENERATIONS = _int_setting("GATEWAY_CONCURRENT_GENERATIONS", 1)
STRIPE_WEBHOOK_SECRET = _setting("GATEWAY_STRIPE_WEBHOOK_SECRET", "")

ALL_SCOPES = frozenset({"inference:chat", "usage:read", "keys:write", "admin"})
