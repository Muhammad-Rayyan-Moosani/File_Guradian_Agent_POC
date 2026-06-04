"""
Profiles API — CRUD for validation_profiles + its two child tables.
Run: python -m api.profiles
"""

import sys
from pathlib import Path

from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from logging_setup import get_logger  # noqa: E402
import db  # noqa: E402

log = get_logger("Profiles API")

app = Flask(__name__)
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

FRONTEND_DIST = Path(__file__).resolve().parent.parent.parent / "frontend" / "dist"


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
