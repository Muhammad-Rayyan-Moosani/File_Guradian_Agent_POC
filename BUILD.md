# Building the File Guardian Agent as a Windows app

This turns the project into **one `.exe`** that serves the dashboard and the API
together and stores everything in a local SQLite file — no cloud, no Node, and
no Python install needed on the server that runs it.

---

## TL;DR (on the Windows build machine)

```bat
git pull
backend\build_windows.bat
```

Result: `backend\dist\FileGuardianAgent.exe`. Put a `.env` next to it, double-click
it, and open `http://<server-name-or-ip>:6500` in a browser.

---

## What you need

**Only on the machine that BUILDS the exe:**

- **Python 3.13** — https://www.python.org/downloads/ (tick "Add Python to PATH")
- **Node.js** — https://nodejs.org/ (used once, to compile the React UI)

**On the server that RUNS the exe:** nothing. The exe is self-contained.

---

## How the build works (what `build_windows.bat` does)

1. **Compiles the web UI.** `npm run build` turns the React app into plain static
   files in `frontend/dist/`.
2. **Sets up Python.** Creates a virtual environment in `backend/venv` and installs
   `requirements.txt` plus **PyInstaller** (PyInstaller is a build-only tool, so it
   is not in `requirements.txt`).
3. **Bundles the exe.** PyInstaller follows `backend/file_guardian.spec`, which packs:
   - the Python app (entry point `backend/app.py`),
   - the SQL schema (`schema_sqlite.sql`),
   - the built web UI (`frontend/dist`),
   - and the libraries (Flask, waitress, pandas, watchdog, anthropic, …).

The output is `backend/dist/FileGuardianAgent.exe`.

---

## Files at runtime: bundled vs. next-to-the-exe

A one-file exe unpacks itself into a temporary folder each time it starts, and that
folder is deleted on exit. So the app is careful about where things live (see
`backend/paths.py`):

| Thing | Where it lives | Why |
|---|---|---|
| Web UI, SQL schema, libraries | **inside** the exe | read-only; never change |
| `.env` (SMTP, Anthropic key) | **next to** the exe | you edit it; copy from `.env.example` |
| `file_guardian.db` (the database) | **next to** the exe | must survive restarts |
| `logs/` folder | **next to** the exe | must survive restarts |

So a deployed folder ends up looking like:

```
FileGuardianAgent.exe
.env
file_guardian.db        (created on first run)
logs\                   (created on first run)
```

Move the exe wherever you like; the database and logs follow it. To put the
database somewhere specific instead, set `FG_DB_PATH` in the `.env`.

---

## Running it

1. Copy `.env.example` to `.env` next to the exe and fill in real values.
2. Start `FileGuardianAgent.exe` (double-click, or run it in a terminal to watch logs).
3. **First start takes ~30 seconds** while it unpacks and loads — this is normal for
   a one-file build. After that it's up.
4. Open `http://<server-name-or-ip>:6500`. Create profiles, point them at the inbound
   folders to watch, and drop files in.

(Step 4 of the plan — running it as an always-on Windows **service** with NSSM, so it
starts on boot and restarts on crash — is the next step after this.)

---

## Restricting access (admin login)

By default the dashboard is open to anyone who can reach it on the network. To
lock it behind a single admin sign-in, set these in the `.env` next to the exe:

```
ADMIN_USERNAME=admin
ADMIN_PASSWORD=choose-a-strong-password
FG_SECRET_KEY=any-long-random-string
```

- Set **both** `ADMIN_USERNAME` and `ADMIN_PASSWORD` to turn login on; leave them
  blank to keep it open. Restart the app after changing them.
- `FG_SECRET_KEY` signs the login cookie — set it so people stay logged in across
  restarts (any long random string).
- This only gates the **web dashboard**. Dropping files into the watched folders
  is unaffected — control who can do that with normal Windows folder permissions
  on the shared inbound folder.
- Note: this is app-level login for a trusted internal network, not Windows/AD
  authentication.

## Good to know

- **Slow first start (~30s).** The one-file build unpacks everything to a temp folder
  on each launch. For an always-on server that's fine. If startup speed matters, the
  alternative is a **one-folder** build (a folder with the exe + files next to it):
  it starts in a second or two but ships as a folder instead of a single file. Easy to
  switch — ask and I'll adjust `file_guardian.spec`.
- **Antivirus.** Fresh one-file exes occasionally get flagged by Windows Defender /
  corporate AV the first time. If that happens, allow-list the exe (or use the
  one-folder build, which is flagged less often).
- **The file-watcher on network shares.** The folder watcher (`watchdog`) behaves a bit
  differently on Windows network shares (UNC paths like `\\server\share\...`) than on a
  local disk. Test the watched folders on the real server; if a share isn't picked up,
  that's the place to look first.
- **Rebuilding.** After code changes: `git pull` then `backend\build_windows.bat` again.

---

## Building on a Mac (for testing only)

The path logic is identical on macOS, so you can smoke-test a build locally. It produces
a Mac binary (not a Windows `.exe`), so it's only for verifying behavior:

```bash
cd frontend && npm run build && cd ..
cd backend && ./venv/bin/pip install pyinstaller
./venv/bin/pyinstaller file_guardian.spec --noconfirm
./dist/FileGuardianAgent          # runs the same way; open http://127.0.0.1:6500
```
