import os
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

from dotenv import load_dotenv
from supabase import create_client, Client
from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

# Let us import logging_setup from backend/
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from logging_setup import get_logger  # noqa: E402

log = get_logger("Monitor")

# Load .env from project root
load_dotenv(Path(__file__).resolve().parent.parent.parent / ".env")

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SERVICE_ROLE_KEY")
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# Files we've seen so the Intake agent can pick them up
file_data: dict = {}


def get_active_inbound_paths() -> list[str]:
    """Return the unique inbound folders for every active profile."""
    rows = (
        supabase.table("validation_profiles")
        .select("inbound_folder")
        .eq("active", True)
        .execute()
        .data
    )
    paths = {r["inbound_folder"] for r in rows if r.get("inbound_folder")}
    return sorted(paths)


class FileHandler(FileSystemEventHandler):
    """Handles file events. Debounces per-path so two folders can fire
    at the same time without one event swallowing the other."""

    def __init__(self):
        self.last_seen: dict[str, datetime] = {}

    def on_modified(self, event):
        if event.is_directory:
            return

        path = event.src_path
        now = datetime.now()

        # Per-file debounce — same file twice within a second = ignore
        last = self.last_seen.get(path)
        if last and now - last < timedelta(seconds=1):
            return
        self.last_seen[path] = now

        try:
            size = os.path.getsize(path)
        except FileNotFoundError:
            log.warning("File gone before we could read it: %s", path)
            return

        file_data[path] = {
            "file_path": path,
            "file_type": os.path.splitext(path)[1].lower(),
            "received_at": now.isoformat(),
            "file_size": size,
        }
        log.info("New file: %s (%d bytes)", path, size)


def start_monitoring(paths: list[str]) -> None:
    """Watch every path with one Observer, block until Ctrl+C."""
    if not paths:
        log.warning("No paths to watch — no active profiles with an inbound folder.")
        return

    observer = Observer()
    handler = FileHandler()

    for p in paths:
        if not os.path.isdir(p):
            log.warning("Skipping missing folder: %s", p)
            continue
        observer.schedule(handler, path=p, recursive=False)
        log.info("Watching: %s", p)

    observer.start()
    log.info("Monitor running — Ctrl+C to stop.")

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        log.info("Stopping monitor…")
        observer.stop()
    observer.join()
    log.info("Monitor stopped.")


if __name__ == "__main__":
    paths = get_active_inbound_paths()
    log.info("Found %d folder(s) to watch", len(paths))
    start_monitoring(paths)
