import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import {
  ArrowLeft,
  FileText,
  Sparkles,
  AlertCircle,
  AlertTriangle,
  CheckCircle2,
  Download,
  ChevronRight,
  Bot,
  Loader2,
} from "lucide-react";
import { Topbar } from "../components/Topbar";
import { StatusBadge } from "../components/StatusBadge";
import { api } from "../lib/api";
import { formatDateTime, formatDuration, formatKb } from "../lib/format";
import type { ValidationProfile, ValidationRun } from "../types";

export function RunDetail() {
  const { id } = useParams();
  const [run, setRun] = useState<ValidationRun | null>(null);
  const [profile, setProfile] = useState<ValidationProfile | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!id) return;
    let cancelled = false;
    api
      .getRun(id)
      .then((r) => {
        if (cancelled) return;
        setRun(r);
        // Also load the profile so the report can list every check performed.
        if (r.profileId && r.profileId !== "—") {
          api
            .getProfile(r.profileId)
            .then((p) => !cancelled && setProfile(p))
            .catch(() => {}); // report still works without it
        }
      })
      .catch((e: Error) => !cancelled && setError(e.message))
      .finally(() => !cancelled && setLoading(false));
    return () => {
      cancelled = true;
    };
  }, [id]);

  if (loading) {
    return (
      <>
        <Topbar title="Loading run…" />
        <main className="flex-1 px-6 py-12 text-center">
          <Loader2 className="mx-auto h-6 w-6 animate-spin text-slate-400" />
        </main>
      </>
    );
  }

  if (error || !run) {
    return (
      <>
        <Topbar title="Run not found" />
        <main className="flex-1 px-6 py-6">
          <Link
            to="/"
            className="inline-flex items-center gap-1.5 text-sm text-brand-700 hover:text-brand-800"
          >
            <ArrowLeft className="h-4 w-4" />
            Back to dashboard
          </Link>
          <p className="mt-4 text-sm text-slate-500">
            {error
              ? `Couldn't load run: ${error}`
              : `No validation run with id ${id} exists.`}
          </p>
        </main>
      </>
    );
  }

  const errors = run.issues.filter((i) => i.severity === "error");
  const warnings = run.issues.filter((i) => i.severity === "warning");

  function downloadReport(current: ValidationRun) {
    const html = buildReportHtml(current, profile);
    const blob = new Blob([html], { type: "text/html" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `validation-report-${current.fileName}.html`;
    link.click();
    URL.revokeObjectURL(url);
  }

  return (
    <>
      <Topbar
        title={run.fileName}
        subtitle={`Run ${run.id} · ${run.profileName}`}
        actions={
          <button
            onClick={() => downloadReport(run)}
            className="hidden md:inline-flex items-center gap-2 rounded-lg border border-slate-200 bg-white px-3.5 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50"
          >
            <Download className="h-4 w-4" />
            Download report
          </button>
        }
      />

      <main className="flex-1 px-6 py-6 space-y-6">
        <div className="flex items-center gap-1 text-sm text-slate-500">
          <Link to="/" className="hover:text-slate-900">
            Dashboard
          </Link>
          <ChevronRight className="h-3.5 w-3.5" />
          <span className="text-slate-900">{run.id}</span>
        </div>

        {/* Header card */}
        <section className="rounded-xl border border-slate-200 bg-white p-6 shadow-card">
          <div className="flex flex-wrap items-start justify-between gap-4">
            <div className="flex items-start gap-4">
              <div className="flex h-12 w-12 items-center justify-center rounded-lg bg-brand-50 text-brand-700">
                <FileText className="h-6 w-6" />
              </div>
              <div>
                <div className="flex items-center gap-3 flex-wrap">
                  <h2 className="text-lg font-semibold text-slate-900">
                    {run.fileName}
                  </h2>
                  <StatusBadge status={run.status} />
                </div>
                <p className="text-sm text-slate-500 mt-1">
                  Received {formatDateTime(run.receivedAt)} · Size{" "}
                  {formatKb(run.fileSizeKb)}
                </p>
              </div>
            </div>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-x-8 gap-y-3">
              <Meta label="Errors" value={String(run.errorCount)} />
              <Meta label="Warnings" value={String(run.warningCount)} />
              <Meta
                label="Duration"
                value={formatDuration(run.receivedAt, run.completedAt)}
              />
              <Meta
                label="Destination"
                value={run.destinationPath ?? "—"}
                mono
              />
            </div>
          </div>
        </section>

        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          {/* Left: AI summary + issues */}
          <div className="lg:col-span-2 space-y-6">
            {/* AI summary */}
            <section className="rounded-xl border border-slate-200 bg-white p-6 shadow-card">
              <div className="flex items-center gap-2 mb-3">
                <div className="flex h-7 w-7 items-center justify-center rounded-md bg-gradient-to-br from-violet-500 to-fuchsia-600 text-white">
                  <Sparkles className="h-4 w-4" />
                </div>
                <h3 className="text-sm font-semibold text-slate-900">
                  AI-generated summary
                </h3>
                <span className="ml-auto inline-flex items-center rounded-md bg-slate-100 px-1.5 py-0.5 text-[10px] font-medium text-slate-600 uppercase tracking-wider">
                  Explanation Agent
                </span>
              </div>
              <p className="text-sm leading-relaxed text-slate-700">
                {run.aiSummary.summary || "No summary available."}
              </p>

              {run.aiSummary.impact ? (
                <div className="mt-4">
                  <div className="text-[11px] font-medium uppercase tracking-wider text-slate-500">
                    Likely impact
                  </div>
                  <p className="mt-1 text-sm leading-relaxed text-slate-700">
                    {run.aiSummary.impact}
                  </p>
                </div>
              ) : null}

              {run.aiSummary.action ? (
                <div className="mt-4 rounded-lg bg-amber-50 border border-amber-100 px-3 py-2.5">
                  <div className="text-[11px] font-medium uppercase tracking-wider text-amber-700">
                    Recommended action
                  </div>
                  <p className="mt-1 text-sm leading-relaxed text-amber-900">
                    {run.aiSummary.action}
                  </p>
                </div>
              ) : null}
            </section>

            {/* Issues */}
            <section className="rounded-xl border border-slate-200 bg-white shadow-card overflow-hidden">
              <div className="px-5 py-4 border-b border-slate-200 flex items-center justify-between">
                <h3 className="text-sm font-semibold text-slate-900">
                  Validation issues
                </h3>
                <span className="text-xs text-slate-500">
                  {run.issueCount} total
                </span>
              </div>

              {run.issues.length === 0 ? (
                <div className="px-5 py-12 text-center">
                  <CheckCircle2 className="mx-auto h-10 w-10 text-emerald-500" />
                  <p className="mt-2 text-sm font-medium text-slate-900">
                    All checks passed
                  </p>
                  <p className="text-xs text-slate-500">
                    No issues found in this file.
                  </p>
                </div>
              ) : (
                <ul className="divide-y divide-slate-100">
                  {[...errors, ...warnings].map((issue) => (
                    <li key={issue.id} className="px-5 py-4 flex gap-3">
                      <div
                        className={`mt-0.5 flex h-6 w-6 items-center justify-center rounded-md flex-shrink-0 ${
                          issue.severity === "error"
                            ? "bg-rose-50 text-rose-600"
                            : "bg-amber-50 text-amber-600"
                        }`}
                      >
                        {issue.severity === "error" ? (
                          <AlertCircle className="h-4 w-4" />
                        ) : (
                          <AlertTriangle className="h-4 w-4" />
                        )}
                      </div>
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2 flex-wrap">
                          <span className="text-sm font-medium text-slate-900">
                            {issue.rule}
                          </span>
                          <span
                            className={`inline-flex items-center rounded-md px-1.5 py-0.5 text-[10px] font-medium uppercase tracking-wider ${
                              issue.severity === "error"
                                ? "bg-rose-50 text-rose-700"
                                : "bg-amber-50 text-amber-700"
                            }`}
                          >
                            {issue.severity}
                          </span>
                        </div>
                        <p className="text-sm text-slate-600 mt-0.5">
                          {issue.message}
                        </p>
                        {issue.location ? (
                          <p className="text-xs text-slate-400 font-mono mt-1">
                            {issue.location}
                          </p>
                        ) : null}
                      </div>
                    </li>
                  ))}
                </ul>
              )}
            </section>
          </div>

          {/* Right: agent timeline + notification */}
          <div className="space-y-6">
            <section className="rounded-xl border border-slate-200 bg-white p-5 shadow-card">
              <h3 className="text-sm font-semibold text-slate-900 mb-1">
                Notification
              </h3>
              <p className="text-xs text-slate-500 mb-3">
                Recipients for this run
              </p>
              {run.notifiedRecipients && run.notifiedRecipients.length > 0 ? (
                <ul className="space-y-1.5">
                  {run.notifiedRecipients.map((r) => (
                    <li
                      key={r}
                      className="flex items-center gap-2 text-sm text-slate-700"
                    >
                      <div className="h-1.5 w-1.5 rounded-full bg-emerald-500" />
                      {r}
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="text-sm text-slate-500">
                  No notification required for this run.
                </p>
              )}
            </section>

            <section className="rounded-xl border border-slate-200 bg-white p-5 shadow-card">
              <div className="flex items-center gap-2 mb-4">
                <Bot className="h-4 w-4 text-slate-500" />
                <h3 className="text-sm font-semibold text-slate-900">
                  Agent workflow timeline
                </h3>
              </div>
              <ol className="relative space-y-4">
                <span className="absolute left-[7px] top-2 bottom-2 w-px bg-slate-200" />
                {run.events.map((ev, i) => (
                  <li key={i} className="relative pl-6">
                    <span className="absolute left-0 top-1.5 h-3.5 w-3.5 rounded-full bg-white ring-2 ring-brand-500" />
                    <div className="flex items-center gap-2">
                      <span className="text-xs font-medium uppercase tracking-wider text-brand-700">
                        {ev.agent}
                      </span>
                      <span className="text-[11px] text-slate-400">
                        {formatDateTime(ev.timestamp)}
                      </span>
                    </div>
                    <p className="text-sm text-slate-700 mt-0.5">{ev.action}</p>
                    {ev.detail ? (
                      <p className="text-xs text-slate-500 mt-0.5">
                        {ev.detail}
                      </p>
                    ) : null}
                  </li>
                ))}
              </ol>
            </section>
          </div>
        </div>
      </main>
    </>
  );
}

function Meta({
  label,
  value,
  mono = false,
}: {
  label: string;
  value: string;
  mono?: boolean;
}) {
  return (
    <div>
      <div className="text-xs text-slate-500">{label}</div>
      <div
        className={`text-sm text-slate-900 ${
          mono ? "font-mono text-xs break-all" : ""
        }`}
      >
        {value}
      </div>
    </div>
  );
}

function buildReportHtml(
  run: ValidationRun,
  profile: ValidationProfile | null
): string {
  const esc = (s: unknown) =>
    String(s ?? "").replace(/[&<>]/g, (c) =>
      c === "&" ? "&amp;" : c === "<" ? "&lt;" : "&gt;"
    );

  // Build the full list of checks the profile defines, and mark each one
  // passed or failed by looking for a matching issue.
  const checks = listChecks(profile);
  for (const check of checks) {
    check.failed = run.issues.some(
      (i) =>
        i.constraintKind === check.kind &&
        (check.column === "" || i.columnName === check.column)
    );
  }
  const passedCount = checks.filter((c) => !c.failed).length;
  const failedCount = checks.filter((c) => c.failed).length;

  const checkRows = checks
    .map(
      (c) => `<tr>
        <td>${esc(c.label)}</td>
        <td>${c.failed ? "FAIL" : "PASS"}</td>
      </tr>`
    )
    .join("");

  const issueRows = run.issues
    .map(
      (i) => `<tr>
        <td>${esc(i.severity)}</td>
        <td>${esc(i.rule)}</td>
        <td>${esc(i.message)}</td>
        <td>${esc(i.location ?? "")}</td>
      </tr>`
    )
    .join("");

  const eventRows = run.events
    .map(
      (e) => `<tr>
        <td>${esc(e.agent)}</td>
        <td>${esc(e.action)}</td>
        <td>${esc(e.detail ?? "")}</td>
        <td>${esc(formatDateTime(e.timestamp))}</td>
      </tr>`
    )
    .join("");

  const s = run.aiSummary;

  return `<!doctype html>
<html><head><meta charset="utf-8">
<title>Validation Report — ${esc(run.fileName)}</title>
<style>
  body { font-family: Arial, sans-serif; color: #1e293b; max-width: 820px; margin: 40px auto; padding: 0 20px; }
  h1 { font-size: 22px; } h2 { font-size: 16px; margin-top: 28px; border-bottom: 1px solid #e2e8f0; padding-bottom: 4px; }
  table { width: 100%; border-collapse: collapse; margin-top: 8px; font-size: 13px; }
  th, td { border: 1px solid #e2e8f0; padding: 6px 8px; text-align: left; vertical-align: top; }
  th { background: #f8fafc; }
  .meta td:first-child { font-weight: bold; width: 180px; }
  .status { display: inline-block; padding: 2px 10px; border-radius: 999px; font-weight: bold; }
</style></head>
<body>
  <h1>File Guardian — Validation Report</h1>
  <table class="meta">
    <tr><td>File</td><td>${esc(run.fileName)}</td></tr>
    <tr><td>Status</td><td>${esc(run.status.toUpperCase())}</td></tr>
    <tr><td>Profile</td><td>${esc(run.profileName)}</td></tr>
    <tr><td>Received</td><td>${esc(formatDateTime(run.receivedAt))}</td></tr>
    <tr><td>Completed</td><td>${esc(formatDateTime(run.completedAt))}</td></tr>
    <tr><td>Errors / Warnings</td><td>${run.errorCount} error(s), ${run.warningCount} warning(s)</td></tr>
    <tr><td>Destination</td><td>${esc(run.destinationPath ?? "")}</td></tr>
    <tr><td>Notification</td><td>${esc(run.notificationStatus)}</td></tr>
    <tr><td>Run reference</td><td>${esc(run.id)}</td></tr>
  </table>

  <h2>Summary</h2>
  <p>${esc(s.summary) || "No summary available."}</p>
  ${s.impact ? `<p><strong>Likely impact:</strong> ${esc(s.impact)}</p>` : ""}
  ${s.action ? `<p><strong>Recommended action:</strong> ${esc(s.action)}</p>` : ""}

  <h2>Checks performed</h2>
  ${
    checks.length
      ? `<p>${checks.length} checks performed · ${passedCount} passed · ${failedCount} failed</p>
         <table><thead><tr><th>Check</th><th>Result</th></tr></thead><tbody>${checkRows}</tbody></table>`
      : "<p>Check list unavailable (no profile loaded).</p>"
  }

  <h2>Issues (${run.issues.length})</h2>
  ${
    run.issues.length
      ? `<table><thead><tr><th>Severity</th><th>Rule</th><th>Message</th><th>Location</th></tr></thead><tbody>${issueRows}</tbody></table>`
      : "<p>No issues found.</p>"
  }

  <h2>Agent timeline</h2>
  ${
    run.events.length
      ? `<table><thead><tr><th>Agent</th><th>Action</th><th>Detail</th><th>Time</th></tr></thead><tbody>${eventRows}</tbody></table>`
      : "<p>No events recorded.</p>"
  }

  <p style="margin-top:32px; font-size:12px; color:#64748b;">
    Generated by File Guardian Agent · open this file and print to PDF if needed.
  </p>
</body></html>`;
}

interface ReportCheck {
  label: string;
  kind: string;
  column: string;
  failed: boolean;
}

function listChecks(profile: ValidationProfile | null): ReportCheck[] {
  const checks: ReportCheck[] = [];
  if (!profile) return checks;

  for (const column of profile.columns) {
    const c = column.constraints;
    if (c.required) {
      checks.push({ label: `${column.name} — present & not blank`, kind: "required", column: column.name, failed: false });
    }
    if (c.type) {
      checks.push({ label: `${column.name} — type is ${c.type}`, kind: "type", column: column.name, failed: false });
    }
    if (c.unique) {
      checks.push({ label: `${column.name} — values are unique`, kind: "unique", column: column.name, failed: false });
    }
    if (c.min !== undefined && c.min !== null && c.min !== "") {
      checks.push({ label: `${column.name} — at least ${c.min}`, kind: "min", column: column.name, failed: false });
    }
    if (c.max !== undefined && c.max !== null && c.max !== "") {
      checks.push({ label: `${column.name} — at most ${c.max}`, kind: "max", column: column.name, failed: false });
    }
    if (c.regex) {
      checks.push({ label: `${column.name} — matches pattern`, kind: "regex", column: column.name, failed: false });
    }
    if (c.allowedValues && c.allowedValues.length > 0) {
      checks.push({ label: `${column.name} — one of the allowed values`, kind: "allowed_values", column: column.name, failed: false });
    }
  }

  for (const rule of profile.crossColumnRules) {
    checks.push({ label: rule.name, kind: "cross", column: rule.leftColumn, failed: false });
  }

  return checks;
}
