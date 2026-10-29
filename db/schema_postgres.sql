-- Fresh PostgreSQL schema for the model gateway. Times are UTC Unix seconds.
-- Apply to an empty database. Existing installations need a reviewed data migration.
CREATE TABLE organizations (
  org_id TEXT PRIMARY KEY,
  name TEXT NOT NULL CHECK (length(trim(name)) > 0),
  status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active','suspended','closed')),
  created_at BIGINT NOT NULL
);

CREATE TABLE users (
  user_id TEXT PRIMARY KEY,
  email TEXT NOT NULL UNIQUE,
  state TEXT NOT NULL DEFAULT 'active' CHECK (state IN ('active','suspended','deleted')),
  created_at BIGINT NOT NULL
);

CREATE TABLE memberships (
  org_id TEXT NOT NULL REFERENCES organizations(org_id),
  user_id TEXT NOT NULL REFERENCES users(user_id),
  role TEXT NOT NULL CHECK (role IN ('owner','admin','member')),
  status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active','suspended','removed')),
  created_at BIGINT NOT NULL,
  PRIMARY KEY (org_id,user_id)
);

CREATE TABLE api_keys (
  key_id TEXT PRIMARY KEY,
  org_id TEXT NOT NULL,
  principal_id TEXT NOT NULL,
  key_prefix TEXT NOT NULL,
  key_hash TEXT NOT NULL UNIQUE,
  scopes TEXT NOT NULL,
  model_restrictions TEXT,
  state TEXT NOT NULL DEFAULT 'active' CHECK (state IN ('active','revoked','expired','suspended')),
  expires_at BIGINT,
  created_at BIGINT NOT NULL,
  last_used_at BIGINT,
  FOREIGN KEY (org_id,principal_id) REFERENCES memberships(org_id,user_id)
);

CREATE TABLE model_hosts (
  host_id TEXT PRIMARY KEY,
  org_id TEXT NOT NULL REFERENCES organizations(org_id),
  status TEXT NOT NULL DEFAULT 'offline' CHECK (status IN ('offline','pending','active','draining','revoked')),
  credential_fingerprint TEXT UNIQUE,
  last_heartbeat BIGINT,
  created_at BIGINT NOT NULL,
  UNIQUE (org_id,host_id)
);

CREATE TABLE deployments (
  deployment_id TEXT PRIMARY KEY,
  org_id TEXT NOT NULL,
  host_id TEXT NOT NULL,
  model TEXT NOT NULL,
  version TEXT NOT NULL,
  model_digest TEXT NOT NULL,
  tokenizer_revision TEXT NOT NULL,
  context_window INTEGER NOT NULL CHECK (context_window > 0),
  capabilities TEXT NOT NULL,
  max_output_tokens INTEGER NOT NULL CHECK (max_output_tokens > 0),
  concurrent_slots INTEGER NOT NULL DEFAULT 1 CHECK (concurrent_slots > 0),
  status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','active','draining','revoked')),
  created_at BIGINT NOT NULL,
  FOREIGN KEY (org_id,host_id) REFERENCES model_hosts(org_id,host_id),
  UNIQUE (org_id,model,version),
  UNIQUE (org_id,deployment_id)
);

CREATE TABLE plans (
  plan_id TEXT NOT NULL,
  version INTEGER NOT NULL CHECK (version > 0),
  name TEXT NOT NULL,
  rolling_credits BIGINT NOT NULL CHECK (rolling_credits >= 0),
  monthly_credits BIGINT NOT NULL CHECK (monthly_credits >= 0),
  requests_per_minute INTEGER NOT NULL CHECK (requests_per_minute > 0),
  concurrent_generations INTEGER NOT NULL DEFAULT 1 CHECK (concurrent_generations > 0),
  max_output_tokens INTEGER NOT NULL CHECK (max_output_tokens > 0),
  input_credit_weight NUMERIC(12,4) NOT NULL DEFAULT 1 CHECK (input_credit_weight >= 0),
  output_credit_weight NUMERIC(12,4) NOT NULL DEFAULT 2 CHECK (output_credit_weight >= 0),
  created_at BIGINT NOT NULL,
  PRIMARY KEY (plan_id,version)
);

CREATE TABLE entitlements (
  entitlement_id TEXT PRIMARY KEY,
  org_id TEXT NOT NULL REFERENCES organizations(org_id),
  user_id TEXT,
  plan_id TEXT NOT NULL,
  plan_version INTEGER NOT NULL,
  status TEXT NOT NULL CHECK (status IN ('active','grace','suspended','expired')),
  effective_from BIGINT NOT NULL,
  effective_until BIGINT,
  billing_anchor BIGINT NOT NULL,
  FOREIGN KEY (org_id,user_id) REFERENCES memberships(org_id,user_id),
  FOREIGN KEY (plan_id,plan_version) REFERENCES plans(plan_id,version),
  CHECK (effective_until IS NULL OR effective_until > effective_from)
);

CREATE TABLE subscriptions (
  subscription_id TEXT PRIMARY KEY,
  org_id TEXT NOT NULL REFERENCES organizations(org_id),
  provider TEXT NOT NULL DEFAULT 'stripe',
  provider_customer_id TEXT,
  status TEXT NOT NULL,
  plan_id TEXT,
  created_at BIGINT NOT NULL,
  updated_at BIGINT NOT NULL
);

