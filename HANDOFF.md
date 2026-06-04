# File Guardian Agent — Project Handoff

> **Purpose of this document:** a complete, self-contained context dump so a fresh Claude Code session (new account, no prior memory of this project) can pick up exactly where the last one left off, with no loss of context. Read this top to bottom before starting work.

---

## 0. TL;DR — where things stand right now

- **What this is:** "File Guardian Agent" — a POC built for an Xorbix internship. It watches inbound folders, validates dropped CSV files against per-column rule profiles, explains failures in plain English (AI), routes files to good/quarantine/review folders, and emails the right people on failure. Has a polished React dashboard.
- **Current state:** Fully working end-to-end (web app). Frontend (React/Vite) + backend (Flask/Python) + cloud database (Supabase Postgres). Live Gmail email alerts work. Dark mode added. Recently had a big performance/robustness overhaul.
- **THE NEXT TASK (the active goal):** Convert this into a **self-contained local Windows application for internal server use**. Plain English: make it run *by itself* on Xorbix's internal Windows server with **no cloud dependency**. **Keep Python — do NOT rewrite to .NET** (that was a misread of meeting notes; .NET was for a different project). The core change is **replacing Supabase (cloud DB) with a local SQLite database**, then bundling/serving it as one Windows app. See **Section 7** for the full plan.
- **Repo:** local git repo on `master`. **Lots of uncommitted work** (the entire current feature set is unstaged — see Section 6). **Do NOT commit unless the user explicitly asks.**

---

## 1. Who the user is & how to work with them

- **User:** Rayyan Moosani, software engineering intern at **Xorbix Technologies**. Email: mrayyanm411@gmail.com. Works on a **Mac** (darwin). New to Windows/.NET — explain Windows concepts in beginner-friendly terms.
- **Communication:** wants clear, honest, practical guidance. Will push back when something seems off — and is often right. Don't over-engineer. Don't bluff; if unsure, say so.
- **Standing preferences / constraints (IMPORTANT — these persist):**
  1. **Never `git commit` or push unless explicitly told to.** The repo has lots of uncommitted changes intentionally.
  2. **Code style:** beginner-readable. A three-line docstring before each function (what it does / parameters / returns). **Avoid lambdas and dense one-liner comprehensions** — prefer plain loops. "Shouldn't look like it was completely done by AI." *Exception:* `backend/Test_agent/validator.py` is deliberately vectorized (pandas) for performance and is necessarily more advanced — that's intentional and was explained to the user.
  3. **Notifications** were kept "log-only / out of the way" for a long time; they are **now live** (real Gmail SMTP). Keep the failure-safe wrapper so a mail error can never crash the pipeline.
  4. **Notion logging protocol:** only write to Notion when the user explicitly says **"log this"** (Xorbix work → the File Guardian page) or **"log for storyverse"** (a different project). Draft the entry and get an OK before the *first* write each session, then append without re-asking. Keep the user's voice, invent nothing, use "—" for empty fields. The Xorbix log page is **"🖥️ File Guardian Agent — Xorbix"**, Notion page id `36d54862-d8cb-81d1-862b-efc98f1e1485`. Newest entries go at the bottom; entries follow a `## YYYY-MM-DD — title` + What I did / Tools / Outcome / Blockers / Next steps format.

---

## 2. What the system does (functional overview)

The "agentic" pipeline, per file dropped into a watched folder:

1. **Monitor** — detects a new file in an active profile's inbound folder.
2. **Intake** — matches the file to a profile by **folder + filename glob** (e.g. `invoices_*.csv`); opens a `validation_runs` row (status `processing`). Unmatched files → `review` folder.
3. **Planning** — loads that profile's column rules + cross-column rules.
4. **Test** — validates the CSV (required, unique, type, min/max, regex, allowed-values, plus two-column cross rules like `DueDate >= InvoiceDate`).
5. **Route** — any error-severity issue quarantines the whole file (→ failure folder); otherwise → good folder.
6. **Explanation** — AI (Claude Haiku) or a deterministic template writes `{summary, impact, action}`. (LLM only runs on failures.)
7. **Notification** — emails recipients on failure (HTML email with the AI summary + issues table). Falls back to log-only if SMTP isn't configured.
8. **Audit** — writes issues + a full agent-event timeline to the DB. Dashboard shows it all live.

---

## 3. Tech stack & architecture (current = web app)

```
React + Vite + TS + Tailwind (port 6200)
        │  HTTP (fetch)
        ▼
Flask API + file Monitor  ── one process: backend/app.py (port 6500, served by waitress)
        │
        ▼
Supabase (cloud Postgres)         ◄── THIS is what becomes local SQLite next
```

