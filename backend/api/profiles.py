"""
Profiles API — CRUD for validation_profiles + its two child tables.
Run: python -m api.profiles
"""

import os
import sys
import hmac
import shutil
import tempfile
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
from flask import Flask, jsonify, request, send_from_directory, session
from flask_cors import CORS

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from logging_setup import get_logger  # noqa: E402
import db  # noqa: E402
import paths  # noqa: E402
import infer_columns  # noqa: E402

log = get_logger("Profiles API")

# Admin login settings come from the .env (next to the .exe when bundled).
load_dotenv(paths.ENV_FILE)

app = Flask(__name__)
# Used to sign the login session cookie. Set FG_SECRET_KEY in the .env to keep
# people logged in across restarts; otherwise a fresh random key is used each
# start (which simply means everyone has to log in again after a restart).
app.secret_key = os.getenv("FG_SECRET_KEY") or os.urandom(32)
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
# Only allow the local frontend (Vite dev server + production preview) to call
# the API — not any website the browser happens to visit.
CORS(app, resources={r"/api/*": {"origins": [
    "http://localhost:6200", "http://127.0.0.1:6200",
]}})

# Reject any single uploaded request body larger than 25 MB. (CSV files are
# dropped into folders, not POSTed, so requests themselves should stay small.)
app.config["MAX_CONTENT_LENGTH"] = 25 * 1024 * 1024

# Mount the read-only runs endpoints (/api/runs, /api/runs/<id>)
from api.runs import runs_bp  # noqa: E402
app.register_blueprint(runs_bp)

# Mount the settings endpoints (/api/settings)
from api.settings import settings_bp  # noqa: E402
app.register_blueprint(settings_bp)


# ─── admin login ─────────────────────────────────────────────────────────────
# Login is OPT-IN: it only turns on when both ADMIN_USERNAME and ADMIN_PASSWORD
# are set in the .env. With them unset (e.g. during development), the app stays
# open exactly as before. Dropping files into the watched folders is never
# affected — that is the filesystem, not this web app.

# These API paths are always reachable so the login page can work + check state.
PUBLIC_API_PATHS = {"/api/login", "/api/logout", "/api/me", "/api/health"}


def auth_enabled():
    """
    Tell whether admin login is switched on (both credentials set in the .env).
    Parameters: none.
    Returns: bool.
    """
    return bool(os.getenv("ADMIN_USERNAME") and os.getenv("ADMIN_PASSWORD"))


def credentials_match(username, password):
    """
    Compare a submitted username/password against the .env values safely.
    Uses a constant-time compare so timing can't leak the real values.
    Parameters: username (str), password (str).
    Returns: bool.
    """
    expected_user = os.getenv("ADMIN_USERNAME") or ""
    expected_pass = os.getenv("ADMIN_PASSWORD") or ""
    user_ok = hmac.compare_digest(username or "", expected_user)
    pass_ok = hmac.compare_digest(password or "", expected_pass)
    return user_ok and pass_ok


def is_logged_in():
    """
    Tell whether the current request is allowed through (logged in, or auth off).
    Parameters: none.
    Returns: bool.
    """
    if not auth_enabled():
        return True
    return bool(session.get("admin"))


@app.before_request
def require_admin_login():
    """
    Block API calls that need a login when login is on and nobody is signed in.
    The static frontend (so the login page can load) and a few public API
    endpoints are always allowed.
    Parameters: none (reads the incoming request).
    Returns: None to allow, or a 401 JSON response to block.
    """
    if not auth_enabled():
        return None
    if request.method == "OPTIONS":
        return None
    path = request.path
    # Let the frontend's static files load so the login screen can appear.
    if not path.startswith("/api/"):
        return None
    if path in PUBLIC_API_PATHS:
        return None
    if session.get("admin"):
        return None
    return jsonify({"error": "Authentication required"}), 401


@app.get("/api/me")
def whoami():
    """
    Report whether login is required and whether this visitor is signed in.
    Parameters: none.
    Returns: JSON {authEnabled, authenticated, username}.
    """
    return jsonify({
        "authEnabled": auth_enabled(),
        "authenticated": is_logged_in(),
        "username": session.get("username"),
    })


