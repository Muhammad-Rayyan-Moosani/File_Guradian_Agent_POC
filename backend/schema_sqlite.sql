-- =====================================================================
-- File Guardian Agent — Database Schema (local SQLite version)
--
-- This is the SQLite translation of schema.sql (which targeted Supabase /
-- Postgres). It lets the whole app run on one machine with no cloud database.
--
-- Differences from the Postgres version, and why:
--   * UUID primary keys  -> TEXT. SQLite has no UUID type; the app generates a
--     UUID string in Python (see db.new_id) and stores it as text.
--   * TIMESTAMPTZ        -> TEXT. We store ISO-8601 strings. The defaults below
--     use strftime so a row gets a timestamp like 2026-06-04T12:00:00.000Z.
--   * TEXT[] arrays      -> TEXT holding JSON (e.g. '["a@x.com","b@x.com"]').
--     db.py decodes these back to Python lists on the way out.
--   * BOOLEAN            -> INTEGER (0 = false, 1 = true).
--
-- Every statement uses "IF NOT EXISTS" so this file is safe to run on every
-- startup — it creates anything missing and leaves existing data alone.
-- =====================================================================

-- ---------------------------------------------------------------------
-- 1. VALIDATION PROFILES — one row per file-type the business cares about
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS validation_profiles (
    id                  TEXT PRIMARY KEY,
    name                TEXT NOT NULL,
    description         TEXT,
    active              INTEGER NOT NULL DEFAULT 1,

    file_pattern        TEXT NOT NULL,
    file_type           TEXT NOT NULL DEFAULT 'CSV'
                        CHECK (file_type IN ('CSV', 'JSON', 'XML')),

    allow_extra_columns INTEGER NOT NULL DEFAULT 1,
    -- When 1, the file format is detected from each file's extension (so one
    -- profile can validate CSV, JSON and XML); when 0, file_type is forced.
    auto_detect_type    INTEGER NOT NULL DEFAULT 0,

    inbound_folder      TEXT NOT NULL,
    success_routing     TEXT NOT NULL,
    failure_routing     TEXT NOT NULL,
    unknown_routing     TEXT NOT NULL,

    notify_on_failure   INTEGER NOT NULL DEFAULT 1,
    notify_channel      TEXT NOT NULL DEFAULT 'email'
                        CHECK (notify_channel IN ('email', 'teams', 'both', 'none')),
    email_recipients    TEXT NOT NULL DEFAULT '[]',   -- JSON array of strings
    teams_webhook_url   TEXT,

    created_at          TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    updated_at          TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);

CREATE INDEX IF NOT EXISTS idx_profiles_active ON validation_profiles(active);


-- ---------------------------------------------------------------------
-- 2. PROFILE COLUMNS — one row per declared column, with its constraints
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS profile_columns (
    id              TEXT PRIMARY KEY,
    profile_id      TEXT NOT NULL REFERENCES validation_profiles(id) ON DELETE CASCADE,
    name            TEXT NOT NULL,
    column_order    INTEGER NOT NULL DEFAULT 0,
    description     TEXT,

    required        INTEGER NOT NULL DEFAULT 0,
    unique_flag     INTEGER NOT NULL DEFAULT 0,
    data_type       TEXT
                    CHECK (data_type IN ('string','integer','decimal','date','datetime','email','boolean')),
    min_value       TEXT,
    max_value       TEXT,
    regex_pattern   TEXT,
    allowed_values  TEXT,                          -- JSON array of strings, or NULL = no enum check
    severity        TEXT NOT NULL DEFAULT 'error'
                    CHECK (severity IN ('error','warning')),

    UNIQUE (profile_id, name)
);

CREATE INDEX IF NOT EXISTS idx_columns_profile ON profile_columns(profile_id);


-- ---------------------------------------------------------------------
-- 3. PROFILE CROSS-COLUMN RULES — two-column comparisons
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS profile_cross_column_rules (
    id            TEXT PRIMARY KEY,
    profile_id    TEXT NOT NULL REFERENCES validation_profiles(id) ON DELETE CASCADE,
    name          TEXT NOT NULL,
    left_column   TEXT NOT NULL,
    op            TEXT NOT NULL CHECK (op IN ('gt','gte','lt','lte','eq','neq')),
    right_column  TEXT NOT NULL,
    severity      TEXT NOT NULL DEFAULT 'error'
                  CHECK (severity IN ('error','warning'))
);

CREATE INDEX IF NOT EXISTS idx_cross_rules_profile ON profile_cross_column_rules(profile_id);


-- ---------------------------------------------------------------------
-- 4. APP SETTINGS — single-row table of global defaults
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS app_settings (
    id                     INTEGER PRIMARY KEY CHECK (id = 1),
    processed_folder       TEXT NOT NULL,
    quarantine_folder      TEXT NOT NULL,
    review_folder          TEXT NOT NULL,
    poll_interval_seconds  INTEGER NOT NULL DEFAULT 5,
    notification_channel   TEXT NOT NULL DEFAULT 'email'
                           CHECK (notification_channel IN ('email','teams','both')),
    smtp_host              TEXT,
    smtp_port              INTEGER DEFAULT 587,
    smtp_from              TEXT,
    teams_webhook_url      TEXT,
    default_recipients     TEXT NOT NULL DEFAULT '[]',   -- JSON array of strings

    -- AI provider settings (keys themselves stay in the .env, not here)
    ai_provider            TEXT NOT NULL DEFAULT 'off',  -- off/anthropic/openai/local/vertex
    ai_model               TEXT,
    ai_base_url            TEXT,                          -- for local / vertex (OpenAI-compatible URL)
    vertex_project         TEXT,
    vertex_location        TEXT,
    ai_cli_path            TEXT,                          -- command for the Claude CLI provider (default 'claude')

    updated_at             TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);


