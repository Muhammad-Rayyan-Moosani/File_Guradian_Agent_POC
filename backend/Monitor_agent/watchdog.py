"""
Monitor agent — watches the inbound folders and feeds files to the pipeline.

How it is built to handle a busy, high-volume office:

  * A pool of worker threads validates files in parallel, so one huge file can
    never block the others behind it.
  * The folder list is refreshed on a timer, so creating or editing a profile
    is picked up automatically — no restart needed.
  * A file is only handed to the pipeline once it has stopped growing, so a
    file that is still being copied in is never read half-written.
  * On startup, any run left stuck in "processing" by a previous crash is
    tidied up so the dashboard never shows a run that will never finish.
"""

import os
import sys
import time
import queue
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path

from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

# Make logging_setup, db and the pipeline (in backend/) importable.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from logging_setup import get_logger  # noqa: E402
import db  # noqa: E402
from pipeline import run_pipeline  # noqa: E402

log = get_logger("Monitor")


def read_int_env(name, default):
    """
    Read a whole-number setting from the environment, or use a default.
    Parameters: name (str), default (int).
    Returns: int.
    """
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return int(raw)
    except ValueError:
        return default


# How many files to validate at the same time, and how often to re-check which
# folders to watch (seconds).
WORKER_COUNT = read_int_env("FG_WORKERS", 4)
REFRESH_SECONDS = read_int_env("FG_REFRESH_SECONDS", 15)

# File name endings that mean "still being written" — we skip these.
TEMP_SUFFIXES = (".tmp", ".part", ".partial", ".crdownload", ".filepart")


def get_active_inbound_paths():
    """
    Read the inbound folder of every active profile.
    Parameters: none.
    Returns: sorted list of unique folder paths (str).
    """
    rows = db.query_all(
        "SELECT inbound_folder FROM validation_profiles WHERE active = 1")

    folders = set()
    for row in rows:
        if row.get("inbound_folder"):
            folders.add(row["inbound_folder"])
    return sorted(folders)


def reconcile_stuck_runs():
    """
    Mark any run left in "processing" by a previous crash as failed.
    Parameters: none.
    Returns: None.
    """
    try:
        stuck = db.query_all(
            "SELECT id FROM validation_runs WHERE status = 'processing'")
    except Exception:
        log.exception("Could not check for stuck runs")
        return

    if not stuck:
        return

    note = '{"summary": "This run was interrupted before it finished (the app ' \
           'restarted). Re-drop the file to validate it again.", "impact": "", "action": ""}'
    for row in stuck:
        db.update("validation_runs", row["id"], {
            "status": "failed",
            "ai_summary": note,
            "completed_at": datetime.now(timezone.utc).isoformat(),
        })
    log.warning("Tidied up %d run(s) left stuck in 'processing'", len(stuck))


def is_temp_file(path):
    """
    Decide whether a path looks like a temporary / half-written file to skip.
    Parameters: path (str).
    Returns: bool.
    """
    name = os.path.basename(path)
    if name.startswith(".") or name.startswith("~$"):
        return True
    lowered = name.lower()
    for suffix in TEMP_SUFFIXES:
        if lowered.endswith(suffix):
            return True
    return False


def wait_until_stable(path, interval=1.0, stable_checks=3, max_wait=3600):
    """
    Wait until a file has stopped growing (so a big copy can finish first).
    We keep waiting as long as the size is still changing, up to max_wait.
    Parameters: path (str), interval (secs), stable_checks (int), max_wait (secs).
    Returns: bool — True once it settled, False if it vanished or stalled.
    """
    last_size = -1
    stable_count = 0
    waited = 0.0

    while waited < max_wait:
        try:
            size = os.path.getsize(path)
        except FileNotFoundError:
            return False

        if size == last_size:
            stable_count += 1
            if stable_count >= stable_checks:
                return True
        else:
            stable_count = 0
            last_size = size

        time.sleep(interval)
        waited += interval

    return False


class WorkQueue:
    """A queue of file paths plus a set that prevents processing one twice."""

    def __init__(self):
        """Create the queue and the in-flight tracking set."""
        self.queue = queue.Queue()
        self.inflight = set()
        self.lock = threading.Lock()

    def submit(self, path):
        """
        Add a file path to the queue unless it is already queued/processing.
        Parameters: path (str).
        Returns: None.
        """
        with self.lock:
            if path in self.inflight:
                return
            self.inflight.add(path)
        self.queue.put(path)

    def done(self, path):
        """
        Mark a file path as finished so the same path can be handled again later.
        Parameters: path (str).
        Returns: None.
        """
        with self.lock:
            self.inflight.discard(path)