@app.post("/api/login")
def login():
    """
    Sign an admin in by username + password (checked against the .env).
    Parameters: none (reads a JSON body {username, password}).
    Returns: JSON on success, or a 401 error on bad credentials.
    """
    if not auth_enabled():
        # Login is off — nothing to do; everyone is already "in".
        return jsonify({"authEnabled": False, "authenticated": True})

    body = request.get_json(silent=True) or {}
    username = body.get("username", "")
    password = body.get("password", "")
    if not credentials_match(username, password):
        log.warning("Failed admin login attempt for user %r", username)
        return jsonify({"error": "Invalid username or password"}), 401

    session["admin"] = True
    session["username"] = username
    log.info("Admin %r logged in", username)
    return jsonify({"authEnabled": True, "authenticated": True, "username": username})


@app.post("/api/logout")
def logout():
    """
    Sign the current admin out by clearing their session.
    Parameters: none.
    Returns: JSON {authEnabled, authenticated}.
    """
    session.clear()
    return jsonify({"authEnabled": auth_enabled(), "authenticated": False})


# ─── helpers ───────────────────────────────────────────────────────────────

REQUIRED_FIELDS = (
    "name", "filePattern", "inboundFolder",
    "successRouting", "failureRouting", "unknownRouting",
)


def to_db_profile(body: dict) -> dict:
    """Map the frontend JSON shape to validation_profiles columns."""
    return {
        "name": body["name"],
        "description": body.get("description"),
        "active": bool(body.get("active", True)),
        "file_pattern": body["filePattern"],
        "file_type": body.get("fileType", "CSV"),
        "allow_extra_columns": bool(body.get("allowExtraColumns", True)),
        "auto_detect_type": bool(body.get("autoDetectType", False)),
        "inbound_folder": body["inboundFolder"],
        "success_routing": body["successRouting"],
        "failure_routing": body["failureRouting"],
        "unknown_routing": body["unknownRouting"],
        "notify_on_failure": bool(body.get("notifyOnFailure", True)),
        "notify_channel": body.get("notifyChannel", "email"),
        "email_recipients": body.get("recipients") or [],
        "teams_webhook_url": body.get("teamsWebhookUrl"),
    }


def to_db_columns(profile_id: str, columns: list) -> list[dict]:
    rows = []
    for i, col in enumerate(columns):
        name = (col.get("name") or "").strip()
        if not name:
            raise ValueError(f"Column at index {i} has no name")
        c = col.get("constraints") or {}
        rows.append({
            "profile_id": profile_id,
            "name": name,
            "column_order": col.get("order", i),
            "description": col.get("description"),
            "required": bool(c.get("required", False)),
            "unique_flag": bool(c.get("unique", False)),
            "data_type": c.get("type"),
            "min_value": None if c.get("min") in (None, "") else str(c["min"]),
            "max_value": None if c.get("max") in (None, "") else str(c["max"]),
            "regex_pattern": c.get("regex"),
            "allowed_values": c.get("allowedValues"),
            "severity": c.get("severity", "error"),
        })
    return rows


def to_db_cross_rules(profile_id: str, rules: list) -> list[dict]:
    return [{
        "profile_id": profile_id,
        "name": r.get("name") or f"{r['leftColumn']} {r['op']} {r['rightColumn']}",
        "left_column": r["leftColumn"],
        "op": r["op"],
        "right_column": r["rightColumn"],
        "severity": r.get("severity", "error"),
    } for r in rules]


def insert_children(profile_id: str, columns: list, cross_rules: list) -> None:
    col_rows = to_db_columns(profile_id, columns)
    if col_rows:
        db.insert_many("profile_columns", col_rows)
    cross_rows = to_db_cross_rules(profile_id, cross_rules)
    if cross_rows:
        db.insert_many("profile_cross_column_rules", cross_rows)


