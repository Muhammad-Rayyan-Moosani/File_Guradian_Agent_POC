"""
File Guardian — centralized logging.

Every process in the backend (Flask API, Monitor Agent, future Intake/Test
agents, etc.) should call:

    from logging_setup import get_logger
    log = get_logger("ComponentName")
    log.info("something happened")

Behaviour:
- Writes BOTH to stdout (so you see it live in the terminal) and to
  `backend/logs/file_guardian.log`.
- On the FIRST call within a process, the log file is wiped so every fresh
  start gives you a clean slate to debug from.
- Each line includes timestamp, log level, component name, and message.
- The file is also rotated at 5 MB just in case a process runs long.

Anything left over from the old `log.txt` / `logs.txt` files is replaced by
this single file.
"""

from __future__ import annotations

import sys
import logging
import os
from logging.handlers import RotatingFileHandler
from pathlib import Path

# Make sibling modules (paths) importable even if we are imported first.
sys.path.insert(0, str(Path(__file__).resolve().parent))
import paths  # noqa: E402

# ---------------------------------------------------------------------------
# Paths — the log folder sits next to the .exe when frozen, else in backend/.
# ---------------------------------------------------------------------------
LOG_DIR = paths.LOGS_DIR
LOG_FILE = LOG_DIR / "file_guardian.log"

LOG_DIR.mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------------------
# Fresh-slate behaviour: wipe the log file on the first import per process.
# Use an env-guard so child processes (e.g. Flask reloader) don't re-wipe.
# ---------------------------------------------------------------------------
_WIPE_GUARD = "_FILEGUARDIAN_LOG_WIPED"

def _wipe_log_once() -> None:
    if os.environ.get(_WIPE_GUARD):
        return
    # Don't wipe inside the Flask debug reloader child either.
    if os.environ.get("WERKZEUG_RUN_MAIN"):
        return
    try:
        with open(LOG_FILE, "w") as f:
            f.write("")  # truncate
    except FileNotFoundError:
        pass
    os.environ[_WIPE_GUARD] = "1"


_wipe_log_once()


# ---------------------------------------------------------------------------
# Configure the root logger once.
# ---------------------------------------------------------------------------
_FORMAT = "[%(asctime)s] %(levelname)-5s %(name)-18s | %(message)s"
_DATEFMT = "%H:%M:%S"

_root = logging.getLogger("file_guardian")
if not _root.handlers:  # idempotent — only configure once per process
    _root.setLevel(logging.DEBUG)

    fmt = logging.Formatter(_FORMAT, datefmt=_DATEFMT)

    # File handler with rotation (5 MB, keep 3 backups)
    fh = RotatingFileHandler(LOG_FILE, maxBytes=5 * 1024 * 1024, backupCount=3)
    fh.setFormatter(fmt)
    fh.setLevel(logging.DEBUG)
    _root.addHandler(fh)

    # Stdout handler
    sh = logging.StreamHandler()
    sh.setFormatter(fmt)
    sh.setLevel(logging.INFO)
    _root.addHandler(sh)

    _root.propagate = False  # don't double-log through Python's root


def get_logger(name: str) -> logging.Logger:
    """Get a namespaced child logger. Use a short component name like
    'Monitor', 'Profiles API', 'Intake'. All children share the same
    formatting and handlers."""
    return _root.getChild(name)


# ---------------------------------------------------------------------------
# Friendly banner so you can tell when a fresh process boots in the log.
# ---------------------------------------------------------------------------
_boot = get_logger("Boot")
_boot.info("─" * 60)
_boot.info("File Guardian backend logger initialised → %s", LOG_FILE)
_boot.info("─" * 60)
