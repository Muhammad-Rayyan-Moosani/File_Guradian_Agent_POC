"""
Intake agent — the first step after a file is detected.

It works out which validation profile (if any) owns a new file, opens a row
for it in the validation_runs table, and sends unmatched files to the review
folder. It does not validate the file's contents — that comes later.
"""

import os
import sys
import time
import shutil
from fnmatch import fnmatch
from pathlib import Path

# Make logging_setup and db (in backend/) importable.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from logging_setup import get_logger  # noqa: E402
import db  # noqa: E402

log = get_logger("Intake")


def with_retries(make_request, attempts=3, pause=1.0):
    """
    Run a database call, retrying a couple of times on a transient blip
    (for SQLite this is usually a brief 'database is locked' under load).
    Parameters: make_request (a function that performs and returns the call),
        attempts (int), pause (seconds between tries).
    Returns: whatever make_request returns (raises if every attempt fails).
    """
    last_error = None
    for attempt in range(attempts):
        try:
            return make_request()
        except Exception as error:
            last_error = error
            log.warning("Database call failed (try %d/%d): %s",
                        attempt + 1, attempts, error)
            time.sleep(pause)
    raise last_error


def same_folder(folder_a, folder_b):
    """
    Check whether two paths point at the same folder (handles symlinks).
    Parameters: folder_a (str), folder_b (str).
    Returns: bool.
    """
    return os.path.realpath(folder_a) == os.path.realpath(folder_b)


def active_profiles():
    """
    Get every active validation profile.
    Parameters: none.
    Returns: list of profile dicts.
    """
    return db.query_all("SELECT * FROM validation_profiles WHERE active = 1")


def profiles_watching(folder):
    """
    Get active profiles whose inbound folder is the same as this folder.
    Parameters: folder (str) — the folder path to look up.
    Returns: list of profile dicts (empty list if none).
    """
    watching = []
    for profile in active_profiles():
        inbound = profile.get("inbound_folder")
        if inbound and same_folder(inbound, folder):
            watching.append(profile)
    return watching


def match_profile(folder, file_name):
    """
    Find the one active profile that owns this file (folder + name pattern).
    Parameters: folder (str), file_name (str).
    Returns: a profile dict, or None if nothing matches.
    """
    candidates = profiles_watching(folder)

    # Keep only the profiles whose pattern matches the file name.
    matches = []
    for profile in candidates:
        if fnmatch(file_name, profile["file_pattern"]):
            matches.append(profile)

    if len(matches) == 1:
        log.info("Matched profile '%s' for %s", matches[0]["name"], file_name)
        return matches[0]

    if len(matches) > 1:
        # Several profiles share this folder and all match this file name. Pick
        # the most specific pattern (e.g. 'payroll_*.csv' beats a broad '*.csv'),
        # so one folder can serve many profiles without files going to the wrong
        # one just because of the order the profiles were created.
        names = []
        for profile in matches:
            names.append(profile["name"])
        best = most_specific_profile(matches)
        log.info("Several profiles match %s (%s) — using the most specific: '%s'",
                 file_name, ", ".join(names), best["name"])
        return best

    log.info("No profile matched %s in %s", file_name, folder)
    return None


def pattern_specificity(pattern):
    """
    Score how specific a filename pattern is (higher means more specific).
    Literal characters add to the score; wildcards (* and ?) take away from it,
    so 'payroll_*.csv' scores higher than a catch-all '*.csv'.
    Parameters: pattern (str).
    Returns: int.
    """
    literal_count = 0
    for character in pattern:
        if character not in "*?":
            literal_count += 1
    wildcard_count = pattern.count("*") + pattern.count("?")
    return literal_count - wildcard_count


