-- ChurnIQ PostgreSQL Schema
-- Run this once against a fresh Supabase / Postgres database.
-- All tables use UUID primary keys and updated_at triggers.

-- ---------------------------------------------------------------------------
-- Extensions
-- ---------------------------------------------------------------------------
CREATE EXTENSION IF NOT EXISTS "pgcrypto";   -- gen_random_uuid()
CREATE EXTENSION IF NOT EXISTS "pg_trgm";    -- fuzzy search on customer names

-- ---------------------------------------------------------------------------
-- Helpers
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION set_updated_at()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
  NEW.updated_at = NOW();
  RETURN NEW;
END;
$$;

-- ---------------------------------------------------------------------------
-- ENUM types
-- ---------------------------------------------------------------------------
CREATE TYPE risk_tier AS ENUM ('low', 'medium', 'high', 'critical');
CREATE TYPE plan_type  AS ENUM ('free', 'starter', 'growth', 'enterprise');

-- ---------------------------------------------------------------------------
-- users  (tenants / dashboard operators)
-- ---------------------------------------------------------------------------
CREATE TABLE users (
  id                UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
  email             TEXT        NOT NULL UNIQUE,
  hashed_password   TEXT        NOT NULL,
  full_name         TEXT        NOT NULL,
  is_active         BOOLEAN     NOT NULL DEFAULT TRUE,
  is_superuser      BOOLEAN     NOT NULL DEFAULT FALSE,
  created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at        TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TRIGGER trg_users_updated_at
  BEFORE UPDATE ON users
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- ---------------------------------------------------------------------------
-- refresh_tokens  (JWT refresh token store — revocation support)
-- ---------------------------------------------------------------------------
CREATE TABLE refresh_tokens (
  id          UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id     UUID        NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  token_hash  TEXT        NOT NULL UNIQUE,  -- SHA-256 of raw token
  expires_at  TIMESTAMPTZ NOT NULL,
  revoked     BOOLEAN     NOT NULL DEFAULT FALSE,
  created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_refresh_tokens_user_id  ON refresh_tokens(user_id);
CREATE INDEX idx_refresh_tokens_hash     ON refresh_tokens(token_hash);

-- ---------------------------------------------------------------------------
-- customers  (end-customers the tenant tracks for churn)
-- ---------------------------------------------------------------------------
CREATE TABLE customers (
  id                      UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id                 UUID        NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  external_id             TEXT,                         -- tenant's own customer ID
  name                    TEXT        NOT NULL,
  email                   TEXT,
  phone                   TEXT,

  -- Subscription
  plan                    plan_type   NOT NULL DEFAULT 'starter',
  monthly_revenue         NUMERIC(10,2) NOT NULL DEFAULT 0,
  contract_length_months  INT,                          -- NULL = month-to-month
  signup_date             DATE        NOT NULL,
  contract_end_date       DATE,

  -- Engagement signals (refreshed by ETL / CSV upload)
  last_activity_date      DATE,
  logins_last_30d         INT         NOT NULL DEFAULT 0,
  feature_usage_score     NUMERIC(5,2),                 -- 0–100
  support_tickets_open    INT         NOT NULL DEFAULT 0,
  support_tickets_total   INT         NOT NULL DEFAULT 0,
  nps_score               SMALLINT,                     -- -100 to 100
  billing_issues_count    INT         NOT NULL DEFAULT 0,

  -- Firmographics
  country                 CHAR(2),                      -- ISO 3166-1 alpha-2
  industry                TEXT,
  company_size            TEXT,                         -- 'small' / 'mid' / 'large'

  -- Ground truth (populated once churn is confirmed)
  is_churned              BOOLEAN     NOT NULL DEFAULT FALSE,
  churned_at              DATE,

  created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at              TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_customers_user_id   ON customers(user_id);
CREATE INDEX idx_customers_ext_id    ON customers(user_id, external_id);
CREATE INDEX idx_customers_plan      ON customers(plan);
CREATE INDEX idx_customers_churned   ON customers(is_churned);
CREATE INDEX idx_customers_name_trgm ON customers USING GIN (name gin_trgm_ops);

CREATE TRIGGER trg_customers_updated_at
  BEFORE UPDATE ON customers
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- ---------------------------------------------------------------------------
-- model_versions  (registry of trained ML models)
-- ---------------------------------------------------------------------------
CREATE TABLE model_versions (
  id                  UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
  version_name        TEXT        NOT NULL UNIQUE,   -- e.g. 'v1.2.0-xgb'
  algorithm           TEXT        NOT NULL,          -- 'xgboost' / 'logistic_regression'
  trained_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  training_rows       INT,
  auc_roc             NUMERIC(6,4),
  accuracy            NUMERIC(6,4),
  precision_score     NUMERIC(6,4),
  recall_score        NUMERIC(6,4),
  f1_score            NUMERIC(6,4),
  feature_names       JSONB,                         -- ordered list of feature columns
  feature_importance  JSONB,                         -- {feature: importance_score}
  hyperparameters     JSONB,                         -- Optuna best params
  model_artifact_path TEXT,                          -- S3 / GCS / local path
  is_active           BOOLEAN     NOT NULL DEFAULT FALSE,
  created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_model_versions_active ON model_versions(is_active);

-- Only one model can be active at a time
CREATE UNIQUE INDEX idx_one_active_model
  ON model_versions(is_active)
  WHERE is_active = TRUE;

-- ---------------------------------------------------------------------------
-- churn_predictions  (one row per customer per model run)
-- ---------------------------------------------------------------------------
CREATE TABLE churn_predictions (
  id                  UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
  customer_id         UUID        NOT NULL REFERENCES customers(id) ON DELETE CASCADE,
  model_version_id    UUID        NOT NULL REFERENCES model_versions(id),
  churn_probability   NUMERIC(5,4) NOT NULL,            -- 0.0000 – 1.0000
  risk_tier           risk_tier   NOT NULL,
  shap_values         JSONB,                            -- {feature: shap_value}
  top_factors         JSONB,                            -- [{feature, direction, magnitude}]
  predicted_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_predictions_customer    ON churn_predictions(customer_id);
CREATE INDEX idx_predictions_model       ON churn_predictions(model_version_id);
CREATE INDEX idx_predictions_risk        ON churn_predictions(risk_tier);
CREATE INDEX idx_predictions_predicted   ON churn_predictions(predicted_at DESC);

-- Latest prediction per customer (used by dashboard queries)
CREATE INDEX idx_predictions_latest
  ON churn_predictions(customer_id, predicted_at DESC);

-- ---------------------------------------------------------------------------
-- analytics_snapshots  (daily aggregates per tenant — pre-computed for speed)
-- ---------------------------------------------------------------------------
CREATE TABLE analytics_snapshots (
  id                    UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id               UUID        NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  snapshot_date         DATE        NOT NULL,
  total_customers       INT         NOT NULL DEFAULT 0,
  active_customers      INT         NOT NULL DEFAULT 0,
  churned_this_period   INT         NOT NULL DEFAULT 0,
  churn_rate            NUMERIC(6,4),                    -- fraction 0–1
  mrr                   NUMERIC(12,2),                   -- total monthly recurring revenue
  mrr_at_risk           NUMERIC(12,2),                   -- MRR from high+critical tier
  avg_churn_probability NUMERIC(5,4),
  critical_risk_count   INT         NOT NULL DEFAULT 0,
  high_risk_count       INT         NOT NULL DEFAULT 0,
  medium_risk_count     INT         NOT NULL DEFAULT 0,
  low_risk_count        INT         NOT NULL DEFAULT 0,
  created_at            TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE (user_id, snapshot_date)
);

CREATE INDEX idx_snapshots_user_date ON analytics_snapshots(user_id, snapshot_date DESC);
