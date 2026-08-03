-- SQLite reference schema for the local TikTok Affiliate Report.
-- The application applies the tables and indexes through versioned SQLAlchemy migrations.
-- The two views below are optional reference queries.

PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS schema_migrations (
    version INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    checksum TEXT NOT NULL,
    applied_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS import_batches (
    id INTEGER PRIMARY KEY,
    file_sha TEXT NOT NULL,
    filename TEXT NOT NULL,
    account TEXT NOT NULL,
    uploaded_by_label TEXT,
    auth_method TEXT,
    auth_subject TEXT,
    inserted INTEGER NOT NULL DEFAULT 0,
    updated INTEGER NOT NULL DEFAULT 0,
    unchanged INTEGER NOT NULL DEFAULT 0,
    rejected INTEGER NOT NULL DEFAULT 0,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (account, file_sha)
);

CREATE INDEX IF NOT EXISTS ix_import_batches_account_created_at
    ON import_batches (account, created_at);

CREATE TABLE IF NOT EXISTS raw_import_rows (
    id INTEGER PRIMARY KEY,
    batch_id INTEGER NOT NULL REFERENCES import_batches(id) ON DELETE RESTRICT,
    row_number INTEGER NOT NULL CHECK (row_number >= 2),
    business_key TEXT NOT NULL,
    raw_json JSON NOT NULL,
    UNIQUE (batch_id, row_number)
);

CREATE INDEX IF NOT EXISTS ix_raw_import_rows_batch_id
    ON raw_import_rows (batch_id);

CREATE TABLE IF NOT EXISTS order_line_versions (
    id INTEGER PRIMARY KEY,
    business_key TEXT NOT NULL,
    account TEXT NOT NULL,
    order_id TEXT,
    sku_id TEXT,
    product_name TEXT,
    shop_name TEXT,
    status TEXT NOT NULL CHECK (status IN ('settled', 'ineligible', 'pending', 'unknown')),
    order_date DATETIME,
    settlement_date DATETIME,
    gmv INTEGER NOT NULL DEFAULT 0,
    units_sold INTEGER NOT NULL DEFAULT 0,
    units_refunded INTEGER NOT NULL DEFAULT 0,
    estimated_commission INTEGER NOT NULL DEFAULT 0,
    final_received INTEGER,
    normalized_hash TEXT NOT NULL,
    raw_json JSON NOT NULL,
    is_current BOOLEAN NOT NULL DEFAULT 1,
    version INTEGER NOT NULL DEFAULT 1,
    batch_id INTEGER NOT NULL REFERENCES import_batches(id) ON DELETE RESTRICT,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (business_key, version)
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_order_line_versions_current
    ON order_line_versions (business_key)
    WHERE is_current = 1;

CREATE INDEX IF NOT EXISTS ix_order_line_versions_account_order_date
    ON order_line_versions (account, order_date)
    WHERE is_current = 1;

CREATE INDEX IF NOT EXISTS ix_order_line_versions_order_id
    ON order_line_versions (order_id);

CREATE INDEX IF NOT EXISTS ix_order_line_versions_sku_id
    ON order_line_versions (sku_id);

CREATE TABLE IF NOT EXISTS monthly_targets (
    id INTEGER PRIMARY KEY,
    account TEXT NOT NULL,
    month DATE NOT NULL,
    target_commission INTEGER NOT NULL,
    UNIQUE (account, month)
);

CREATE TABLE IF NOT EXISTS app_users (
    id INTEGER PRIMARY KEY,
    issuer TEXT NOT NULL,
    subject TEXT NOT NULL,
    email TEXT NOT NULL,
    display_name TEXT,
    role TEXT NOT NULL CHECK (role IN ('owner', 'operator', 'viewer')),
    active BOOLEAN NOT NULL DEFAULT 1,
    last_login_at DATETIME,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (issuer, subject)
);

CREATE INDEX IF NOT EXISTS ix_app_users_email ON app_users (email);

CREATE TABLE IF NOT EXISTS user_account_access (
    user_id INTEGER NOT NULL REFERENCES app_users(id) ON DELETE CASCADE,
    account TEXT NOT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (user_id, account)
);

CREATE INDEX IF NOT EXISTS ix_user_account_access_account ON user_account_access (account);

CREATE TABLE IF NOT EXISTS auth_sessions (
    token_hash TEXT PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES app_users(id) ON DELETE CASCADE,
    csrf_hash TEXT NOT NULL,
    expires_at DATETIME NOT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS ix_auth_sessions_user_id ON auth_sessions (user_id);
CREATE INDEX IF NOT EXISTS ix_auth_sessions_expires_at ON auth_sessions (expires_at);

CREATE TABLE IF NOT EXISTS oidc_login_states (
    state_hash TEXT PRIMARY KEY,
    code_verifier TEXT NOT NULL,
    nonce TEXT NOT NULL,
    expires_at DATETIME NOT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS ix_oidc_login_states_expires_at ON oidc_login_states (expires_at);

CREATE VIEW IF NOT EXISTS v_order_line_current AS
SELECT
    id,
    business_key,
    account,
    order_id,
    sku_id,
    product_name,
    shop_name,
    status,
    order_date,
    settlement_date,
    units_sold,
    units_refunded,
    gmv,
    estimated_commission,
    final_received,
    version,
    batch_id,
    created_at
FROM order_line_versions
WHERE is_current = 1;

CREATE VIEW IF NOT EXISTS v_daily_affiliate_report AS
SELECT
    account,
    date(order_date) AS report_date,
    SUM(units_sold) AS units_sold,
    SUM(units_refunded) AS units_refunded,
    SUM(gmv) AS gross_revenue,
    SUM(estimated_commission) AS initial_commission,
    SUM(CASE WHEN status = 'ineligible' THEN gmv ELSE 0 END) AS cancelled_revenue,
    SUM(CASE WHEN status = 'ineligible' THEN estimated_commission ELSE 0 END) AS cancelled_commission,
    SUM(CASE WHEN status <> 'ineligible' THEN gmv ELSE 0 END) AS actual_revenue,
    SUM(CASE WHEN status <> 'ineligible' THEN estimated_commission ELSE 0 END) AS actual_commission,
    SUM(COALESCE(final_received, 0)) AS final_received
FROM v_order_line_current
WHERE order_date IS NOT NULL
GROUP BY account, date(order_date);

INSERT OR IGNORE INTO monthly_targets (account, month, target_commission)
VALUES
    ('ALL', '2026-03-01', 350000),
    ('ALL', '2026-04-01', 400000),
    ('ALL', '2026-05-01', 450000),
    ('ALL', '2026-06-01', 500000),
    ('ALL', '2026-07-01', 500000),
    ('ALL', '2026-08-01', 500000);
