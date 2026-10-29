-- Model gateway database schema (PostgreSQL).
-- Mirrors the tables described in docs/model-gateway-architecture.md section 7.

CREATE TABLE IF NOT EXISTS organizations (
    org_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    created_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS users (
    user_id TEXT NOT NULL,
    org_id TEXT NOT NULL REFERENCES organizations (org_id),
    email TEXT NOT NULL DEFAULT '',
    state TEXT NOT NULL DEFAULT 'active',
    created_at INTEGER NOT NULL,
    PRIMARY KEY (org_id, user_id)
);

CREATE TABLE IF NOT EXISTS memberships (
    org_id TEXT NOT NULL REFERENCES organizations (org_id),
    user_id TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'member',
    status TEXT NOT NULL DEFAULT 'active',
    PRIMARY KEY (org_id, user_id)
);

CREATE TABLE IF NOT EXISTS api_keys (
    key_hash TEXT PRIMARY KEY,
    key_id TEXT NOT NULL,
    org_id TEXT NOT NULL REFERENCES organizations (org_id),
    principal_id TEXT NOT NULL,
    scopes TEXT NOT NULL,
    state TEXT NOT NULL DEFAULT 'active',
    expires_at INTEGER,
    created_at INTEGER NOT NULL,
    last_used_at INTEGER
);

CREATE TABLE IF NOT EXISTS model_hosts (
    host_id TEXT PRIMARY KEY,
    org_id TEXT NOT NULL REFERENCES organizations (org_id),
    status TEXT NOT NULL DEFAULT 'offline',
    last_heartbeat INTEGER
);

CREATE TABLE IF NOT EXISTS deployments (
    deployment_id TEXT PRIMARY KEY,
    host_id TEXT NOT NULL REFERENCES model_hosts (host_id),
    org_id TEXT NOT NULL REFERENCES organizations (org_id),
    model TEXT NOT NULL,
    version TEXT NOT NULL,
    context_window INTEGER NOT NULL,
    capabilities TEXT NOT NULL,
    created_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS plans (
    plan_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    rolling_credits INTEGER NOT NULL,
    monthly_credits INTEGER NOT NULL,
    requests_per_minute INTEGER NOT NULL,
    max_output_tokens INTEGER NOT NULL,
    version INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS entitlements (
    entitlement_id TEXT PRIMARY KEY,
    org_id TEXT NOT NULL REFERENCES organizations (org_id),
    user_id TEXT NOT NULL,
    plan_id TEXT NOT NULL REFERENCES plans (plan_id),
    status TEXT NOT NULL DEFAULT 'active',
    effective_from INTEGER NOT NULL,
    effective_until INTEGER
);

CREATE TABLE IF NOT EXISTS subscriptions (
    subscription_id TEXT PRIMARY KEY,
    org_id TEXT NOT NULL REFERENCES organizations (org_id),
    status TEXT NOT NULL,
    plan_id TEXT,
    created_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS requests (
    request_id TEXT PRIMARY KEY,
    org_id TEXT NOT NULL REFERENCES organizations (org_id),
    principal_id TEXT NOT NULL,
    key_id TEXT,
    model TEXT NOT NULL,
    deployment_id TEXT,
    idempotency_key TEXT,
    state TEXT NOT NULL,
    created_at INTEGER NOT NULL,
    settled_at INTEGER
);

CREATE TABLE IF NOT EXISTS idempotency_keys (
    idempotency_key TEXT PRIMARY KEY,
    request_id TEXT NOT NULL REFERENCES requests (request_id),
    body_hash TEXT NOT NULL,
    created_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS quota_holds (
    hold_id TEXT PRIMARY KEY,
    org_id TEXT NOT NULL REFERENCES organizations (org_id),
    principal_id TEXT NOT NULL,
    model TEXT NOT NULL,
    credits INTEGER NOT NULL,
    state TEXT NOT NULL DEFAULT 'held',
    created_at INTEGER NOT NULL,
    settled_at INTEGER
);

CREATE TABLE IF NOT EXISTS usage_ledger (
    entry_id TEXT PRIMARY KEY,
    org_id TEXT NOT NULL REFERENCES organizations (org_id),
    principal_id TEXT NOT NULL,
    request_id TEXT NOT NULL REFERENCES requests (request_id),
    model TEXT NOT NULL,
    input_tokens INTEGER NOT NULL DEFAULT 0,
    output_tokens INTEGER NOT NULL DEFAULT 0,
    credits INTEGER NOT NULL DEFAULT 0,
    phase TEXT NOT NULL,
    created_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS audit_events (
    event_id TEXT PRIMARY KEY,
    event TEXT NOT NULL,
    subject TEXT NOT NULL,
    detail TEXT,
    created_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS webhook_events (
    event_id TEXT PRIMARY KEY,
    signature_valid BOOLEAN NOT NULL,
    processing_state TEXT NOT NULL,
    subscription_id TEXT,
    created_at INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_usage_org_principal_created ON usage_ledger (org_id, principal_id, created_at);
CREATE INDEX IF NOT EXISTS idx_holds_status_expires ON quota_holds (state, created_at);
CREATE INDEX IF NOT EXISTS idx_keys_org_prefix ON api_keys (org_id, key_hash);
