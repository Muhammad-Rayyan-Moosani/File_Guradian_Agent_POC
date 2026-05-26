import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import {
  Plus,
  ShieldCheck,
  FileType2,
  Mail,
  FolderOutput,
  FolderInput,
  CheckCircle2,
  XCircle,
  Trash2,
  Pencil,
  Columns3,
  GitCompareArrows,
  Hash,
  Calendar,
  Type,
  AtSign,
  ToggleLeft,
  Binary,
  Loader2,
  AlertCircle,
} from "lucide-react";
import { Topbar } from "../components/Topbar";
import { api } from "../lib/api";
import type {
  ColumnConstraints,
  ColumnType,
  CrossColumnOp,
  CrossColumnRule,
  ProfileColumn,
  ValidationProfile,
} from "../types";

export function Profiles() {
  const [profiles, setProfiles] = useState<ValidationProfile[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);

  // Delete-confirm modal state
  const [confirmDelete, setConfirmDelete] = useState<ValidationProfile | null>(
    null
  );
  const [deleting, setDeleting] = useState(false);
  const [deleteError, setDeleteError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    api
      .listProfiles()
      .then((list) => {
        if (cancelled) return;
        setProfiles(list);
        setSelectedId(list[0]?.id ?? null);
      })
      .catch((e: Error) => !cancelled && setError(e.message))
      .finally(() => !cancelled && setLoading(false));
    return () => {
      cancelled = true;
    };
  }, []);

  const selected = profiles.find((p) => p.id === selectedId);

  async function handleConfirmDelete() {
    if (!confirmDelete) return;
    const idToDelete = confirmDelete.id;
    setDeleting(true);
    setDeleteError(null);
    try {
      await api.deleteProfile(idToDelete);
      const next = profiles.filter((p) => p.id !== idToDelete);
      setProfiles(next);
      // If we deleted the currently-selected one, pick another (or none).
      if (selectedId === idToDelete) {
        setSelectedId(next[0]?.id ?? null);
      }
      setConfirmDelete(null);
    } catch (e) {
      setDeleteError(e instanceof Error ? e.message : String(e));
    } finally {
      setDeleting(false);
    }
  }

  return (
    <>
      <Topbar
        title="Validation Profiles"
        subtitle="Define what makes a file valid"
        actions={
          <Link
            to="/profiles/new"
            className="hidden md:inline-flex items-center gap-2 rounded-lg bg-brand-600 px-3.5 py-2 text-sm font-medium text-white hover:bg-brand-700"
          >
            <Plus className="h-4 w-4" />
            New profile
          </Link>
        }
      />

      <main className="flex-1 px-6 py-6">
        {loading ? (
          <div className="rounded-xl border border-slate-200 bg-white p-12 text-center shadow-card">
            <Loader2 className="mx-auto h-6 w-6 animate-spin text-slate-400" />
            <p className="mt-2 text-sm text-slate-500">Loading profiles…</p>
          </div>
        ) : error ? (
          <div className="rounded-xl border border-rose-200 bg-rose-50 p-6 text-sm text-rose-800 flex items-start gap-3">
            <AlertCircle className="h-5 w-5 flex-shrink-0 mt-0.5" />
            <div>
              <div className="font-medium">Couldn't load profiles</div>
              <div className="text-rose-700 mt-0.5">{error}</div>
              <div className="text-xs text-rose-600 mt-1">
                Is the Flask backend running on <code>http://127.0.0.1:5000</code>?
              </div>
            </div>
          </div>
        ) : profiles.length === 0 ? (
          <div className="rounded-xl border border-dashed border-slate-300 bg-white p-12 text-center">
            <ShieldCheck className="mx-auto h-8 w-8 text-slate-400" />
            <p className="mt-3 text-sm font-medium text-slate-900">
              No validation profiles yet
            </p>
            <p className="mt-1 text-xs text-slate-500">
              Create your first profile to start validating files.
            </p>
            <Link
              to="/profiles/new"
              className="mt-4 inline-flex items-center gap-2 rounded-lg bg-brand-600 px-3.5 py-2 text-sm font-medium text-white hover:bg-brand-700"
            >
              <Plus className="h-4 w-4" />
              New profile
            </Link>
          </div>
        ) : (
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          {/* Left: profile list */}
          <aside className="lg:col-span-1 space-y-3">
            {profiles.map((p) => (
              <button
                key={p.id}
                onClick={() => setSelectedId(p.id)}
                className={`w-full text-left rounded-xl border bg-white p-4 shadow-card transition-all ${
                  selectedId === p.id
                    ? "border-brand-500 ring-2 ring-brand-100"
                    : "border-slate-200 hover:border-slate-300"
                }`}
              >
                <div className="flex items-start justify-between gap-3">
                  <div className="flex items-start gap-3 min-w-0">
                    <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-brand-50 text-brand-700 flex-shrink-0">
                      <ShieldCheck className="h-4 w-4" />
                    </div>
                    <div className="min-w-0">
                      <div className="text-sm font-semibold text-slate-900 truncate">
                        {p.name}
                      </div>
                      <div className="text-xs text-slate-500 mt-0.5 line-clamp-2">
                        {p.description}
                      </div>
                    </div>
                  </div>
                  {p.active ? (
                    <span className="inline-flex items-center gap-1 rounded-full bg-emerald-50 px-2 py-0.5 text-[10px] font-medium text-emerald-700 ring-1 ring-emerald-200">
                      <CheckCircle2 className="h-3 w-3" />
                      Active
                    </span>
                  ) : (
                    <span className="inline-flex items-center gap-1 rounded-full bg-slate-100 px-2 py-0.5 text-[10px] font-medium text-slate-600">
                      Draft
                    </span>
                  )}
                </div>
                <div className="mt-3 flex items-center gap-4 text-[11px] text-slate-500">
                  <span className="font-mono">{p.filePattern}</span>
                  <span>·</span>
                  <span>{p.columns.length} columns</span>
                  {p.crossColumnRules.length > 0 ? (
                    <>
                      <span>·</span>
                      <span>{p.crossColumnRules.length} cross-rule{p.crossColumnRules.length === 1 ? "" : "s"}</span>
                    </>
                  ) : null}
                </div>
              </button>
            ))}
          </aside>

          {/* Right: profile detail */}
          <section className="lg:col-span-2 space-y-6">
            {selected ? (
              <ProfileDetail
                profile={selected}
                onRequestDelete={() => setConfirmDelete(selected)}
              />
            ) : null}
          </section>
        </div>
        )}
      </main>

      {confirmDelete ? (
        <DeleteConfirmModal
          profile={confirmDelete}
          deleting={deleting}
          error={deleteError}
          onCancel={() => {
            if (deleting) return;
            setConfirmDelete(null);
            setDeleteError(null);
          }}
          onConfirm={handleConfirmDelete}
        />
      ) : null}
    </>
  );
}

