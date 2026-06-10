"""
Local database layer — a thin, beginner-readable wrapper over one SQLite file.

This replaces the old Supabase (cloud Postgres) client so the whole app can
run on a single machine with no internet connection. It opens the database
file, creates the tables on first use, and offers a few small helpers
(query / insert / update / delete) that the rest of the backend calls instead
of talking to Supabase.

The table shapes are identical to the old Postgres schema, so every other part
of the app (and the frontend) keeps working unchanged.
"""

import os
import sys
import json
import uuid
import sqlite3
from pathlib import Path

# Make sibling modules (paths, logging_setup) importable no matter who imports
# us first.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from logging_setup import get_logger  # noqa: E402
import paths  # noqa: E402

log = get_logger("DB")

# Where the database file lives and where to find the schema. paths.py figures
# out the right spot whether we run from source or as a bundled .exe; FG_DB_PATH
# still overrides the database location.
DB_PATH = paths.DB_PATH
SCHEMA_PATH = paths.SCHEMA_PATH

# Columns that hold a list of strings. In Postgres these were TEXT[] arrays;
# in SQLite we store them as JSON text and decode them back to Python lists
# whenever a row is read.
ARRAY_COLUMNS = {
    "email_recipients",
    "allowed_values",
    "notified_recipients",
    "default_recipients",
}


def new_id():
    """
    Make a new unique id string (a UUID4), used as a table primary key.
    Parameters: none.
    Returns: str.
    """
    return str(uuid.uuid4())


def get_connection():
    """
    Open a fresh SQLite connection with foreign keys and dict-style rows on.
    A new connection per call keeps things safe across the Monitor's worker
    threads and the API's request threads.
    Returns: an open sqlite3.Connection (the caller is responsible for closing).
    """
    connection = sqlite3.connect(DB_PATH, timeout=30)
    connection.row_factory = sqlite3.Row
    # Foreign keys are off by default in SQLite; turn them on so ON DELETE
    # CASCADE actually removes child rows. WAL mode lets reads and one writer
    # work at the same time, which suits the parallel file workers.
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA journal_mode = WAL")
    return connection


def init_db():
    """
    Create the database file and all tables if they do not exist yet.
    Safe to call on every startup — the schema script uses IF NOT EXISTS.
    Parameters: none.
    Returns: None.
    """
    schema_sql = SCHEMA_PATH.read_text()
    connection = get_connection()
    try:
        connection.executescript(schema_sql)
        connection.commit()
    finally:
        connection.close()

    # Add any newer columns to tables that already existed from an older version
    # (CREATE TABLE IF NOT EXISTS won't alter an existing table).
    ensure_columns("app_settings", {
        "ai_provider": "TEXT NOT NULL DEFAULT 'off'",
        "ai_model": "TEXT",
        "ai_base_url": "TEXT",
        "vertex_project": "TEXT",
        "vertex_location": "TEXT",
        "ai_cli_path": "TEXT",
    })

    log.info("Database ready at %s", DB_PATH)


def ensure_columns(table, columns):
    """
    Add any missing columns to an existing table (a simple forward migration).
    Parameters: table (str), columns (dict of column name -> column definition).
    Returns: None.
    """
    connection = get_connection()
    try:
        rows = connection.execute("PRAGMA table_info({})".format(table)).fetchall()
        existing = set()
        for row in rows:
            existing.add(row["name"])
        for name, definition in columns.items():
            if name not in existing:
                connection.execute(
                    "ALTER TABLE {} ADD COLUMN {} {}".format(table, name, definition))
                log.info("Added new column %s.%s", table, name)
        connection.commit()
    finally:
        connection.close()


def decode_row(row):
    """
    Turn a sqlite3.Row into a plain dict, decoding JSON list columns to lists.
    Parameters: row (sqlite3.Row).
    Returns: dict.
    """
    result = {}
    for key in row.keys():
        value = row[key]
        if key in ARRAY_COLUMNS and value is not None:
            result[key] = json.loads(value)
        else:
            result[key] = value
    return result


def encode_value(column, value):
    """
    Prepare a Python value for storage (a list column becomes JSON text).
    Parameters: column (str name), value (the value to store).
    Returns: a value SQLite can store directly.
    """
    if column in ARRAY_COLUMNS and isinstance(value, list):
        return json.dumps(value)
    return value


# Note on the "{}".format(table, ...) below: table and column names come from
# our own code (constants in the backend), never from user input, so building
# the SQL text this way is safe. All actual values still go through ? params.