def process_one(path):
    """
    Wait for a file to settle, then run it through the whole pipeline.
    Parameters: path (str).
    Returns: None.
    """
    if not wait_until_stable(path):
        log.warning("File never settled (still writing or gone): %s", path)
        return

    try:
        size = os.path.getsize(path)
    except FileNotFoundError:
        log.warning("File gone before we could read it: %s", path)
        return

    file_info = {
        "file_path": path,
        "file_type": os.path.splitext(path)[1].lower(),
        "received_at": datetime.now().isoformat(),
        "file_size": size,
    }
    log.info("New file: %s (%d bytes)", path, size)

    try:
        run_pipeline(file_info)
    except Exception:
        log.exception("Pipeline failed for %s", path)


def worker_loop(work):
    """
    Pull file paths off the queue forever and process them one at a time.
    Parameters: work (WorkQueue).
    Returns: None (runs until the process stops).
    """
    while True:
        path = work.queue.get()
        try:
            process_one(path)
        finally:
            work.done(path)
            work.queue.task_done()


class FileHandler(FileSystemEventHandler):
    """Reacts to file events by adding the file to the work queue."""

    def __init__(self, work):
        """
        Set up the handler.
        Parameters: work (WorkQueue).
        Returns: None.
        """
        self.work = work

    def on_created(self, event):
        """Handle a brand-new file appearing in a watched folder."""
        self.handle_file(event)

    def on_modified(self, event):
        """Handle a file being written to in a watched folder."""
        self.handle_file(event)

    def on_moved(self, event):
        """Handle a file being renamed into a watched folder (common for copies)."""
        if not event.is_directory:
            self.queue_path(event.dest_path)

    def handle_file(self, event):
        """
        Queue a normal file event (ignoring folders and temp files).
        Parameters: event (watchdog event).
        Returns: None.
        """
        if event.is_directory:
            return
        self.queue_path(event.src_path)

    def queue_path(self, path):
        """
        Add a path to the work queue unless it is a temp/partial file.
        Parameters: path (str).
        Returns: None.
        """
        if is_temp_file(path):
            return
        self.work.submit(path)


def schedule_watches(observer, handler, watches, wanted):
    """
    Make the observer watch exactly the folders in `wanted` (add new, drop gone).
    Parameters: observer (Observer), handler (FileHandler),
        watches (dict folder -> watch handle), wanted (list of folder paths).
    Returns: None (updates `watches` in place).
    """
    wanted_set = set(wanted)

    # Stop watching folders that are no longer wanted.
    for folder in list(watches.keys()):
        if folder not in wanted_set:
            observer.unschedule(watches[folder])
            del watches[folder]
            log.info("Stopped watching: %s", folder)

    # Start watching new folders (only if they exist on disk right now).
    for folder in wanted:
        if folder in watches:
            continue
        if not os.path.isdir(folder):
            log.warning("Waiting for missing folder to appear: %s", folder)
            continue
        watches[folder] = observer.schedule(handler, path=folder, recursive=False)
        log.info("Watching: %s", folder)


def start_monitoring(paths):
    """
    Start the workers and the observer, then keep the watch list fresh.
    Parameters: paths (list of folder paths to start with).
    Returns: None (runs until Ctrl+C).
    """
    reconcile_stuck_runs()

    work = WorkQueue()
    for _ in range(WORKER_COUNT):
        thread = threading.Thread(target=worker_loop, args=(work,), daemon=True)
        thread.start()
    log.info("Started %d validation worker(s)", WORKER_COUNT)

    observer = Observer()
    handler = FileHandler(work)
    watches = {}
    schedule_watches(observer, handler, watches, paths)
    observer.start()
    log.info("Monitor running — Ctrl+C to stop. Re-checking folders every %ds.",
             REFRESH_SECONDS)

    try:
        while True:
            time.sleep(REFRESH_SECONDS)
            # Re-read the active profiles so new/edited ones are picked up,
            # and folders that only just appeared on disk start being watched.
            try:
                schedule_watches(observer, handler, watches, get_active_inbound_paths())
            except Exception:
                log.exception("Could not refresh the watch list")
    except KeyboardInterrupt:
        log.info("Stopping monitor…")
        observer.stop()

    observer.join()
    log.info("Monitor stopped.")


if __name__ == "__main__":
    folders = get_active_inbound_paths()
    log.info("Found %d folder(s) to watch", len(folders))
    start_monitoring(folders)
