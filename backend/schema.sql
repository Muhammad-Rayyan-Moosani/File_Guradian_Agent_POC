-- =====================================================================
-- File Guardian Agent — Database Schema (v2, per-column constraint model)
-- Designed for Supabase / Postgres. Run this in the Supabase SQL editor.
--
-- Safe to re-run: drops the old objects first so you can paste this on
-- top of any previous version of the schema during development.
-- =====================================================================

-- Clean slate (only affects this project's tables) ---------------------
DROP TABLE IF EXISTS agent_events           CASCADE;
DROP TABLE IF EXISTS run_issues             CASCADE;
DROP TABLE IF EXISTS validation_runs        CASCADE;
DROP TABLE IF EXISTS profile_cross_column_rules CASCADE;
DROP TABLE IF EXISTS profile_columns        CASCADE;
DROP TABLE IF EXISTS profile_rules          CASCADE;   -- legacy v1
DROP TABLE IF EXISTS rule_catalog           CASCADE;   -- legacy v1
DROP TABLE IF EXISTS validation_profiles    CASCADE;
DROP TABLE IF EXISTS app_settings           CASCADE;

-- ---------------------------------------------------------------------
-- 1. VALIDATION PROFILES
-- One row per file-type the business cares about (Invoice CSV, PO CSV, …)
-- ---------------------------------------------------------------------
CREATE TABLE validation_profiles (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name                TEXT NOT NULL,
    description         TEXT,
    active              BOOLEAN NOT NULL DEFAULT TRUE,

    file_pattern        TEXT NOT NULL,                          -- 'invoices_*.csv'
    file_type           TEXT NOT NULL DEFAULT 'CSV'
                        CHECK (file_type IN ('CSV', 'JSON', 'XML')),

    allow_extra_columns BOOLEAN NOT NULL DEFAULT TRUE,

    -- Per-profile folder paths
    inbound_folder      TEXT NOT NULL,
    success_routing     TEXT NOT NULL,
    failure_routing     TEXT NOT NULL,
    unknown_routing     TEXT NOT NULL,

    -- Notifications
    notify_on_failure   BOOLEAN NOT NULL DEFAULT TRUE,
    notify_channel      TEXT NOT NULL DEFAULT 'email'
                        CHECK (notify_channel IN ('email', 'teams', 'both', 'none')),
    email_recipients    TEXT[] NOT NULL DEFAULT '{}',
    teams_webhook_url   TEXT,

    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_profiles_active ON validation_profiles(active);


-- ---------------------------------------------------------------------
-- 2. PROFILE COLUMNS
-- One row per column declared in a profile. Each row carries the
-- constraints applied to that column.
-- ---------------------------------------------------------------------
CREATE TABLE profile_columns (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    profile_id      UUID NOT NULL REFERENCES validation_profiles(id) ON DELETE CASCADE,
    name            TEXT NOT NULL,
    column_order    INT  NOT NULL DEFAULT 0,
    description     TEXT,

    required        BOOLEAN NOT NULL DEFAULT FALSE,
    unique_flag     BOOLEAN NOT NULL DEFAULT FALSE,
    data_type       TEXT
                    CHECK (data_type IN ('string','integer','decimal','date','datetime','email','boolean')),
    min_value       TEXT,                              -- TEXT to hold dates too
    max_value       TEXT,
    regex_pattern   TEXT,
    allowed_values  TEXT[],                            -- NULL = no enum check
    severity        TEXT NOT NULL DEFAULT 'error'
                    CHECK (severity IN ('error','warning')),

    UNIQUE (profile_id, name)
);

CREATE INDEX idx_columns_profile ON profile_columns(profile_id);


-- ---------------------------------------------------------------------
-- 3. PROFILE CROSS-COLUMN RULES
-- Two-column comparisons like `DueDate > InvoiceDate`.
-- ---------------------------------------------------------------------
CREATE TABLE profile_cross_column_rules (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    profile_id    UUID NOT NULL REFERENCES validation_profiles(id) ON DELETE CASCADE,
    name          TEXT NOT NULL,
    left_column   TEXT NOT NULL,
    op            TEXT NOT NULL CHECK (op IN ('gt','gte','lt','lte','eq','neq')),
    right_column  TEXT NOT NULL,
    severity      TEXT NOT NULL DEFAULT 'error'
                  CHECK (severity IN ('error','warning'))
);

CREATE INDEX idx_cross_rules_profile ON profile_cross_column_rules(profile_id);


-- ---------------------------------------------------------------------
-- 4. APP SETTINGS  (single-row table, holds global defaults)
-- ---------------------------------------------------------------------
CREATE TABLE app_settings (
    id                     INT PRIMARY KEY DEFAULT 1 CHECK (id = 1),
    processed_folder       TEXT NOT NULL,
    quarantine_folder      TEXT NOT NULL,
    review_folder          TEXT NOT NULL,
    poll_interval_seconds  INT NOT NULL DEFAULT 5,
    notification_channel   TEXT NOT NULL DEFAULT 'email'
                           CHECK (notification_channel IN ('email','teams','both')),
    smtp_host              TEXT,
    smtp_port              INT DEFAULT 587,
    smtp_from              TEXT,
    teams_webhook_url      TEXT,
    default_recipients     TEXT[] NOT NULL DEFAULT '{}',
    updated_at             TIMESTAMPTZ NOT NULL DEFAULT now()
);


-- ---------------------------------------------------------------------
-- 5. VALIDATION RUNS  (one per file processed)
-- ---------------------------------------------------------------------
CREATE TABLE validation_runs (
    id                   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    file_name            TEXT NOT NULL,
    file_size_kb         INT,
    received_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    completed_at         TIMESTAMPTZ,
    status               TEXT NOT NULL
                         CHECK (status IN ('passed','failed','processing','quarantined','review')),
    profile_id           UUID REFERENCES validation_profiles(id),
    profile_name         TEXT,                                  -- denormalised snapshot
    issue_count          INT NOT NULL DEFAULT 0,
    error_count          INT NOT NULL DEFAULT 0,
    warning_count        INT NOT NULL DEFAULT 0,
    notification_status  TEXT NOT NULL DEFAULT 'not_required'
                         CHECK (notification_status IN ('sent','not_required','failed','pending')),
    notified_recipients  TEXT[] NOT NULL DEFAULT '{}',
    destination_path     TEXT,
    ai_summary           TEXT
);

CREATE INDEX idx_runs_received_at ON validation_runs(received_at DESC);
CREATE INDEX idx_runs_status      ON validation_runs(status);


-- ---------------------------------------------------------------------
-- 6. RUN ISSUES  (every constraint failure detected on a file)
-- ---------------------------------------------------------------------
CREATE TABLE run_issues (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id          UUID NOT NULL REFERENCES validation_runs(id) ON DELETE CASCADE,
    rule_name       TEXT NOT NULL,
    severity        TEXT NOT NULL CHECK (severity IN ('error','warning','info')),
    message         TEXT NOT NULL,
    location        TEXT,                                       -- free-form, e.g. 'row 14, column Amount'
    column_name     TEXT,
    row_number      INT,
    constraint_kind TEXT
                    CHECK (constraint_kind IN
                          ('type','min','max','regex','allowed_values',
                           'unique','required','cross','missing_column'))
);

CREATE INDEX idx_issues_run_id ON run_issues(run_id);


-- ---------------------------------------------------------------------
-- 7. AGENT EVENTS  (workflow timeline per run)
-- ---------------------------------------------------------------------
CREATE TABLE agent_events (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id      UUID NOT NULL REFERENCES validation_runs(id) ON DELETE CASCADE,
    agent       TEXT NOT NULL
                CHECK (agent IN ('Monitor','Intake','Planning','Test','Explanation','Notification','Audit')),
    action      TEXT NOT NULL,
    detail      TEXT,
    occurred_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_events_run_id ON agent_events(run_id, occurred_at);


-- =====================================================================
-- SEED DATA — default settings + a starter Invoice CSV profile.
-- Safe to delete from the Supabase dashboard later if you want a clean db.
-- =====================================================================

INSERT INTO app_settings (
    id, processed_folder, quarantine_folder, review_folder,
    poll_interval_seconds, notification_channel, smtp_host, smtp_port, smtp_from,
    default_recipients
) VALUES (
    1,
    'C:\FileGuardian\processed\good',
    'C:\FileGuardian\processed\quarantine',
    'C:\FileGuardian\processed\review',
    5, 'email', 'smtp.xorbix.com', 587, 'fileguardian@xorbix.com',
    ARRAY['ops-team@xorbix.com']
);

-- Starter profile (optional). Comment out if you want to test "Save" from
-- the frontend without an existing row present.
WITH new_profile AS (
    INSERT INTO validation_profiles (
        name, description, active,
        file_pattern, file_type, allow_extra_columns,
        inbound_folder, success_routing, failure_routing, unknown_routing,
        notify_on_failure, notify_channel, email_recipients
    ) VALUES (
        'Invoice CSV Validation',
        'Validates incoming invoice CSV files from vendors.',
        TRUE,
        'invoices_*.csv', 'CSV', TRUE,
        'C:\FileGuardian\inbound\invoices',
        'C:\FileGuardian\processed\good',
        'C:\FileGuardian\processed\quarantine',
        'C:\FileGuardian\processed\review',
        TRUE, 'email',
        ARRAY['ops-team@xorbix.com','billing-lead@xorbix.com']
    )
    RETURNING id
)
INSERT INTO profile_columns
    (profile_id, name, column_order, required, unique_flag, data_type,
     min_value, regex_pattern, allowed_values, severity)
SELECT np.id, c.name, c.col_order, c.required, c.uniq, c.data_type,
       c.min_value, c.regex_pattern, c.allowed_values, c.severity
FROM new_profile np
CROSS JOIN (VALUES
    ('CustomerId',    0, TRUE,  FALSE, 'string'::TEXT, NULL::TEXT, NULL::TEXT, NULL::TEXT[], 'error'::TEXT),
    ('CustomerName',  1, TRUE,  FALSE, 'string',       NULL,       NULL,       NULL,         'error'),
    ('InvoiceNumber', 2, TRUE,  TRUE,  'string',       NULL,       '^INV-\d{4,8}$', NULL,    'error'),
    ('InvoiceDate',   3, TRUE,  FALSE, 'date',         NULL,       NULL,       NULL,         'error'),
    ('Amount',        4, TRUE,  FALSE, 'decimal',      '0.01',     NULL,       NULL,         'error'),
    ('Email',         5, FALSE, FALSE, 'email',        NULL,       NULL,       NULL,         'warning'),
    ('Status',        6, FALSE, FALSE, 'string',       NULL,       NULL,       ARRAY['PAID','DUE','VOID'], 'warning')
) AS c(name, col_order, required, uniq, data_type, min_value, regex_pattern, allowed_values, severity);