function DeleteConfirmModal({
  profile,
  deleting,
  error,
  onCancel,
  onConfirm,
}: {
  profile: ValidationProfile;
  deleting: boolean;
  error: string | null;
  onCancel: () => void;
  onConfirm: () => void;
}) {
  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/40 backdrop-blur-sm px-4"
      role="dialog"
      aria-modal="true"
    >
      <div className="w-full max-w-md rounded-xl bg-white shadow-2xl border border-slate-200">
        <div className="p-5 flex items-start gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-full bg-rose-50 text-rose-600 flex-shrink-0">
            <Trash2 className="h-5 w-5" />
          </div>
          <div className="min-w-0">
            <h3 className="text-base font-semibold text-slate-900">
              Delete this profile?
            </h3>
            <p className="mt-1 text-sm text-slate-600">
              <span className="font-medium text-slate-900">
                {profile.name}
              </span>{" "}
              and its {profile.columns.length} column
              {profile.columns.length === 1 ? "" : "s"}
              {profile.crossColumnRules.length > 0
                ? ` + ${profile.crossColumnRules.length} cross-column rule${
                    profile.crossColumnRules.length === 1 ? "" : "s"
                  }`
                : ""}{" "}
              will be permanently removed. Files already validated stay in the
              dashboard.
            </p>
            <p className="mt-2 text-xs text-rose-700 inline-flex items-center gap-1">
              <AlertCircle className="h-3.5 w-3.5" />
              This action cannot be undone.
            </p>
            {error ? (
              <div className="mt-3 rounded-md bg-rose-50 border border-rose-200 px-3 py-2 text-xs text-rose-800">
                <strong>Couldn't delete:</strong> {error}
              </div>
            ) : null}
          </div>
        </div>
        <div className="px-5 py-3 bg-slate-50 border-t border-slate-200 flex items-center justify-end gap-2 rounded-b-xl">
          <button
            type="button"
            onClick={onCancel}
            disabled={deleting}
            className="rounded-lg border border-slate-200 bg-white px-3.5 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={onConfirm}
            disabled={deleting}
            className="inline-flex items-center gap-1.5 rounded-lg bg-rose-600 px-3.5 py-2 text-sm font-medium text-white hover:bg-rose-700 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            <Trash2 className="h-4 w-4" />
            {deleting ? "Deleting…" : "Delete profile"}
          </button>
        </div>
      </div>
    </div>
  );
}

