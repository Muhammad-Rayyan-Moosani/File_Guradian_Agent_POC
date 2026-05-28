import os
import sys
import shutil
from fnmatch import fnmatch
from pathlib import Path

from dotenv import load_dotenv
from supabase import create_client, Client

#  logging_setup from backend/
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from logging_setup import get_logger  # noqa: E402

log = get_logger("Intake")

load_dotenv(Path(__file__).resolve().parent.parent.parent / ".env")

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SERVICE_ROLE_KEY")
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)


def profiles_watching(folder: str) -> list[dict]:
    """Active profiles whose inbound folder is this folder."""
    return (
        supabase.table("validation_profiles")
        .select("*")
        .eq("active", True)
        .eq("inbound_folder", folder)
        .execute()
        .data
        or []
    )


def match_profile(folder: str, file_name: str) -> dict | None:
    """Find the active profile that owns this file.

    A profile owns the file when it watches the folder AND the file name
    matches its glob pattern (e.g. 'invoices_*.csv'). Returns the profile
    row, or None if nothing matches.
    """
    candidates = profiles_watching(folder)
    matches = [p for p in candidates if fnmatch(file_name, p["file_pattern"])]

    if len(matches) == 1:
        log.info("Matched profile '%s' for %s", matches[0]["name"], file_name)
        return matches[0]

    if len(matches) > 1:
        names = ", ".join(p["name"] for p in matches)
        log.warning("Multiple profiles match %s (%s) — using first", file_name, names)
        return matches[0]

    log.info("No profile matched %s in %s", file_name, folder)
    return None


def review_folder_for(folder: str) -> str | None:
    """Where to send files we can't classify. Prefer the unknown_routing of a
    profile already watching this folder; otherwise fall back to the global
    review folder in app_settings."""
    watching = profiles_watching(folder)
    if watching:
        return watching[0]["unknown_routing"]

    settings = supabase.table("app_settings").select("review_folder").eq("id", 1).execute().data
    return settings[0]["review_folder"] if settings else None


def move_file(file_path: str, dest_folder: str) -> str | None:
    """Move a file into dest_folder, keeping its name. Returns the new path."""
    if not dest_folder:
        log.warning("No destination folder set — leaving file in place: %s", file_path)
        return None
    os.makedirs(dest_folder, exist_ok=True)
    dest = os.path.join(dest_folder, os.path.basename(file_path))
    shutil.move(file_path, dest)
    log.info("Moved %s -> %s", file_path, dest)
    return dest


def create_run(file_info: dict, profile: dict | None, status: str) -> str:
    """Create the validation_runs row for this file (Pass 1).

    Only the things we know up front are filled here: file metadata, status,
    and which profile matched. Issue counts, result and destination are filled
    later once the file has actually been validated.
    """
    size_bytes = file_info.get("file_size") or 0
    row = {
        "file_name": os.path.basename(file_info["file_path"]),
        "file_size_kb": round(size_bytes / 1024),
        "received_at": file_info.get("received_at"),
        "status": status,
        "profile_id": profile["id"] if profile else None,
        "profile_name": profile["name"] if profile else "No matching profile",
    }
    run = supabase.table("validation_runs").insert(row).execute().data[0]
    log.info("Created run %s for %s (status=%s)", run["id"], row["file_name"], status)
    return run["id"]


def intake_file(file_info: dict) -> dict:
    """Classify a newly detected file and open its validation run.

    Returns {"run_id", "profile"}. If profile is None the file had no match
    and was routed to review — the pipeline should stop. Otherwise the run is
    'processing' and the caller continues to validation.
    """
    file_path = file_info["file_path"]
    folder = os.path.dirname(file_path)
    file_name = os.path.basename(file_path)

    profile = match_profile(folder, file_name)

    if profile:
        run_id = create_run(file_info, profile, "processing")
        return {"run_id": run_id, "profile": profile}

    # No match — open the run as 'review', move the file, record where it went.
    run_id = create_run(file_info, None, "review")
    dest = move_file(file_path, review_folder_for(folder))
    if dest:
        supabase.table("validation_runs").update({"destination_path": dest}).eq("id", run_id).execute()
    return {"run_id": run_id, "profile": None}