- **Frontend:** React 18 + Vite + TypeScript + TailwindCSS v3 + react-router-dom + lucide-react + clsx. Dev server **port 6200** (`vite.config.ts`, strictPort). Calls the API at `http://127.0.0.1:6500` (`src/lib/api.ts`).
- **Backend:** Flask + flask-cors + **waitress** (production server) + supabase-py + python-dotenv + watchdog + pandas + numpy + anthropic. **One entry point: `backend/app.py`** runs the Monitor in a daemon thread and the API on **port 6500**.
- **Database:** Supabase / Postgres. Schema in `backend/schema.sql`.
- **AI:** Anthropic Claude, model `claude-haiku-4-5`, with prompt caching. Optional — template fallback works without a key.
- **Email:** Gmail SMTP via `smtplib` (live).

**Why ports 6200/6500:** the user originally asked for frontend 6000 / backend 6500, but **port 6000 is blocked by Chrome/Firefox (`ERR_UNSAFE_PORT`)**, so the frontend was moved to **6200**. Don't use 6000.

---

## 4. Repository map (every source file, what it does)

**Backend (`backend/`):**
- `app.py` — single entry point. Starts Monitor (daemon thread) + API (waitress on 6500, falls back to Flask dev server if waitress missing). `python app.py` runs everything.
- `api/profiles.py` — the Flask `app`; registers `runs_bp` + `settings_bp`; CORS locked to localhost:6200; profiles CRUD. **`load_all_profiles()` does the whole list in 3 bulk queries** (was an N+1 that made the page slow).
- `api/runs.py` — `runs_bp`: `GET /api/runs` (list), `GET /api/runs/<id>` (with issues+events), `DELETE /api/runs/<id>` (deletes the physical file at `destination_path` **and** the DB row; children cascade).
- `api/settings.py` — `settings_bp`: `GET`/`PUT /api/settings` (single row id=1).
- `Monitor_agent/watchdog.py` — the Monitor. **Worker-thread pool** (parallel file processing), **periodic re-scan of active profiles' inbound folders** (so creating/editing a profile needs **no restart**), **crash recovery** (`reconcile_stuck_runs` tidies runs stuck in `processing` on startup), **adaptive file-stability wait** (waits until the file stops growing), temp-file skipping, in-flight dedup. Tunables via env (Section 5).
- `Intake_agent/initial_check.py` — `match_profile` (folder + `fnmatch`), `create_run`, `move_file` (**collision-safe**, never overwrites), `same_folder` (macOS `realpath` to handle `/private` vs `/var` symlinks), `with_retries` (transient-DB-error retry helper). Holds the shared `supabase` client.
- `Test_agent/validator.py` — **streaming + vectorized** validation engine. `validate_file(path, columns, cross_rules, allow_extra, chunk_rows)` reads the CSV in chunks (flat memory for huge files) and checks each constraint with pandas boolean masks. Returns `{issues (capped sample), error_count, warning_count, total_rows, headers, notes}`. ~442k rows/sec; built for 100s of GB. (This file is intentionally the one "advanced" file.)
- `pipeline.py` — orchestrator. `run_pipeline(file_info)` ties Intake → validate → route → explain → notify → finalize. `complete_run(...)` does the move/explain/notify/write/finalize. File-size guard (`FG_MAX_FILE_MB`). Routes on true error count.
- `Explanation_agent/explain.py` — `explain(meta, issues)` → `{summary, impact, action}`. Template path always works; Claude path runs **only on failures** and only if `ANTHROPIC_API_KEY` is set; falls back to template on any error. Uses true counts from `meta`.
- `Notification_agent/notify.py` — `notify_failure(...)`. Sends a **multipart text + HTML email** (HTML has the AI summary/impact/action cards + an example-issues table). Real Gmail SMTP if configured, else log-only. `DASHBOARD_URL` env controls the email's dashboard link (defaults `http://localhost:6200`).
- `logging_setup.py` — central rotating logger → `backend/logs/file_guardian.log` (+ stdout).
- `schema.sql` — full Postgres schema (drop+create+seed). Tables below.
- `test_smtp.py` — `python backend/test_smtp.py you@example.com` sends one test email to verify SMTP.
- `requirements.txt` — flask, flask-cors, waitress, supabase, python-dotenv, watchdog, pandas, numpy, anthropic.
- `venv/` — Python 3.13 virtualenv (gitignored). Use `backend/venv/bin/python`.