def shape_profile(p: dict, cols: list, cross: list) -> dict:
    """
    Build the frontend profile shape from a profile row + its children.
    Parameters: p (profile row), cols (its column rows), cross (its cross rows).
    Returns: dict in the frontend ValidationProfile shape.
    """
    return {
        "id": p["id"],
        "name": p["name"],
        "description": p.get("description") or "",
        "active": bool(p.get("active", True)),
        "filePattern": p["file_pattern"],
        "fileType": p.get("file_type", "CSV"),
        "allowExtraColumns": bool(p.get("allow_extra_columns", True)),
        "autoDetectType": bool(p.get("auto_detect_type", False)),
        "inboundFolder": p["inbound_folder"],
        "successRouting": p["success_routing"],
        "failureRouting": p["failure_routing"],
        "unknownRouting": p["unknown_routing"],
        "notifyOnFailure": bool(p.get("notify_on_failure", True)),
        "recipients": p.get("email_recipients") or [],
        "createdAt": p.get("created_at"),
        "updatedAt": p.get("updated_at"),
        "columns": [{
            "id": c["id"],
            "name": c["name"],
            "order": c.get("column_order", 0),
            "description": c.get("description"),
            "constraints": {
                "required": bool(c.get("required")),
                "unique": bool(c.get("unique_flag")),
                "type": c.get("data_type"),
                "min": c.get("min_value"),
                "max": c.get("max_value"),
                "regex": c.get("regex_pattern"),
                "allowedValues": c.get("allowed_values"),
                "severity": c.get("severity", "error"),
            },
        } for c in cols],
        "crossColumnRules": [{
            "id": r["id"],
            "name": r["name"],
            "leftColumn": r["left_column"],
            "op": r["op"],
            "rightColumn": r["right_column"],
            "severity": r.get("severity", "error"),
        } for r in cross],
    }


def group_by_profile(rows: list) -> dict:
    """
    Group child rows (columns or cross-rules) into a dict keyed by profile_id.
    Parameters: rows (list of child rows, each with a profile_id).
    Returns: dict mapping profile_id -> list of its rows.
    """
    grouped = {}
    for row in rows:
        grouped.setdefault(row["profile_id"], []).append(row)
    return grouped


def load_profile(profile_id: str) -> dict | None:
    """Load one profile row + its children and shape it for the frontend."""
    profile = db.query_one(
        "SELECT * FROM validation_profiles WHERE id = ?", (profile_id,))
    if not profile:
        return None

    cols = db.query_all(
        "SELECT * FROM profile_columns WHERE profile_id = ? ORDER BY column_order",
        (profile_id,))
    cross = db.query_all(
        "SELECT * FROM profile_cross_column_rules WHERE profile_id = ?",
        (profile_id,))
    return shape_profile(profile, cols, cross)


def load_all_profiles() -> list:
    """
    Load every profile with its children using just three queries total.
    This replaces the old per-profile loop (which did 3 queries per profile
    and made the page slow once there were many profiles).
    Parameters: none.
    Returns: list of frontend profile dicts, newest first.
    """
    profiles = db.query_all(
        "SELECT * FROM validation_profiles ORDER BY created_at DESC")
    if not profiles:
        return []

    # One query for all columns, one for all cross-rules, then group in memory.
    all_cols = db.query_all("SELECT * FROM profile_columns")
    all_cross = db.query_all("SELECT * FROM profile_cross_column_rules")
    cols_by_profile = group_by_profile(all_cols)
    cross_by_profile = group_by_profile(all_cross)

    shaped = []
    for p in profiles:
        cols = cols_by_profile.get(p["id"], [])
        cols.sort(key=lambda c: c.get("column_order", 0))
        cross = cross_by_profile.get(p["id"], [])
        shaped.append(shape_profile(p, cols, cross))
    return shaped


def validate_body(body):
    """Returns an (error_response, status) tuple, or None if OK."""
    if not isinstance(body, dict):
        return jsonify({"error": "Request body must be JSON"}), 400
    missing = [k for k in REQUIRED_FIELDS if not body.get(k)]
    if missing:
        return jsonify({"error": "Missing required fields", "fields": missing}), 400
    if not body.get("columns"):
        return jsonify({"error": "At least one column is required"}), 400
    return None


# ─── routes ────────────────────────────────────────────────────────────────

@app.get("/api/health")
def health():
    return jsonify({"ok": True, "db_path": db.DB_PATH})