CREATE TABLE requests (
  request_id TEXT PRIMARY KEY,
  org_id TEXT NOT NULL,
  principal_id TEXT NOT NULL,
  key_id TEXT,
  deployment_id TEXT NOT NULL,
  entitlement_id TEXT NOT NULL REFERENCES entitlements(entitlement_id),
  body_hash TEXT NOT NULL,
  state TEXT NOT NULL CHECK (state IN ('reserved','running','completed','failed','cancelled','reconciling')),
  input_tokens INTEGER NOT NULL CHECK (input_tokens >= 0),
  max_output_tokens INTEGER NOT NULL CHECK (max_output_tokens > 0),
  created_at BIGINT NOT NULL,
  settled_at BIGINT,
  FOREIGN KEY (org_id,principal_id) REFERENCES memberships(org_id,user_id),
  FOREIGN KEY (org_id,deployment_id) REFERENCES deployments(org_id,deployment_id),
  FOREIGN KEY (key_id) REFERENCES api_keys(key_id),
  UNIQUE (org_id,request_id)
);

CREATE TABLE idempotency_keys (
  org_id TEXT NOT NULL,
  principal_id TEXT NOT NULL,
  endpoint TEXT NOT NULL,
  idempotency_key TEXT NOT NULL,
  request_id TEXT NOT NULL UNIQUE,
  body_hash TEXT NOT NULL,
  created_at BIGINT NOT NULL,
  PRIMARY KEY (org_id,principal_id,endpoint,idempotency_key),
  FOREIGN KEY (org_id,principal_id) REFERENCES memberships(org_id,user_id),
  FOREIGN KEY (org_id,request_id) REFERENCES requests(org_id,request_id)
);

CREATE TABLE quota_holds (
  hold_id TEXT PRIMARY KEY,
  org_id TEXT NOT NULL,
  principal_id TEXT NOT NULL,
  request_id TEXT NOT NULL UNIQUE,
  model TEXT NOT NULL,
  credits BIGINT NOT NULL CHECK (credits >= 0),
  state TEXT NOT NULL DEFAULT 'held' CHECK (state IN ('held','settled','released')),
  created_at BIGINT NOT NULL,
  expires_at BIGINT NOT NULL,
  settled_at BIGINT,
  FOREIGN KEY (org_id,request_id) REFERENCES requests(org_id,request_id)
);

CREATE TABLE usage_ledger (
  entry_id TEXT PRIMARY KEY,
  org_id TEXT NOT NULL,
  principal_id TEXT NOT NULL,
  request_id TEXT NOT NULL,
  model TEXT NOT NULL,
  input_tokens INTEGER NOT NULL DEFAULT 0 CHECK (input_tokens >= 0),
  output_tokens INTEGER NOT NULL DEFAULT 0 CHECK (output_tokens >= 0),
  credits BIGINT NOT NULL CHECK (credits >= 0 OR phase = 'adjustment'),
  phase TEXT NOT NULL CHECK (phase IN ('reserve','settle','release','adjustment')),
  usage_source TEXT NOT NULL DEFAULT 'model' CHECK (usage_source IN ('model','estimated','manual')),
  created_at BIGINT NOT NULL,
  FOREIGN KEY (org_id,request_id) REFERENCES requests(org_id,request_id)
);

CREATE TABLE guardrail_events (
  event_id TEXT PRIMARY KEY,
  org_id TEXT NOT NULL REFERENCES organizations(org_id),
  request_id TEXT,
  policy_version TEXT NOT NULL,
  decision TEXT NOT NULL CHECK (decision IN ('allow','deny','review')),
  detail JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at BIGINT NOT NULL,
  FOREIGN KEY (org_id,request_id) REFERENCES requests(org_id,request_id)
);

CREATE TABLE audit_events (
  event_id TEXT PRIMARY KEY,
  org_id TEXT NOT NULL REFERENCES organizations(org_id),
  actor_id TEXT,
  event TEXT NOT NULL,
  subject TEXT NOT NULL,
  detail JSONB NOT NULL DEFAULT '{}'::jsonb,
  request_id TEXT,
  created_at BIGINT NOT NULL
);

CREATE TABLE webhook_events (
  event_id TEXT PRIMARY KEY,
  provider TEXT NOT NULL,
  signature_valid BOOLEAN NOT NULL,
  processing_state TEXT NOT NULL CHECK (processing_state IN ('received','processed','failed')),
  subscription_id TEXT REFERENCES subscriptions(subscription_id),
  created_at BIGINT NOT NULL,
  processed_at BIGINT
);

CREATE INDEX idx_usage_org_principal_created ON usage_ledger(org_id,principal_id,created_at);
CREATE UNIQUE INDEX idx_usage_one_terminal_phase ON usage_ledger(request_id,phase)
  WHERE phase IN ('reserve','settle','release');
CREATE INDEX idx_audit_org_actor_created ON audit_events(org_id,actor_id,created_at);
CREATE INDEX idx_holds_status_expires ON quota_holds(state,expires_at);
CREATE INDEX idx_keys_org_prefix ON api_keys(org_id,key_prefix);
CREATE INDEX idx_requests_org_principal_created ON requests(org_id,principal_id,created_at);
CREATE INDEX idx_deployments_active ON deployments(org_id,model) WHERE status = 'active';
CREATE INDEX idx_entitlements_effective ON entitlements(org_id,user_id,effective_from,effective_until);

-- Financial and security history is append-only. Corrections use new rows.
CREATE FUNCTION prevent_gateway_history_change() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  RAISE EXCEPTION '% is append-only', TG_TABLE_NAME;
END
$$;
CREATE TRIGGER usage_ledger_append_only BEFORE UPDATE OR DELETE ON usage_ledger
  FOR EACH ROW EXECUTE FUNCTION prevent_gateway_history_change();
CREATE TRIGGER audit_events_append_only BEFORE UPDATE OR DELETE ON audit_events
  FOR EACH ROW EXECUTE FUNCTION prevent_gateway_history_change();