**Frontend (`frontend/src/`):**
- `main.tsx`, `App.tsx` (routes), `App.css`.
- `components/Layout.tsx` — app shell. **Sidebar + topbar are fixed; only content scrolls** (`h-screen overflow-hidden` + content `overflow-y-auto`).
- `components/Sidebar.tsx`, `Topbar.tsx` (has the **dark-mode toggle** ☀️/🌙), `StatCard.tsx`, `StatusBadge.tsx`, `ColumnConstraintRow.tsx`, `CrossColumnRuleEditor.tsx`.
- `pages/Dashboard.tsx` (live runs, **auto-refresh every 4s**, delete-run modal), `RunDetail.tsx` (downloadable HTML report with checks-performed, timeline), `Profiles.tsx` (list + detail, delete), `ProfileEditor.tsx` (`/profiles/new`, `/profiles/:id/edit`; upload-sample [mocked inference] + build-manually), `Settings.tsx`.
- `lib/api.ts` (typed API client, `API_BASE = http://127.0.0.1:6500`), `lib/format.ts`, `lib/theme.ts` (`useTheme` hook — class-based dark mode).
- `types/index.ts`, `data/mockData.ts` (only `mockRuns` + `mockSettings` remain; profiles come from the API).
- `index.css` — **dark-mode is a centralized `.dark` remap layer** (remaps the app's hardcoded Tailwind utilities under `.dark` so all pages theme at once, instead of per-element `dark:` classes). `tailwind.config.js` has `darkMode: "class"`. `index.html` has a no-flash inline script that sets the theme before paint.

**Demo (`demo_files/`):** `seed_demo.py` wipes profiles/runs and creates 3 profiles + good/bad sample CSVs.

---

## 5. Database schema & environment

**Tables (Postgres, see `backend/schema.sql`):**
- `validation_profiles` — one per file type (name, file_pattern, file_type, allow_extra_columns, inbound_folder, success/failure/unknown_routing, notify_on_failure, email_recipients, …).
- `profile_columns` — per-column rules (required, unique_flag, data_type, min/max, regex, allowed_values[], severity).
- `profile_cross_column_rules` — two-column comparisons (left_column, op gt/gte/lt/lte/eq/neq, right_column, severity).
- `app_settings` — single row (id=1): default folders, SMTP-from, default_recipients.
- `validation_runs` — one per processed file (status, counts, destination_path, ai_summary JSON, notification_status, …).
- `run_issues` — every constraint failure (rule_name, severity, message, column_name, row_number, constraint_kind).
- `agent_events` — workflow timeline per run (agent, action, detail, occurred_at).

**`.env` (project ROOT, gitignored — NEVER commit or print values):** keys present:
`SUPABASE_URL`, `SUPABASE_SECRET_KEY`, `SERVICE_ROLE_KEY` (backend uses URL + SERVICE_ROLE_KEY), `ANTHROPIC_API_KEY`, `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `SMTP_FROM`.
Optional tunables (have sane defaults): `FG_WORKERS` (4), `FG_CHUNK_ROWS` (100000), `FG_MAX_FILE_MB` (0 = no cap), `FG_REFRESH_SECONDS` (15), `DASHBOARD_URL`. Template: `.env.example`.

**Current live data:** 3 active profiles in Supabase — `Employee CSV` (`employees_*.csv`), `Invoice CSV Validation` (`invoices_*.csv`), `Purchase Order CSV` (`po_*.csv`) — with inbound/good/quarantine/review folders under `/Users/rayyan/Desktop/File_Guradian_Agent_POC/`. Demo email recipients are placeholders (e.g. `hr@xorbix.com`); set them to a real inbox to see real alerts arrive.

---

## 6. Git state

- Branch: `master`. Last commit: `37461ac` (validation pipeline). **Everything since then is uncommitted** — the Notification agent, single `app.py`, Settings API, runs delete, demo files, the performance/robustness overhaul, email HTML, port changes, dark mode, sidebar fix, this handoff. (`.env`, `venv/`, `node_modules/`, `logs/`, `dist/` are gitignored.)
- **Do not commit/push unless the user explicitly asks.**

---

## 7. ⭐ THE ACTIVE TASK — convert to a self-contained local Windows app

**Goal (from Xorbix meeting notes, action item owned by Rayyan):** *"Convert web app to Windows application for internal server use."*

**Correct interpretation (confirmed with the user):**
- It stays a **web app** (browser-accessed). "Windows application / internal server use" = **host it on Xorbix's internal Windows server** for the team, with **no cloud dependency**. ("Internal server" may be a Windows Server VM in a data center / Azure — not necessarily a physical office.)
- **Keep Python. Do NOT migrate to .NET.** (The ".NET" in the notes referred to a *different* project's future stack. The user corrected this — respect it.)
- The user is new to Windows — explain Windows pieces simply.

**The plan (in order):**
1. **Database: Supabase → SQLite (the core change).** Replace the cloud DB with a local SQLite file so the app is truly standalone. Translate `backend/schema.sql` to SQLite, and replace the `supabase` client calls (in `Intake_agent/initial_check.py`, `pipeline.py`, `api/*.py`, `Monitor_agent/watchdog.py`) with a thin local DB layer (sqlite3 or SQLAlchemy). Keep the same table shapes so nothing else changes. **Recommended first step — everything else builds on it.**
2. **Serve the frontend from Flask.** `npm run build` the React app and serve the static `dist/` from Flask so **one process serves UI + API** (no separate Vite server in production).
3. **Bundle into a single `.exe`** with **PyInstaller** (`pyinstaller --onefile app.py`) so the server needs no Python install.
4. **Run as a Windows Service** with **NSSM** (auto-start on boot, restart on crash) — the "always on" piece for server use.
5. **(Optional) Installer** via Inno Setup for clean IT deployment.

**Notes/gotchas for the Windows move:** inbound folders may become **network shares (UNC paths)** — test `watchdog`/`FileSystemWatcher` against those. Multi-user on a server may eventually want **Windows/AD authentication** (none today — POC had no login, which is fine). SQLite is great for low/moderate concurrency; if they later need heavy concurrent writes, SQL Server Express is the upgrade.

**How the user will run Claude Code on the company side:** they just got **team/company Claude Code access** and are switching accounts for this project (the reason this handoff exists). On a corporate Windows VM, Claude Code needs outbound access to `api.anthropic.com` — if the VM is firewalled/proxied it may be blocked; the fallback is to develop where access works and move code via git. (This is context, not a blocker for the task itself.)

---

## 8. How to run & verify (commands)

```bash
# Backend (from repo root). Installs deps incl. waitress + numpy.
cd backend && ./venv/bin/pip install -r requirements.txt
./venv/bin/python app.py            # API on :6500 + Monitor (one command)

# Frontend
cd frontend && npm install
npm run dev                          # dev server on :6200  (open http://localhost:6200)
npm run build                        # production build → dist/

# Email check
./venv/bin/python backend/test_smtp.py mrayyanm411@gmail.com

# Reseed demo profiles + sample files
./venv/bin/python demo_files/seed_demo.py
```

- Build must stay green: `cd frontend && npm run build`, and `python -m py_compile` the backend files.
- The validator can be benchmarked by generating a large CSV and timing `validate_file` (no DB needed).
- Preview tooling: a `.claude/launch.json` exists pointing at the frontend dev server.

---

## 9. History / decisions worth knowing (so context isn't re-litigated)

- Validation model is **per-column constraint profiles** (Pandera-style), not a fixed rule catalog — chosen so any file type works without code changes. Includes cross-column rules. Optional columns = "present-only". Any error quarantines the whole file.
- Performance overhaul (most recent big work): N+1 profiles query → 3 bulk queries; per-cell Python validation → streaming vectorized pandas (~50× faster, flat memory); parallel worker pool; dynamic folder refresh (no restart); crash recovery; collision-safe moves; DB retries; CORS locked; waitress; dashboard auto-refresh; HTML emails; dark mode; sidebar/topbar fixed.
- Known minor leftovers: a stray Windows-path-named folder exists from earlier (`backend/C:\FileGuardian\...`) — junk, ignore/delete. Upload-sample inference in ProfileEditor is **mocked** (no real backend inference endpoint). No Teams webhook, no cross-run trend AI (both optional, not built).
- There is a file-based memory dir for the *previous* account at `~/.claude/projects/-Users-rayyan-Xorbix-FIle-Guardian-Agent/memory/` — the new account won't have it, so the key facts are captured in this doc instead.

---

## 10. First move for the new session

Recommended opening: confirm the plan in Section 7, then **start step 1 — convert the Supabase data layer to local SQLite** (translate `schema.sql`, add a small `db.py` helper, swap the `supabase.table(...)` calls), keeping every table shape identical so the rest of the app and the frontend keep working unchanged. Verify by running `app.py`, dropping a sample CSV from `demo_files/samples/`, and confirming a run appears with issues + timeline — all with **no internet/cloud**.
