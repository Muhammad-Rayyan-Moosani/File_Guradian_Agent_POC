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
} from "lucide-react";
import { Topbar } from "../components/Topbar";
import { StatusBadge } from "../components/StatusBadge";
import { mockRuns } from "../data/mockData";
import { formatDateTime, formatDuration, formatKb } from "../lib/format";

export function RunDetail() {
  const { id } = useParams();
  const run = mockRuns.find((r) => r.id === id);

  if (!run) {
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
            No validation run with id <code>{id}</code> exists.
          </p>
        </main>
      </>
    );
  }

  const errors = run.issues.filter((i) => i.severity === "error");
  const warnings = run.issues.filter((i) => i.severity === "warning");

  return (
    <>
      <Topbar
        title={run.fileName}
        subtitle={`Run ${run.id} · ${run.profileName}`}
        actions={
          <button className="hidden md:inline-flex items-center gap-2 rounded-lg border border-slate-200 bg-white px-3.5 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50">
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
                {run.aiSummary}
              </p>
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