@app.get("/api/profiles")
def list_profiles():
    log.info("GET /api/profiles")
    profiles = load_all_profiles()
    log.info("Returned %d profile(s)", len(profiles))
    return jsonify(profiles)


@app.get("/api/profiles/<profile_id>")
def get_profile(profile_id):
    log.info("GET /api/profiles/%s", profile_id)
    profile = load_profile(profile_id)
    if not profile:
        return jsonify({"error": "Profile not found"}), 404
    return jsonify(profile)


@app.post("/api/profiles/infer-from-sample")
def infer_from_sample():
    """
    Infer columns from an uploaded sample CSV, optionally AI-enhanced.
    Reads a multipart 'file'; add ?enhance=true to turn on AI enrichment.
    Returns: JSON {columns, aiSuggestedColumns, aiUsed, rowCount}.
    """
    log.info("POST /api/profiles/infer-from-sample")
    uploaded = request.files.get("file")
    if uploaded is None or uploaded.filename == "":
        return jsonify({"error": "No file uploaded"}), 400

    enhance_flag = request.args.get("enhance", "").lower()
    want_ai = enhance_flag in ("1", "true", "yes")

    try:
        result = infer_columns.infer_columns(uploaded.stream)
    except Exception as e:
        log.exception("Could not read the sample file")
        return jsonify({"error": "Could not read the CSV file", "detail": str(e)}), 400

    columns = result["columns"]
    ai_ids = []
    if want_ai:
        columns, ai_ids = infer_columns.enhance_with_ai(columns, result["samples"])

    return jsonify({
        "columns": columns,
        "aiSuggestedColumns": ai_ids,
        "aiUsed": len(ai_ids) > 0,
        "rowCount": result["row_count"],
    })


@app.post("/api/profiles/<profile_id>/validate-sample")
def validate_sample(profile_id):
    """
    Validate an uploaded file against an existing profile and record a run —
    exactly as if the file had been dropped into the profile's inbound folder.
    Used so the sample file used to create a profile is also processed and shown
    in the dashboard (moved to the good or quarantine folder).
    Reads a multipart 'file'. Returns JSON {runId, status}.
    """
    log.info("POST /api/profiles/%s/validate-sample", profile_id)
    profile = db.query_one(
        "SELECT * FROM validation_profiles WHERE id = ?", (profile_id,))
    if not profile:
        return jsonify({"error": "Profile not found"}), 404

    uploaded = request.files.get("file")
    if uploaded is None or uploaded.filename == "":
        return jsonify({"error": "No file uploaded"}), 400

    # Save the upload to a temporary folder (NOT a watched inbound folder, so the
    # Monitor doesn't also pick it up). The pipeline moves it to the good or
    # quarantine folder, leaving this temp folder empty.
    staging_dir = tempfile.mkdtemp(prefix="fg_upload_")
    file_name = os.path.basename(uploaded.filename)
    staging_path = os.path.join(staging_dir, file_name)
    uploaded.save(staging_path)

    file_info = {
        "file_path": staging_path,
        "file_type": os.path.splitext(file_name)[1].lower(),
        "received_at": datetime.now().isoformat(),
        "file_size": os.path.getsize(staging_path),
    }

    try:
        from pipeline import run_pipeline_for_profile
        result = run_pipeline_for_profile(file_info, profile)
    except Exception as e:
        log.exception("Could not validate the uploaded sample")
        return jsonify({"error": "Could not validate the file", "detail": str(e)}), 500
    finally:
        shutil.rmtree(staging_dir, ignore_errors=True)

    return jsonify({"runId": result["run_id"], "status": result["status"]})


@app.post("/api/profiles")
def create_profile():
    log.info("POST /api/profiles")
    body = request.get_json(silent=True)
    err = validate_body(body)
    if err:
        return err

    try:
        inserted = db.insert("validation_profiles", to_db_profile(body))
        profile_id = inserted["id"]
    except Exception as e:
        log.exception("Insert failed")
        return jsonify({"error": "Failed to insert profile", "detail": str(e)}), 500

    try:
        insert_children(profile_id, body["columns"], body.get("crossColumnRules") or [])
    except Exception as e:
        # Cascade delete cleans up any half-saved children
        db.delete_where("validation_profiles", "id", profile_id)
        log.exception("Failed to insert children")
        return jsonify({"error": "Failed to insert profile children", "detail": str(e)}), 500

    return jsonify(load_profile(profile_id)), 201


