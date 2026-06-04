"""
File Guardian — where files live, whether running from source or as a bundled .exe.

PyInstaller packs the whole app into one .exe that unpacks itself into a NEW
temporary folder every time it launches. That folder is deleted when the app
exits. So anything found through `__file__` ends up inside that throwaway
folder — which would mean the database gets wiped on every restart and the
bundled files look like they moved.

To avoid that, we split paths into two kinds:

  * Bundled, read-only resources — the SQL schema and the built web UI. These
    are packed inside the .exe and read from the unpack folder (sys._MEIPASS).
  * Writable data the app must keep — the SQLite database, the logs, and the
    .env config file. These live NEXT TO the .exe so they survive restarts and
    so IT staff can open/edit them.

When running normally from source (`python app.py`), every path resolves to the
exact same place it always has, so nothing changes for day-to-day development.
"""

import os
import sys
from pathlib import Path


def is_frozen():
    """
    Tell whether the app is running inside a PyInstaller-built executable.
    Parameters: none.
    Returns: bool (True when frozen into an .exe, False when run from source).
    """
    return getattr(sys, "frozen", False)


if is_frozen():
    # Read-only files that were unpacked from inside the .exe.
    BUNDLE_DIR = Path(sys._MEIPASS)
    # Writable files live in the same folder as the .exe itself.
    APP_DIR = Path(sys.executable).resolve().parent

    SCHEMA_PATH = BUNDLE_DIR / "schema_sqlite.sql"
    FRONTEND_DIST = BUNDLE_DIR / "frontend_dist"
    ENV_FILE = APP_DIR / ".env"
    LOGS_DIR = APP_DIR / "logs"
    DEFAULT_DB_PATH = APP_DIR / "file_guardian.db"
else:
    BACKEND_DIR = Path(__file__).resolve().parent
    PROJECT_ROOT = BACKEND_DIR.parent

    BUNDLE_DIR = BACKEND_DIR
    APP_DIR = BACKEND_DIR

    SCHEMA_PATH = BACKEND_DIR / "schema_sqlite.sql"
    FRONTEND_DIST = PROJECT_ROOT / "frontend" / "dist"
    ENV_FILE = PROJECT_ROOT / ".env"
    LOGS_DIR = BACKEND_DIR / "logs"
    DEFAULT_DB_PATH = BACKEND_DIR / "file_guardian.db"

# The database file location. FG_DB_PATH overrides it everywhere if set.
DB_PATH = os.getenv("FG_DB_PATH") or str(DEFAULT_DB_PATH)