def most_specific_profile(matches):
    """
    From several matching profiles, return the one with the most specific pattern.
    On a tie, the first one (creation order) is kept.
    Parameters: matches (list of profile dicts).
    Returns: a profile dict.
    """
    best = matches[0]
    best_score = pattern_specificity(best["file_pattern"])
    for profile in matches[1:]:
        score = pattern_specificity(profile["file_pattern"])
        if score > best_score:
            best = profile
            best_score = score
    return best


def review_folder_for(folder):
    """
    Decide where to put a file we could not classify.
    Parameters: folder (str) — the inbound folder the file arrived in.
    Returns: a folder path (str), or None if none is configured.
    """
    # If some profile watches this folder, use its review folder.
    watching = profiles_watching(folder)
    if watching:
        return watching[0]["unknown_routing"]

    # Otherwise fall back to the global review folder in settings.
    settings = db.query_one("SELECT review_folder FROM app_settings WHERE id = 1")
    if settings:
        return settings["review_folder"]
    return None


def unique_destination(dest_folder, file_name):
    """
    Pick a path in dest_folder that does not already exist.
    If 'invoice.csv' is taken we try 'invoice (1).csv', 'invoice (2).csv', …
    Parameters: dest_folder (str), file_name (str).
    Returns: a free path (str).
    """
    candidate = os.path.join(dest_folder, file_name)
    if not os.path.exists(candidate):
        return candidate

    base, extension = os.path.splitext(file_name)
    counter = 1
    while True:
        candidate = os.path.join(dest_folder, f"{base} ({counter}){extension}")
        if not os.path.exists(candidate):
            return candidate
        counter += 1


def move_file(file_path, dest_folder):
    """
    Move a file into a destination folder without ever overwriting an existing
    file (a name clash gets a numbered suffix).
    Parameters: file_path (str), dest_folder (str).
    Returns: the new path (str), or None if no folder was given or the file is gone.
    """
    if not dest_folder:
        log.warning("No destination folder set — leaving file in place: %s", file_path)
        return None

    if not os.path.exists(file_path):
        log.warning("File vanished before it could be moved: %s", file_path)
        return None

    os.makedirs(dest_folder, exist_ok=True)
    dest = unique_destination(dest_folder, os.path.basename(file_path))
    shutil.move(file_path, dest)
    log.info("Moved %s -> %s", file_path, dest)
    return dest


def create_run(file_info, profile, status):
    """
    Open a validation_runs row for a file as soon as it is seen.
    Parameters: file_info (dict), profile (dict or None), status (str).
    Returns: the new run id (str).
    """
    size_bytes = file_info.get("file_size") or 0

    if profile:
        profile_id = profile["id"]
        profile_name = profile["name"]
    else:
        profile_id = None
        profile_name = "No matching profile"

    row = {
        "file_name": os.path.basename(file_info["file_path"]),
        "file_size_kb": round(size_bytes / 1024),
        "received_at": file_info.get("received_at"),
        "status": status,
        "profile_id": profile_id,
        "profile_name": profile_name,
    }
    def do_insert():
        return db.insert("validation_runs", row)

    run = with_retries(do_insert)
    log.info("Created run %s for %s (status=%s)", run["id"], row["file_name"], status)
    return run["id"]


def intake_file(file_info):
    """
    Classify a new file and open its validation run.
    Parameters: file_info (dict) with at least "file_path".
    Returns: dict {"run_id": str, "profile": dict or None}.
    """
    file_path = file_info["file_path"]
    folder = os.path.dirname(file_path)
    file_name = os.path.basename(file_path)

    profile = match_profile(folder, file_name)

    # Matched a profile — open the run and let the pipeline continue.
    if profile:
        run_id = create_run(file_info, profile, "processing")
        return {"run_id": run_id, "profile": profile}

    # No match — record it as 'review' and move the file aside.
    run_id = create_run(file_info, None, "review")
    dest = move_file(file_path, review_folder_for(folder))
    if dest:
        db.update("validation_runs", run_id, {"destination_path": dest})
    return {"run_id": run_id, "profile": None}
