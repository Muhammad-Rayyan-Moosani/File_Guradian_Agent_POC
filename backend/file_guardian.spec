# PyInstaller spec for the File Guardian Agent — builds one self-contained
# executable that serves the web UI and the API together.
#
# Build (run from the backend folder, with the venv active):
#     pyinstaller file_guardian.spec
# The result is dist/FileGuardianAgent (FileGuardianAgent.exe on Windows).
#
# What gets bundled INTO the exe (read-only): the SQL schema and the built web
# UI (frontend/dist). What lives NEXT TO the exe at runtime (writable): the
# .env file, the SQLite database, and the logs folder. See backend/paths.py.

import os
from PyInstaller.utils.hooks import collect_all

# SPECPATH is the folder holding this .spec file (the backend folder).
HERE = SPECPATH
PROJECT_ROOT = os.path.dirname(HERE)

# Read-only resources to pack inside the exe: (source on disk, folder in bundle).
datas = [
    (os.path.join(HERE, "schema_sqlite.sql"), "."),
    (os.path.join(PROJECT_ROOT, "frontend", "dist"), "frontend_dist"),
]
binaries = []

# The agent folders have no __init__.py (namespace packages), so list their
# modules explicitly to be sure PyInstaller includes them.
hiddenimports = [
    "waitress",
    "paths",
    "db",
    "pipeline",
    "logging_setup",
    "api.profiles",
    "api.runs",
    "api.settings",
    "Intake_agent.initial_check",
    "Test_agent.validator",
    "Explanation_agent.explain",
    "Notification_agent.notify",
    "Monitor_agent.watchdog",
]

# anthropic and watchdog ship submodules/metadata that the analyzer can miss
# (watchdog picks its OS-specific file-watcher at runtime). Collect them whole.
# collect_all runs on the build machine, so the Windows build picks up the
# Windows file-watcher automatically.
for package_name in ("anthropic", "watchdog"):
    package_datas, package_binaries, package_hidden = collect_all(package_name)
    datas += package_datas
    binaries += package_binaries
    hiddenimports += package_hidden

a = Analysis(
    [os.path.join(HERE, "app.py")],
    pathex=[HERE],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="FileGuardianAgent",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,                 # keep a console so logs are visible
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