function ProfileDetail({
  profile,
  onRequestDelete,
}: {
  profile: ValidationProfile;
  onRequestDelete: () => void;
}) {
  return (
    <>
      <div className="rounded-xl border border-slate-200 bg-white p-6 shadow-card">
        <div className="flex items-start justify-between gap-4">
          <div>
            <h2 className="text-lg font-semibold text-slate-900">
              {profile.name}
            </h2>
            <p className="text-sm text-slate-500 mt-1">{profile.description}</p>
          </div>
          <div className="flex items-center gap-2">
            <Link
              to={`/profiles/${profile.id}/edit`}
              className="inline-flex items-center gap-1.5 rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-sm text-slate-700 hover:bg-slate-50"
            >
              <Pencil className="h-3.5 w-3.5" />
              Edit
            </Link>
            <button
              type="button"
              onClick={onRequestDelete}
              className="inline-flex items-center gap-1.5 rounded-lg border border-rose-200 bg-white px-3 py-1.5 text-sm text-rose-700 hover:bg-rose-50"
            >
              <Trash2 className="h-3.5 w-3.5" />
              Delete
            </button>
          </div>
        </div>

        <div className="mt-6 grid grid-cols-2 md:grid-cols-4 gap-5">
          <Meta Icon={FileType2} label="File type" value={profile.fileType} />
          <Meta
            Icon={ShieldCheck}
            label="File pattern"
            value={profile.filePattern}
            mono
          />
          <Meta
            Icon={Columns3}
            label="Columns declared"
            value={String(profile.columns.length)}
          />
          <Meta
            Icon={Mail}
            label="Notify on failure"
            value={profile.notifyOnFailure ? "Yes" : "No"}
          />
        </div>

        <div className="mt-4 flex items-center gap-2 text-xs text-slate-500">
          {profile.allowExtraColumns ? (
            <span className="inline-flex items-center gap-1 rounded-md bg-slate-100 px-2 py-1">
              <CheckCircle2 className="h-3 w-3 text-slate-500" />
              Extra columns allowed
            </span>
          ) : (
            <span className="inline-flex items-center gap-1 rounded-md bg-rose-50 px-2 py-1 text-rose-700">
              <XCircle className="h-3 w-3" />
              Extra columns rejected
            </span>
          )}
        </div>
      </div>

      {/* Columns table */}
      <div className="rounded-xl border border-slate-200 bg-white shadow-card overflow-hidden">
        <div className="px-5 py-4 border-b border-slate-200 flex items-center justify-between">
          <div>
            <h3 className="text-sm font-semibold text-slate-900 inline-flex items-center gap-2">
              <Columns3 className="h-4 w-4 text-slate-500" />
              Columns
            </h3>
            <p className="text-xs text-slate-500 mt-0.5">
              {profile.columns.length} declared columns and their per-column
              constraints
            </p>
          </div>
        </div>

        <div className="overflow-x-auto">
          <table className="min-w-full divide-y divide-slate-200">
            <thead className="bg-slate-50">
              <tr>
                <Th>Column</Th>
                <Th>Type</Th>
                <Th className="text-center">Required</Th>
                <Th className="text-center">Unique</Th>
                <Th>Constraints</Th>
                <Th>Severity</Th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100 bg-white">
              {profile.columns.map((col) => (
                <ColumnRow key={col.id} col={col} />
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* Cross-column rules */}
      <div className="rounded-xl border border-slate-200 bg-white shadow-card overflow-hidden">
        <div className="px-5 py-4 border-b border-slate-200">
          <h3 className="text-sm font-semibold text-slate-900 inline-flex items-center gap-2">
            <GitCompareArrows className="h-4 w-4 text-slate-500" />
            Cross-column rules
          </h3>
          <p className="text-xs text-slate-500 mt-0.5">
            Compare two columns row-by-row (e.g. <code>DueDate &gt; InvoiceDate</code>).
          </p>
        </div>
        {profile.crossColumnRules.length === 0 ? (
          <div className="px-5 py-8 text-center">
            <p className="text-sm text-slate-500">
              No cross-column rules configured for this profile.
            </p>
          </div>
        ) : (
          <ul className="divide-y divide-slate-100">
            {profile.crossColumnRules.map((rule) => (
              <CrossRuleRow key={rule.id} rule={rule} />
            ))}
          </ul>
        )}
      </div>

      {/* Routing + recipients */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        <div className="rounded-xl border border-slate-200 bg-white p-6 shadow-card">
          <div className="flex items-center gap-2 mb-3">
            <FolderInput className="h-4 w-4 text-slate-500" />
            <h3 className="text-sm font-semibold text-slate-900">
              Folder paths
            </h3>
          </div>
          <dl className="space-y-3 text-sm">
            <RoutingRow
              label="Inbound (watched)"
              path={profile.inboundFolder}
              Icon={FolderInput}
              tone="brand"
            />
            <div className="border-t border-slate-100 pt-3 space-y-3">
              <RoutingRow
                label="Success"
                path={profile.successRouting}
                Icon={CheckCircle2}
                tone="success"
              />
              <RoutingRow
                label="Failure"
                path={profile.failureRouting}
                Icon={XCircle}
                tone="danger"
              />
              <RoutingRow
                label="Unknown"
                path={profile.unknownRouting}
                Icon={FolderOutput}
                tone="info"
              />
            </div>
          </dl>
        </div>

        <div className="rounded-xl border border-slate-200 bg-white p-6 shadow-card">
          <div className="flex items-center gap-2 mb-3">
            <Mail className="h-4 w-4 text-slate-500" />
            <h3 className="text-sm font-semibold text-slate-900">
              Notification recipients
            </h3>
          </div>
          {profile.recipients.length === 0 ? (
            <p className="text-sm text-slate-500">No recipients configured.</p>
          ) : (
            <ul className="space-y-2">
              {profile.recipients.map((r) => (
                <li
                  key={r}
                  className="flex items-center gap-2 rounded-md bg-slate-50 px-3 py-2 text-sm text-slate-700"
                >
                  <Mail className="h-3.5 w-3.5 text-slate-400" />
                  {r}
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>
    </>
  );
}

/* ------------------------------------------------------------------------ */
/* Sub-components                                                            */
/* ------------------------------------------------------------------------ */

const typeIcon: Record<ColumnType, React.ComponentType<{ className?: string }>> = {
  string: Type,
  integer: Hash,
  decimal: Hash,
  date: Calendar,
  datetime: Calendar,
  email: AtSign,
  boolean: ToggleLeft,
};

function ColumnRow({ col }: { col: ProfileColumn }) {
  const { constraints } = col;
  const hasContentChecks = Boolean(
    constraints.type ||
      constraints.min !== undefined ||
      constraints.max !== undefined ||
      constraints.regex ||
      (constraints.allowedValues && constraints.allowedValues.length > 0) ||
      constraints.required ||
      constraints.unique
  );

  const Icon = constraints.type ? typeIcon[constraints.type] : Binary;

  return (
    <tr className="hover:bg-slate-50/60">
      <td className="px-5 py-3.5">
        <div className="font-medium text-sm text-slate-900">{col.name}</div>
        {col.description ? (
          <div className="text-xs text-slate-500 mt-0.5">{col.description}</div>
        ) : null}
      </td>
      <td className="px-5 py-3.5">
        {constraints.type ? (
          <span className="inline-flex items-center gap-1.5 rounded-md bg-slate-100 px-2 py-1 text-xs font-medium text-slate-700">
            <Icon className="h-3 w-3" />
            {constraints.type}
          </span>
        ) : (
          <span className="text-xs text-slate-400">—</span>
        )}
      </td>
      <td className="px-5 py-3.5 text-center">
        <BoolDot on={!!constraints.required} />
      </td>
      <td className="px-5 py-3.5 text-center">
        <BoolDot on={!!constraints.unique} />
      </td>
      <td className="px-5 py-3.5">
        <ConstraintSummary c={constraints} hasAny={hasContentChecks} />
      </td>
      <td className="px-5 py-3.5">
        <SeverityPill severity={constraints.severity} />
      </td>
    </tr>
  );
}

function BoolDot({ on }: { on: boolean }) {
  return on ? (
    <span className="inline-flex h-5 w-5 items-center justify-center rounded-full bg-emerald-50 text-emerald-600">
      <CheckCircle2 className="h-3.5 w-3.5" />
    </span>
  ) : (
    <span className="text-slate-300">—</span>
  );
}

function ConstraintSummary({
  c,
  hasAny,
}: {
  c: ColumnConstraints;
  hasAny: boolean;
}) {
  if (!hasAny) {
    return (
      <span className="inline-flex items-center rounded-md bg-violet-50 px-2 py-1 text-[11px] font-medium text-violet-700">
        Present-only
      </span>
    );
  }
  const badges: string[] = [];
  if (c.min !== undefined) badges.push(`min ${c.min}`);
  if (c.max !== undefined) badges.push(`max ${c.max}`);
  if (c.regex) badges.push(`regex`);
  if (c.allowedValues && c.allowedValues.length > 0)
    badges.push(`enum (${c.allowedValues.length})`);
  if (badges.length === 0)
    return <span className="text-xs text-slate-400">—</span>;
  return (
    <div className="flex flex-wrap gap-1">
      {badges.map((b) => (
        <span
          key={b}
          className="inline-flex items-center rounded-md bg-slate-100 px-1.5 py-0.5 text-[11px] font-mono text-slate-700"
        >
          {b}
        </span>
      ))}
      {c.regex ? (
        <span className="inline-flex items-center rounded-md bg-slate-100 px-1.5 py-0.5 text-[11px] font-mono text-slate-700 max-w-[14rem] truncate">
          {c.regex}
        </span>
      ) : null}
    </div>
  );
}

function SeverityPill({ severity }: { severity: "error" | "warning" }) {
  return (
    <span
      className={`inline-flex items-center rounded-md px-1.5 py-0.5 text-[10px] font-medium uppercase tracking-wider ${
        severity === "error"
          ? "bg-rose-50 text-rose-700"
          : "bg-amber-50 text-amber-700"
      }`}
    >
      {severity}
    </span>
  );
}

const opLabel: Record<CrossColumnOp, string> = {
  gt: ">",
  gte: "≥",
  lt: "<",
  lte: "≤",
  eq: "=",
  neq: "≠",
};

function CrossRuleRow({ rule }: { rule: CrossColumnRule }) {
  return (
    <li className="px-5 py-3.5 flex items-center justify-between gap-4">
      <div className="flex items-center gap-3 min-w-0">
        <div className="flex h-7 w-7 items-center justify-center rounded-md bg-sky-50 text-sky-700 flex-shrink-0">
          <GitCompareArrows className="h-4 w-4" />
        </div>
        <div className="min-w-0">
          <div className="text-sm font-medium text-slate-900">{rule.name}</div>
          <div className="text-xs text-slate-500 mt-0.5 font-mono">
            <span className="text-slate-900">{rule.leftColumn}</span>{" "}
            <span className="px-1 text-slate-500">{opLabel[rule.op]}</span>{" "}
            <span className="text-slate-900">{rule.rightColumn}</span>
          </div>
        </div>
      </div>
      <SeverityPill severity={rule.severity} />
    </li>
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

function Meta({
  Icon,
  label,
  value,
  mono = false,
}: {
  Icon: React.ComponentType<{ className?: string }>;
  label: string;
  value: string;
  mono?: boolean;
}) {
  return (
    <div>
      <div className="flex items-center gap-1.5 text-xs text-slate-500">
        <Icon className="h-3.5 w-3.5" />
        {label}
      </div>
      <div
        className={`mt-1 text-sm text-slate-900 ${
          mono ? "font-mono text-xs" : ""
        }`}
      >
        {value}
      </div>
    </div>
  );
}

function RoutingRow({
  label,
  path,
  Icon,
  tone,
}: {
  label: string;
  path: string;
  Icon: React.ComponentType<{ className?: string }>;
  tone: "success" | "danger" | "info" | "brand";
}) {
  const tones = {
    success: "bg-emerald-50 text-emerald-600",
    danger: "bg-rose-50 text-rose-600",
    info: "bg-sky-50 text-sky-600",
    brand: "bg-brand-50 text-brand-700",
  };
  return (
    <div className="flex items-center gap-3">
      <div
        className={`flex h-7 w-7 items-center justify-center rounded-md ${tones[tone]}`}
      >
        <Icon className="h-3.5 w-3.5" />
      </div>
      <div className="flex-1 min-w-0">
        <div className="text-xs text-slate-500">{label}</div>
        <div className="text-sm font-mono text-slate-900 truncate">{path}</div>
      </div>
    </div>
  );
}
