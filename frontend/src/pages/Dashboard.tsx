import { Link } from "react-router-dom";
import {
  FileCheck2,
  FileX2,
  FolderOpen,
  Activity,
  Filter,
  ChevronRight,
  Mail,
  MailX,
  Send,
  Clock,
} from "lucide-react";
import { useMemo, useState } from "react";
import { Topbar } from "../components/Topbar";
import { StatCard } from "../components/StatCard";
import { StatusBadge } from "../components/StatusBadge";
import { mockRuns } from "../data/mockData";
import {
  formatDateTime,
  formatDuration,
  formatKb,
  formatRelative,
} from "../lib/format";
import type { RunStatus } from "../types";

const filterOptions: { value: RunStatus | "all"; label: string }[] = [
  { value: "all", label: "All" },
  { value: "passed", label: "Passed" },
  { value: "failed", label: "Failed" },
  { value: "quarantined", label: "Quarantined" },
  { value: "review", label: "Review" },
  { value: "processing", label: "Processing" },
];

export function Dashboard() {
  const [filter, setFilter] = useState<RunStatus | "all">("all");

  const stats = useMemo(() => {
    const total = mockRuns.length;
    const passed = mockRuns.filter((r) => r.status === "passed").length;
    const failed = mockRuns.filter(
      (r) => r.status === "failed" || r.status === "quarantined"
    ).length;
    const processing = mockRuns.filter(
      (r) => r.status === "processing"
    ).length;
    return { total, passed, failed, processing };
  }, []);

  const filtered = useMemo(() => {
    if (filter === "all") return mockRuns;
    return mockRuns.filter((r) => r.status === filter);
  }, [filter]);

  return (
    <>
      <Topbar
        title="Dashboard"
        subtitle="Recent file validation runs"
        actions={
          <button className="hidden md:inline-flex items-center gap-2 rounded-lg bg-brand-600 px-3.5 py-2 text-sm font-medium text-white hover:bg-brand-700 transition-colors">
            <FolderOpen className="h-4 w-4" />
            Open inbound folder
          </button>
        }
      />

      <main className="flex-1 px-6 py-6 space-y-6">
        {/* Stats grid */}
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
          <StatCard
            label="Total runs (24h)"
            value={stats.total}
            Icon={Activity}
            tone="info"
            trend="6 in the last 24 hours"
          />
          <StatCard
            label="Passed"
            value={stats.passed}
            Icon={FileCheck2}
            tone="success"
            trend="No action needed"
          />
          <StatCard
            label="Failed / Quarantined"
            value={stats.failed}
            Icon={FileX2}
            tone="danger"
            trend="Notifications sent"
          />
          <StatCard
            label="Processing now"
            value={stats.processing}
            Icon={Clock}
            tone="warning"
            trend="Active validation runs"
          />
        </div>

        {/* Runs table */}
        <section className="rounded-xl border border-slate-200 bg-white shadow-card overflow-hidden">
          <div className="flex flex-wrap items-center justify-between gap-3 px-5 py-4 border-b border-slate-200">
            <div>
              <h2 className="text-sm font-semibold text-slate-900">
                Recent validation runs
              </h2>
              <p className="text-xs text-slate-500">
                Last {mockRuns.length} files processed by the agent workflow
              </p>
            </div>
            <div className="flex items-center gap-2">
              <Filter className="h-4 w-4 text-slate-400" />
              <div className="flex rounded-lg border border-slate-200 bg-slate-50 p-0.5">
                {filterOptions.map((opt) => (
                  <button
                    key={opt.value}
                    onClick={() => setFilter(opt.value)}
                    className={`px-2.5 py-1 text-xs font-medium rounded-md transition-colors ${
                      filter === opt.value
                        ? "bg-white text-slate-900 shadow-card"
                        : "text-slate-500 hover:text-slate-700"
                    }`}
                  >
                    {opt.label}
                  </button>
                ))}
              </div>
            </div>
          </div>

          <div className="overflow-x-auto">
            <table className="min-w-full divide-y divide-slate-200">
              <thead className="bg-slate-50">
                <tr>
                  <Th>File</Th>
                  <Th>Status</Th>
                  <Th>Profile</Th>
                  <Th className="text-right">Issues</Th>
                  <Th>Notification</Th>
                  <Th>Received</Th>
                  <Th>Duration</Th>
                  <Th>Size</Th>
                  <Th className="w-8"></Th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100 bg-white">
                {filtered.map((run) => (
                  <tr
                    key={run.id}
                    className="hover:bg-slate-50/60 transition-colors"
                  >
                    <td className="px-5 py-3.5">
                      <Link
                        to={`/runs/${run.id}`}
                        className="block group"
                      >
                        <div className="font-medium text-sm text-slate-900 group-hover:text-brand-700 truncate max-w-xs">
                          {run.fileName}
                        </div>
                        <div className="text-xs text-slate-500 font-mono truncate max-w-xs">
                          {run.id}
                        </div>
                      </Link>
                    </td>
                    <td className="px-5 py-3.5">
                      <StatusBadge status={run.status} />
                    </td>
                    <td className="px-5 py-3.5 text-sm text-slate-700">
                      {run.profileName}
                    </td>
                    <td className="px-5 py-3.5 text-right">
                      {run.issueCount === 0 ? (
                        <span className="text-sm text-slate-400">—</span>
                      ) : (
                        <div className="flex items-center justify-end gap-2">
                          {run.errorCount > 0 && (
                            <span className="inline-flex items-center rounded-md bg-rose-50 px-1.5 py-0.5 text-xs font-medium text-rose-700">
                              {run.errorCount} error
                              {run.errorCount > 1 ? "s" : ""}
                            </span>
                          )}
                          {run.warningCount > 0 && (
                            <span className="inline-flex items-center rounded-md bg-amber-50 px-1.5 py-0.5 text-xs font-medium text-amber-700">
                              {run.warningCount} warn
                            </span>
                          )}
                        </div>
                      )}
                    </td>
                    <td className="px-5 py-3.5">
                      <NotificationCell status={run.notificationStatus} />
                    </td>
                    <td className="px-5 py-3.5">
                      <div className="text-sm text-slate-700">
                        {formatRelative(run.receivedAt)}
                      </div>
                      <div className="text-xs text-slate-400">
                        {formatDateTime(run.receivedAt)}
                      </div>
                    </td>
                    <td className="px-5 py-3.5 text-sm text-slate-700">
                      {formatDuration(run.receivedAt, run.completedAt)}
                    </td>
                    <td className="px-5 py-3.5 text-sm text-slate-700">
                      {formatKb(run.fileSizeKb)}
                    </td>
                    <td className="px-5 py-3.5">
                      <Link
                        to={`/runs/${run.id}`}
                        className="inline-flex items-center justify-center h-7 w-7 rounded-md text-slate-400 hover:bg-slate-100 hover:text-slate-700"
                      >
                        <ChevronRight className="h-4 w-4" />
                      </Link>
                    </td>
                  </tr>
                ))}

                {filtered.length === 0 ? (
                  <tr>
                    <td colSpan={9} className="px-5 py-12 text-center">
                      <p className="text-sm text-slate-500">
                        No runs match this filter.
                      </p>
                    </td>
                  </tr>
                ) : null}
              </tbody>
            </table>
          </div>
        </section>
      </main>
    </>
  );
}

function Th({
  children,
  className = "",
}: {
  children?: React.ReactNode;
  className?: string;
}) {
  return (
    <th
      className={`px-5 py-3 text-left text-xs font-medium uppercase tracking-wider text-slate-500 ${className}`}
    >
      {children}
    </th>
  );
}

function NotificationCell({
  status,
}: {
  status: "sent" | "not_required" | "failed" | "pending";
}) {
  switch (status) {
    case "sent":
      return (
        <span className="inline-flex items-center gap-1.5 text-xs text-slate-700">
          <Mail className="h-3.5 w-3.5 text-emerald-600" />
          Sent
        </span>
      );
    case "failed":
      return (
        <span className="inline-flex items-center gap-1.5 text-xs text-rose-700">
          <MailX className="h-3.5 w-3.5" />
          Failed
        </span>
      );
    case "pending":
      return (
        <span className="inline-flex items-center gap-1.5 text-xs text-sky-700">
          <Send className="h-3.5 w-3.5" />
          Pending
        </span>
      );
    default:
      return (
        <span className="inline-flex items-center gap-1.5 text-xs text-slate-400">
          —
        </span>
      );
  }
}