@app.put("/api/profiles/<profile_id>")
def update_profile(profile_id):
    log.info("PUT /api/profiles/%s", profile_id)
    body = request.get_json(silent=True)
    err = validate_body(body)
    if err:
        return err

    existing = db.query_one(
        "SELECT id FROM validation_profiles WHERE id = ?", (profile_id,))
    if not existing:
        return jsonify({"error": "Profile not found"}), 404

    # Snapshot children so we can restore on failure
    prev_cols = db.query_all(
        "SELECT * FROM profile_columns WHERE profile_id = ?", (profile_id,))
    prev_cross = db.query_all(
        "SELECT * FROM profile_cross_column_rules WHERE profile_id = ?", (profile_id,))

    try:
        db.update("validation_profiles", profile_id, to_db_profile(body))
        db.delete_where("profile_columns", "profile_id", profile_id)
        db.delete_where("profile_cross_column_rules", "profile_id", profile_id)
        insert_children(profile_id, body["columns"], body.get("crossColumnRules") or [])
    except Exception as e:
        log.exception("Update failed, restoring previous children")
        db.delete_where("profile_columns", "profile_id", profile_id)
        db.delete_where("profile_cross_column_rules", "profile_id", profile_id)
        if prev_cols:
            db.insert_many("profile_columns", prev_cols)
        if prev_cross:
            db.insert_many("profile_cross_column_rules", prev_cross)
        return jsonify({"error": "Failed to update profile", "detail": str(e)}), 500

    return jsonify(load_profile(profile_id))


@app.delete("/api/profiles/<profile_id>")
def delete_profile(profile_id):
    log.info("DELETE /api/profiles/%s", profile_id)
    existing = db.query_one(
        "SELECT id FROM validation_profiles WHERE id = ?", (profile_id,))
    if not existing:
        return jsonify({"error": "Profile not found"}), 404
    db.delete_where("validation_profiles", "id", profile_id)
    return jsonify({"id": profile_id, "ok": True, "deleted": True})


# ─── frontend (production) ───────────────────────────────────────────────────
# In production there is no separate Vite server. Flask serves the built React
# app (frontend/dist) from this same port, so the whole product is one process
# that can later be bundled into a single Windows .exe. Build it first with
# `npm run build` in the frontend folder.

FRONTEND_DIST = paths.FRONTEND_DIST


@app.route("/", defaults={"path": ""})
@app.route("/<path:path>")
def serve_frontend(path):
    """
    Serve the built React app, falling back to index.html for client routes.
    The /api/* endpoints are handled by their own routes and never reach here.
    Parameters: path (str) — the part of the URL after the domain.
    Returns: a static file, the app's index.html, or a small message/404.
    """
    # An /api path that reaches this catch-all matched no real endpoint.
    if path.startswith("api/"):
        return jsonify({"error": "Not found"}), 404

    # If the app has not been built yet, point the developer at the next step.
    index_file = FRONTEND_DIST / "index.html"
    if not index_file.is_file():
        return (
            "Frontend is not built yet. Run 'npm run build' in the frontend "
            "folder, or use the Vite dev server at http://localhost:6200.",
            200,
        )

    # Serve a real built file when one exists (e.g. /assets/index-abc123.js).
    requested = FRONTEND_DIST / path
    if path and requested.is_file():
        return send_from_directory(FRONTEND_DIST, path)

    # Otherwise it is a client-side route (e.g. /profiles) — hand back the app
    # and let React Router show the right page.
    return send_from_directory(FRONTEND_DIST, "index.html")


if __name__ == "__main__":
    # Run the API on its own (without the Monitor). The normal way to start
    # everything is `python app.py`. debug stays off so no second process
    # spawns and so tracebacks are never exposed.
    log.info("Starting Profiles API on http://127.0.0.1:6500")
    app.run(host="127.0.0.1", port=6500, debug=False)