-- ---------------------------------------------------------------------
-- 5. VALIDATION RUNS — one per file processed
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS validation_runs (
    id                   TEXT PRIMARY KEY,
    file_name            TEXT NOT NULL,
    file_size_kb         INTEGER,
    received_at          TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    completed_at         TEXT,
    status               TEXT NOT NULL
                         CHECK (status IN ('passed','failed','processing','quarantined','review')),
    -- If a profile is deleted we keep the run but null out the link (the run
    -- still has its profile_name snapshot). Postgres would have blocked the
    -- delete; SET NULL is the friendlier local behaviour.
    profile_id           TEXT REFERENCES validation_profiles(id) ON DELETE SET NULL,
    profile_name         TEXT,
    issue_count          INTEGER NOT NULL DEFAULT 0,
    error_count          INTEGER NOT NULL DEFAULT 0,
    warning_count        INTEGER NOT NULL DEFAULT 0,
    total_rows           INTEGER,
    column_count         INTEGER,
    notification_status  TEXT NOT NULL DEFAULT 'not_required'
                         CHECK (notification_status IN ('sent','not_required','failed','pending')),
    notified_recipients  TEXT NOT NULL DEFAULT '[]',   -- JSON array of strings
    destination_path     TEXT,
    ai_summary           TEXT
);

CREATE INDEX IF NOT EXISTS idx_runs_received_at ON validation_runs(received_at DESC);
CREATE INDEX IF NOT EXISTS idx_runs_status      ON validation_runs(status);


-- ---------------------------------------------------------------------
-- 6. RUN ISSUES — every constraint failure detected on a file
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS run_issues (
    id              TEXT PRIMARY KEY,
    run_id          TEXT NOT NULL REFERENCES validation_runs(id) ON DELETE CASCADE,
    rule_name       TEXT NOT NULL,
    severity        TEXT NOT NULL CHECK (severity IN ('error','warning','info')),
    message         TEXT NOT NULL,
    location        TEXT,
    column_name     TEXT,
    row_number      INTEGER,
    constraint_kind TEXT
                    CHECK (constraint_kind IN
                          ('type','min','max','regex','allowed_values',
                           'unique','required','cross','missing_column'))
);

CREATE INDEX IF NOT EXISTS idx_issues_run_id ON run_issues(run_id);


-- ---------------------------------------------------------------------
-- 7. AGENT EVENTS — workflow timeline per run
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS agent_events (
    id          TEXT PRIMARY KEY,
    run_id      TEXT NOT NULL REFERENCES validation_runs(id) ON DELETE CASCADE,
    agent       TEXT NOT NULL
                CHECK (agent IN ('Monitor','Intake','Planning','Test','Explanation','Notification','Audit')),
    action      TEXT NOT NULL,
    detail      TEXT,
    occurred_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);

CREATE INDEX IF NOT EXISTS idx_events_run_id ON agent_events(run_id, occurred_at);


-- ---------------------------------------------------------------------
-- 8. RUN COLUMN STATISTICS  (one row per column of each processed file)
-- A statistical profile of every file — groundwork for ML-based validation.
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS run_column_stats (
    id                 TEXT PRIMARY KEY,
    run_id             TEXT NOT NULL REFERENCES validation_runs(id) ON DELETE CASCADE,
    column_name        TEXT NOT NULL,
    total_count        INTEGER NOT NULL DEFAULT 0,   -- non-blank values seen
    blank_count        INTEGER NOT NULL DEFAULT 0,
    distinct_count     INTEGER NOT NULL DEFAULT 0,
    distinct_truncated INTEGER NOT NULL DEFAULT 0,   -- 1 if distinct tracking hit its cap
    numeric_min        REAL,
    numeric_max        REAL,
    numeric_mean       REAL,
    text_min_length    INTEGER,
    text_max_length    INTEGER,
    top_values         TEXT                          -- JSON array of {value, count}
);

CREATE INDEX IF NOT EXISTS idx_col_stats_run ON run_column_stats(run_id);


-- =====================================================================
-- SEED — default settings row (id = 1). Only inserted if it is missing,
-- so re-running this script never clobbers settings the user has changed.
-- =====================================================================
INSERT OR IGNORE INTO app_settings (
    id, processed_folder, quarantine_folder, review_folder,
    poll_interval_seconds, notification_channel, smtp_host, smtp_port, smtp_from,
    default_recipients
) VALUES (
    1,
    'C:\FileGuardian\processed\good',
    'C:\FileGuardian\processed\quarantine',
    'C:\FileGuardian\processed\review',
    5, 'email', 'smtp.xorbix.com', 587, 'fileguardian@xorbix.com',
    '["ops-team@xorbix.com"]'
);
