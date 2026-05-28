"""
Profiles API — CRUD for validation_profiles + its two child tables.
Run: python -m api.profiles
"""

import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from flask import Flask, jsonify, request
from flask_cors import CORS
from supabase import Client, create_client

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from logging_setup import get_logger  # noqa: E402

log = get_logger("Profiles API")

# Load .env from project root
load_dotenv(Path(__file__).resolve().parent.parent.parent / ".env")

SUPABASE_URL = os.getenv("SUPABASE_URL")
SERVICE_ROLE_KEY = os.getenv("SERVICE_ROLE_KEY")
if not SUPABASE_URL or not SERVICE_ROLE_KEY:
    raise RuntimeError("Missing SUPABASE_URL or SERVICE_ROLE_KEY in .env")

supabase: Client = create_client(SUPABASE_URL, SERVICE_ROLE_KEY)

app = Flask(__name__)
CORS(app)

# Mount the read-only runs endpoints (/api/runs, /api/runs/<id>)
from api.runs import runs_bp  # noqa: E402
app.register_blueprint(runs_bp)


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
        supabase.table("profile_columns").insert(col_rows).execute()
    cross_rows = to_db_cross_rules(profile_id, cross_rules)
    if cross_rows:
        supabase.table("profile_cross_column_rules").insert(cross_rows).execute()


def load_profile(profile_id: str) -> dict | None:
    """Load a profile row + its children and shape them for the frontend."""
    rows = (
        supabase.table("validation_profiles")
        .select("*").eq("id", profile_id).limit(1).execute().data
    )
    if not rows:
        return None
    p = rows[0]

    cols = (
        supabase.table("profile_columns")
        .select("*").eq("profile_id", profile_id)
        .order("column_order").execute().data or []
    )
    cross = (
        supabase.table("profile_cross_column_rules")
        .select("*").eq("profile_id", profile_id).execute().data or []
    )

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
    return jsonify({"ok": True, "supabase_url": SUPABASE_URL})


@app.get("/api/profiles")
def list_profiles():
    log.info("GET /api/profiles")
    rows = (
        supabase.table("validation_profiles")
        .select("id").order("created_at", desc=True).execute().data
    )
    profiles = [load_profile(r["id"]) for r in rows]
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
        inserted = supabase.table("validation_profiles").insert(to_db_profile(body)).execute()
        profile_id = inserted.data[0]["id"]
    except Exception as e:
        log.exception("Insert failed")
        return jsonify({"error": "Failed to insert profile", "detail": str(e)}), 500

    try:
        insert_children(profile_id, body["columns"], body.get("crossColumnRules") or [])
    except Exception as e:
        # Cascade delete cleans up any half-saved children
        supabase.table("validation_profiles").delete().eq("id", profile_id).execute()
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

    existing = (
        supabase.table("validation_profiles")
        .select("id").eq("id", profile_id).limit(1).execute().data
    )
    if not existing:
        return jsonify({"error": "Profile not found"}), 404

    # Snapshot children so we can restore on failure
    prev_cols = supabase.table("profile_columns").select("*").eq("profile_id", profile_id).execute().data or []
    prev_cross = supabase.table("profile_cross_column_rules").select("*").eq("profile_id", profile_id).execute().data or []

    try:
        supabase.table("validation_profiles").update(to_db_profile(body)).eq("id", profile_id).execute()
        supabase.table("profile_columns").delete().eq("profile_id", profile_id).execute()
        supabase.table("profile_cross_column_rules").delete().eq("profile_id", profile_id).execute()
        insert_children(profile_id, body["columns"], body.get("crossColumnRules") or [])
    except Exception as e:
        log.exception("Update failed, restoring previous children")
        supabase.table("profile_columns").delete().eq("profile_id", profile_id).execute()
        supabase.table("profile_cross_column_rules").delete().eq("profile_id", profile_id).execute()
        if prev_cols:
            supabase.table("profile_columns").insert(prev_cols).execute()
        if prev_cross:
            supabase.table("profile_cross_column_rules").insert(prev_cross).execute()
        return jsonify({"error": "Failed to update profile", "detail": str(e)}), 500

    return jsonify(load_profile(profile_id))


@app.delete("/api/profiles/<profile_id>")
def delete_profile(profile_id):
    log.info("DELETE /api/profiles/%s", profile_id)
    existing = (
        supabase.table("validation_profiles")
        .select("id").eq("id", profile_id).limit(1).execute().data
    )
    if not existing:
        return jsonify({"error": "Profile not found"}), 404
    supabase.table("validation_profiles").delete().eq("id", profile_id).execute()
    return jsonify({"id": profile_id, "ok": True, "deleted": True})


if __name__ == "__main__":
    log.info("Starting Profiles API on http://127.0.0.1:5000")
    app.run(host="127.0.0.1", port=5000, debug=True)