def query_all(sql, params=()):
    """
    Run a SELECT and return every matching row as a list of dicts.
    Parameters: sql (str), params (tuple of values for the ? placeholders).
    Returns: list of dicts (empty list if nothing matched).
    """
    connection = get_connection()
    try:
        cursor = connection.execute(sql, params)
        rows = cursor.fetchall()
    finally:
        connection.close()

    results = []
    for row in rows:
        results.append(decode_row(row))
    return results


def query_one(sql, params=()):
    """
    Run a SELECT and return the first matching row as a dict, or None.
    Parameters: sql (str), params (tuple).
    Returns: dict or None.
    """
    rows = query_all(sql, params)
    if rows:
        return rows[0]
    return None


def get_by_id(table, row_id):
    """
    Fetch a single row from a table by its id.
    Parameters: table (str), row_id (the id value to look up).
    Returns: dict or None.
    """
    return query_one("SELECT * FROM {} WHERE id = ?".format(table), (row_id,))


def insert(table, row):
    """
    Insert one row (a dict of column -> value) and return it back as stored.
    A text id is generated when the row has none; list columns are saved as JSON.
    Parameters: table (str), row (dict).
    Returns: the stored row as a dict.
    """
    row = dict(row)
    if "id" not in row:
        row["id"] = new_id()

    columns = list(row.keys())
    placeholders = ", ".join(["?"] * len(columns))

    values = []
    for column in columns:
        values.append(encode_value(column, row[column]))

    sql = "INSERT INTO {} ({}) VALUES ({})".format(
        table, ", ".join(columns), placeholders)

    connection = get_connection()
    try:
        connection.execute(sql, values)
        connection.commit()
    finally:
        connection.close()

    return get_by_id(table, row["id"])


def insert_many(table, rows):
    """
    Insert a list of rows into a table in one transaction.
    Each row gets a generated id when it has none; list columns are saved as JSON.
    All rows are expected to have the same set of columns.
    Parameters: table (str), rows (list of dicts).
    Returns: None.
    """
    if not rows:
        return

    prepared = []
    for row in rows:
        row = dict(row)
        if "id" not in row:
            row["id"] = new_id()
        prepared.append(row)

    columns = list(prepared[0].keys())
    placeholders = ", ".join(["?"] * len(columns))
    sql = "INSERT INTO {} ({}) VALUES ({})".format(
        table, ", ".join(columns), placeholders)

    value_rows = []
    for row in prepared:
        values = []
        for column in columns:
            values.append(encode_value(column, row.get(column)))
        value_rows.append(values)

    connection = get_connection()
    try:
        connection.executemany(sql, value_rows)
        connection.commit()
    finally:
        connection.close()


def update(table, row_id, fields):
    """
    Update one row (found by its id) with the given fields.
    List columns are saved as JSON.
    Parameters: table (str), row_id (the id value), fields (dict of changes).
    Returns: None.
    """
    if not fields:
        return

    assignments = []
    values = []
    for column in fields:
        assignments.append("{} = ?".format(column))
        values.append(encode_value(column, fields[column]))
    values.append(row_id)

    sql = "UPDATE {} SET {} WHERE id = ?".format(table, ", ".join(assignments))

    connection = get_connection()
    try:
        connection.execute(sql, values)
        connection.commit()
    finally:
        connection.close()


def delete_where(table, column, value):
    """
    Delete every row in a table whose column equals the given value.
    Child rows are removed automatically via ON DELETE CASCADE.
    Parameters: table (str), column (str), value (the value to match).
    Returns: None.
    """
    sql = "DELETE FROM {} WHERE {} = ?".format(table, column)

    connection = get_connection()
    try:
        connection.execute(sql, (value,))
        connection.commit()
    finally:
        connection.close()


def replace_settings(row):
    """
    Save the single app_settings row (id = 1), inserting or replacing it.
    Parameters: row (dict of settings columns; the id is forced to 1).
    Returns: the stored settings row as a dict.
    """
    row = dict(row)
    row["id"] = 1

    columns = list(row.keys())
    placeholders = ", ".join(["?"] * len(columns))

    values = []
    for column in columns:
        values.append(encode_value(column, row[column]))

    sql = "INSERT OR REPLACE INTO app_settings ({}) VALUES ({})".format(
        ", ".join(columns), placeholders)

    connection = get_connection()
    try:
        connection.execute(sql, values)
        connection.commit()
    finally:
        connection.close()

    return get_by_id("app_settings", 1)


# Prepare the database as soon as this module is imported, so every entry point
# (app.py, the API, the Monitor, the demo seeder) finds the tables ready.
init_db()
