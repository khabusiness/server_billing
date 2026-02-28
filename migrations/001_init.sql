CREATE TABLE IF NOT EXISTS subscription_verifications (
    id UUID PRIMARY KEY,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    app_id VARCHAR(64) NOT NULL,
    package_name VARCHAR(255) NOT NULL,
    subscription_id VARCHAR(255) NOT NULL,
    user_id VARCHAR(128) NOT NULL,
    purchase_token_hash VARCHAR(64) NOT NULL,
    active BOOLEAN NOT NULL,
    status VARCHAR(32) NOT NULL,
    expiry_time_ms BIGINT NOT NULL DEFAULT 0,
    is_trial BOOLEAN NOT NULL DEFAULT FALSE,
    auto_renewing BOOLEAN NOT NULL DEFAULT FALSE,
    raw_google_response JSONB NULL
);

CREATE INDEX IF NOT EXISTS idx_sub_ver_app_user
    ON subscription_verifications (app_id, user_id);
CREATE INDEX IF NOT EXISTS idx_sub_ver_token_hash
    ON subscription_verifications (purchase_token_hash);
CREATE INDEX IF NOT EXISTS idx_sub_ver_expiry_time_ms
    ON subscription_verifications (expiry_time_ms);

CREATE TABLE IF NOT EXISTS entitlements (
    app_id VARCHAR(64) NOT NULL,
    user_id VARCHAR(128) NOT NULL,
    purchase_token_hash VARCHAR(64) NOT NULL,
    status VARCHAR(32) NOT NULL,
    active BOOLEAN NOT NULL,
    expiry_time_ms BIGINT NOT NULL DEFAULT 0,
    last_verified_ms BIGINT NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT pk_entitlements PRIMARY KEY (app_id, user_id)
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_entitlements_app_user
    ON entitlements (app_id, user_id);
CREATE INDEX IF NOT EXISTS idx_entitlements_token_hash
    ON entitlements (purchase_token_hash);
