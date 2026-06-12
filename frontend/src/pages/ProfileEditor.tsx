import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import {
  ArrowLeft,
  Save,
  Upload,
  Pencil,
  Plus,
  ChevronRight,
  X,
  Mail,
  MessageSquare,
  FolderOutput,
  FolderInput,
  CheckCircle2,
  XCircle,
  Columns3,
  GitCompareArrows,
  Sparkles,
  FileText,
  AlertCircle,
  ArrowRight,
  ShieldCheck,
} from "lucide-react";
import { Topbar } from "../components/Topbar";
import { ColumnConstraintRow } from "../components/ColumnConstraintRow";
import { CrossColumnRuleEditor } from "../components/CrossColumnRuleEditor";
import { api } from "../lib/api";
import type {
  CrossColumnRule,
  ProfileColumn,
  ValidationProfile,
} from "../types";

type Mode = "upload" | "manual";

function emptyProfile(): ValidationProfile {
  const now = new Date().toISOString();
  return {
    id: `prof_${Date.now()}`,
    name: "",
    description: "",
    active: true,
    filePattern: "",
    fileType: "CSV",
    autoDetectType: false,
    columns: [],
    crossColumnRules: [],
    allowExtraColumns: true,
    inboundFolder: "",
    successRouting: "C:\\FileGuardian\\processed\\good",
    failureRouting: "C:\\FileGuardian\\processed\\quarantine",
    unknownRouting: "C:\\FileGuardian\\processed\\review",
    notifyOnFailure: true,
    recipients: [],
    createdAt: now,
    updatedAt: now,
  };
}

function newColumn(order: number): ProfileColumn {
  return {
    id: `col_${Date.now()}_${Math.random().toString(36).slice(2, 7)}`,
    name: "",
    order,
    constraints: { severity: "error" },
  };
}

export function ProfileEditor() {
  const navigate = useNavigate();
  const { id } = useParams();
  const isEditing = Boolean(id);

  // useMemo so the empty form doesn't get rebuilt on every render.
  const initialEmpty = useMemo(() => emptyProfile(), []);

  const [profile, setProfile] = useState<ValidationProfile>(initialEmpty);
  const [loading, setLoading] = useState(isEditing);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [mode, setMode] = useState<Mode>("manual");
  const [recipientDraft, setRecipientDraft] = useState("");
  const [aiSuggestedIds, setAiSuggestedIds] = useState<Set<string>>(new Set());
  const [enhanceWithAi, setEnhanceWithAi] = useState(false);
  const [inferring, setInferring] = useState(false);
  const [inferError, setInferError] = useState<string | null>(null);
  // The sample file uploaded to build a new profile. After saving, we also run
  // it through validation so it shows up in the dashboard like a dropped file.
  const [sampleFile, setSampleFile] = useState<File | null>(null);

  // When editing, fetch the profile from the API.
  useEffect(() => {
    if (!isEditing || !id) return;
    let cancelled = false;
    api
      .getProfile(id)
      .then((p) => !cancelled && setProfile(p))
      .catch((e: Error) => !cancelled && setLoadError(e.message))
      .finally(() => !cancelled && setLoading(false));
    return () => {
      cancelled = true;
    };
  }, [id, isEditing]);

  // ─── handlers ────────────────────────────────────────────────────────
  function patch<K extends keyof ValidationProfile>(
    key: K,
    value: ValidationProfile[K]
  ) {
    setProfile((p) => ({ ...p, [key]: value }));
  }

  function addColumn() {
    setProfile((p) => ({
      ...p,
      columns: [...p.columns, newColumn(p.columns.length)],
    }));
  }

  function updateColumn(next: ProfileColumn) {
    setProfile((p) => ({
      ...p,
      columns: p.columns.map((c) => (c.id === next.id ? next : c)),
    }));
  }

  function deleteColumn(colId: string) {
    setProfile((p) => ({
      ...p,
      columns: p.columns
        .filter((c) => c.id !== colId)
        .map((c, idx) => ({ ...c, order: idx })),
      // also drop any cross-column rules referencing the deleted column
      crossColumnRules: p.crossColumnRules.filter((r) => {
        const name = p.columns.find((c) => c.id === colId)?.name;
        return r.leftColumn !== name && r.rightColumn !== name;
      }),
    }));
    setAiSuggestedIds((s) => {
      const n = new Set(s);
      n.delete(colId);
      return n;
    });
  }

  function updateCrossRules(rules: CrossColumnRule[]) {
    setProfile((p) => ({ ...p, crossColumnRules: rules }));
  }

  function addRecipient() {
    const v = recipientDraft.trim();
    if (!v || profile.recipients.includes(v)) {
      setRecipientDraft("");
      return;
    }
    patch("recipients", [...profile.recipients, v]);
    setRecipientDraft("");
  }

  function removeRecipient(r: string) {
    patch(
      "recipients",
      profile.recipients.filter((x) => x !== r)
    );
  }

  /**
   * Upload a sample CSV and let the backend infer the columns.
   * Reads real headers + sample rows; with "Enhance with AI" on, it also asks
   * for suggested regex / allowed-values. The filename seeds the profile name
   * and file pattern.
   * Parameters: file (the chosen CSV File).
   * Returns: nothing (updates the form state).
   */
  async function handleSampleUpload(file: File) {
    setInferError(null);
    setInferring(true);
    try {
      const result = await api.inferFromSample(file, enhanceWithAi);
      setProfile((p) => ({
        ...p,
        filePattern: p.filePattern || file.name.replace(/[\d_-]+\..+$/, "_*.csv"),
        name: p.name || file.name.replace(/\.[^.]+$/, ""),
        columns: result.columns,
      }));
      setAiSuggestedIds(new Set(result.aiSuggestedColumns));
      // Remember the file so we can validate it after the profile is saved.
      setSampleFile(file);
    } catch (e) {
      setInferError((e as Error).message);
    } finally {
      setInferring(false);
    }
  }

  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);

  async function handleSave() {
    setSaving(true);
    setSaveError(null);
    try {
      const saved = isEditing && id
        ? await api.updateProfile(id, profile)
        : await api.createProfile(profile);
      // eslint-disable-next-line no-console
      console.log(isEditing ? "Updated profile:" : "Created profile:", saved);

      // For a brand-new profile created from a sample file, also validate that
      // file so it lands in the good/quarantine folder and shows in the
      // dashboard — exactly like a file dropped into the inbound folder.
      if (!isEditing && sampleFile && saved?.id) {
        try {
          await api.validateSample(saved.id, sampleFile);
          navigate("/");
          return;
        } catch (e) {
          // The profile saved fine; only the sample run failed. Don't block.
          // eslint-disable-next-line no-console
          console.warn("Sample validation failed:", e);
        }
      }
      navigate("/profiles");
    } catch (err) {
      setSaveError(err instanceof Error ? err.message : String(err));
    } finally {
      setSaving(false);
    }
  }

  const canSave =
    profile.name.trim().length > 0 &&
    profile.filePattern.trim().length > 0 &&
    profile.inboundFolder.trim().length > 0 &&
    profile.columns.length > 0 &&
    profile.columns.every((c) => c.name.trim().length > 0);

  return (
    <>
      <Topbar
        title={isEditing ? `Edit profile` : "New validation profile"}
        subtitle={
          isEditing
            ? `Editing ${profile.name || profile.id}`
            : "Define which file pattern to match and what 'good' looks like"
        }
        actions={
          <div className="hidden md:flex items-center gap-2">
            <Link
              to="/profiles"
              className="inline-flex items-center gap-1.5 rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50"
            >
              Cancel
            </Link>
            <button
              type="button"
              onClick={handleSave}
              disabled={!canSave || saving}
              className="inline-flex items-center gap-2 rounded-lg bg-brand-600 px-3.5 py-2 text-sm font-medium text-white hover:bg-brand-700 disabled:opacity-50 disabled:cursor-not-allowed"
            >
              <Save className="h-4 w-4" />
              {saving
                ? isEditing
                  ? "Updating…"
                  : "Saving…"
                : isEditing
                ? "Update profile"
                : "Save profile"}
            </button>
          </div>
        }
      />

      <main className="flex-1 px-6 py-6 max-w-5xl space-y-6">
        {/* Breadcrumb */}
        <div className="flex items-center gap-1 text-sm text-slate-500">
          <Link to="/profiles" className="hover:text-slate-900 inline-flex items-center gap-1">
            <ArrowLeft className="h-3.5 w-3.5" />
            Profiles
          </Link>
          <ChevronRight className="h-3.5 w-3.5" />
          <span className="text-slate-900">
            {isEditing ? "Edit" : "New"}
          </span>
        </div>

        {loading ? (
          <div className="rounded-xl border border-slate-200 bg-white p-12 text-center shadow-card">
            <p className="text-sm text-slate-500">Loading profile…</p>
          </div>
        ) : loadError ? (
          <div className="rounded-lg border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-800 flex items-start gap-2">
            <AlertCircle className="h-4 w-4 flex-shrink-0 mt-0.5" />
            <div>
              <div className="font-medium">Couldn't load profile</div>
              <div className="text-rose-700 mt-0.5">{loadError}</div>
            </div>
          </div>
        ) : (
        <>
        {/* Mode chooser (only shown when creating new) */}
        {!isEditing ? (
          <section className="rounded-xl border border-slate-200 bg-white p-1 shadow-card">
            <div className="grid grid-cols-2 gap-1">
              <ModeTab
                active={mode === "manual"}
                Icon={Pencil}
                title="Build manually"
                subtitle="Type column names + constraints"
                onClick={() => setMode("manual")}
              />
              <ModeTab
                active={mode === "upload"}
                Icon={Upload}
                title="Upload sample file"
                subtitle="Infer columns automatically"
                onClick={() => setMode("upload")}
              />
            </div>
          </section>
        ) : null}

        {/* Upload area */}
        {mode === "upload" && !isEditing ? (
          <div className="space-y-2">
            <UploadDropzone onFile={handleSampleUpload} disabled={inferring} />
            <div className="flex items-center justify-between px-1">
              <label className="inline-flex items-center gap-2 text-sm text-slate-700 cursor-pointer">
                <input
                  type="checkbox"
                  checked={enhanceWithAi}
                  onChange={(e) => setEnhanceWithAi(e.target.checked)}
                  className="h-4 w-4 rounded border-slate-300 text-brand-600 focus:ring-brand-500"
                />
                <Sparkles className="h-3.5 w-3.5 text-violet-500" />
                Enhance with AI
                <span className="text-xs text-slate-500">
                  (suggest regex &amp; allowed values — needs an Anthropic key)
                </span>
              </label>
              {inferring ? (
                <span className="text-xs text-slate-500">
                  Analysing sample…
                </span>
              ) : null}
            </div>
            {inferError ? (
              <p className="px-1 text-xs text-red-600">{inferError}</p>
            ) : null}
          </div>
        ) : null}

        {/* Basic metadata */}
        <FormCard
          title="Profile details"
          subtitle="High-level identification — admin will see these in the profiles list."
        >
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <Field label="Profile name" required>
              <input
                type="text"
                value={profile.name}
                onChange={(e) => patch("name", e.target.value)}
                placeholder="Invoice CSV Validation"
                className={inputClass}
              />
            </Field>
            <Field label="File pattern" required hint="Glob pattern matched against incoming filenames">
              <input
                type="text"
                value={profile.filePattern}
                onChange={(e) => patch("filePattern", e.target.value)}
                placeholder="invoices_*.csv"
                className={`${inputClass} font-mono`}
              />
            </Field>
            <Field
              label="File type"
              hint="Auto detects the format from each file's extension, so one profile can handle CSV, JSON and XML (use a pattern like orders_*)."
            >
              <select
                value={profile.autoDetectType ? "AUTO" : profile.fileType}
                onChange={(e) => {
                  const choice = e.target.value;
                  if (choice === "AUTO") {
                    patch("autoDetectType", true);
                  } else {
                    setProfile((p) => ({
                      ...p,
                      autoDetectType: false,
                      fileType: choice as ValidationProfile["fileType"],
                    }));
                  }
                }}
                className={inputClass}
              >
                <option value="AUTO">Auto (detect by extension)</option>
                <option value="CSV">CSV</option>
                <option value="JSON">JSON</option>
                <option value="XML">XML</option>
              </select>
            </Field>
            <Field label="Status">
              <div className="flex items-center gap-2 h-[38px]">
                <ToggleSwitch
                  checked={profile.active}
                  onChange={(v) => patch("active", v)}
                />
                <span className="text-sm text-slate-700">
                  {profile.active ? "Active (will validate)" : "Draft (ignored by monitor)"}
                </span>
              </div>
            </Field>
            <Field label="Description" className="md:col-span-2">
              <textarea
                value={profile.description}
                onChange={(e) => patch("description", e.target.value)}
                placeholder="What kind of file is this, who sends it, what's the purpose?"
                rows={2}
                className={inputClass}
              />
            </Field>
          </div>

          <div className="mt-3 flex items-center gap-2">
            <input
              id="allow-extra"
              type="checkbox"
              checked={profile.allowExtraColumns}
              onChange={(e) => patch("allowExtraColumns", e.target.checked)}
              className="h-4 w-4 rounded border-slate-300 text-brand-600 focus:ring-brand-500"
            />
            <label htmlFor="allow-extra" className="text-sm text-slate-700">
              Allow extra columns not declared below
              <span className="text-xs text-slate-500 ml-1.5">
                (off = unexpected columns cause an error)
              </span>
            </label>
          </div>
        </FormCard>

        {/* Columns */}
        <FormCard
          title={
            <span className="inline-flex items-center gap-2">
              <Columns3 className="h-4 w-4 text-slate-500" />
              Columns
            </span>
          }
          subtitle="Add one row per column the file should contain. Constraints on each column define what 'valid content' means."
          right={
            aiSuggestedIds.size > 0 ? (
              <span className="inline-flex items-center gap-1 rounded-full bg-gradient-to-r from-violet-500 to-fuchsia-600 px-2 py-0.5 text-[10px] font-medium text-white">
                <Sparkles className="h-2.5 w-2.5" />
                {aiSuggestedIds.size} AI-suggested
              </span>
            ) : null
          }
        >
          {profile.columns.length === 0 ? (
            <div className="rounded-lg border border-dashed border-slate-300 px-4 py-8 text-center">
              <Columns3 className="mx-auto h-6 w-6 text-slate-400" />
              <p className="mt-2 text-sm text-slate-600">
                No columns yet.
              </p>
              <p className="text-xs text-slate-500">
                {mode === "upload"
                  ? "Drop a sample file above to auto-populate, or click below to add manually."
                  : "Click below to add your first column."}
              </p>
            </div>
          ) : (
            <div className="space-y-2">
              {profile.columns.map((col) => (
                <ColumnConstraintRow
                  key={col.id}
                  column={col}
                  aiSuggested={aiSuggestedIds.has(col.id)}
                  onChange={updateColumn}
                  onDelete={() => deleteColumn(col.id)}
                />
              ))}
            </div>
          )}

          <div className="mt-3">
            <button
              type="button"
              onClick={addColumn}
              className="inline-flex items-center gap-1.5 rounded-lg border border-dashed border-slate-300 bg-white px-3 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50"
            >
              <Plus className="h-4 w-4" />
              Add column
            </button>
          </div>
        </FormCard>

        {/* Cross-column rules */}
        <FormCard
          title={
            <span className="inline-flex items-center gap-2">
              <GitCompareArrows className="h-4 w-4 text-slate-500" />
              Cross-column rules
            </span>
          }
          subtitle="Compare two columns row-by-row. Example: DueDate > InvoiceDate."
        >
          <CrossColumnRuleEditor
            rules={profile.crossColumnRules}
            columns={profile.columns}
            onChange={updateCrossRules}
          />
        </FormCard>

        {/* Folder paths — inbound + destinations */}
        <FormCard
          title={
            <span className="inline-flex items-center gap-2">
              <FolderInput className="h-4 w-4 text-slate-500" />
              Folder paths
            </span>
          }
          subtitle="Where files are picked up from, and where they go after validation."
        >
          {/* Visual flow indicator */}
          <FlowDiagram />

          {/* Inbound folder */}
          <div className="mb-5">
            <RoutingField
              label="Inbound folder"
              Icon={FolderInput}
              tone="info"
              value={profile.inboundFolder}
              onChange={(v) => patch("inboundFolder", v)}
              required
              placeholder="C:\FileGuardian\inbound\invoices"
              hint="The agent watches this folder for new files matching the file pattern above."
            />
          </div>

          <div className="border-t border-slate-100 pt-4">
            <h4 className="text-xs font-medium uppercase tracking-wider text-slate-500 mb-3">
              Destination folders
            </h4>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              <RoutingField
                label="On success"
                Icon={CheckCircle2}
                tone="success"
                value={profile.successRouting}
                onChange={(v) => patch("successRouting", v)}
              />
              <RoutingField
                label="On failure"
                Icon={XCircle}
                tone="danger"
                value={profile.failureRouting}
                onChange={(v) => patch("failureRouting", v)}
              />
              <RoutingField
                label="No match / unknown"
                Icon={FolderOutput}
                tone="info"
                value={profile.unknownRouting}
                onChange={(v) => patch("unknownRouting", v)}
              />
            </div>
          </div>
        </FormCard>

        {/* Notifications */}
        <FormCard
          title={
            <span className="inline-flex items-center gap-2">
              <Mail className="h-4 w-4 text-slate-500" />
              Notifications
            </span>
          }
          subtitle="Who to alert when this profile's files fail validation."
        >
          <div className="flex items-center gap-2 mb-4">
            <ToggleSwitch
              checked={profile.notifyOnFailure}
              onChange={(v) => patch("notifyOnFailure", v)}
            />
            <span className="text-sm text-slate-700">
              {profile.notifyOnFailure
                ? "Send a notification when a file fails"
                : "No notifications for this profile"}
            </span>
          </div>

          {profile.notifyOnFailure ? (
            <>
              <Field label="Recipients (email)">
                <div className="flex flex-wrap gap-1.5 mb-2">
                  {profile.recipients.map((r) => (
                    <span
                      key={r}
                      className="inline-flex items-center gap-1.5 rounded-full bg-slate-100 pl-3 pr-1.5 py-1 text-sm text-slate-700"
                    >
                      <Mail className="h-3 w-3 text-slate-400" />
                      {r}
                      <button
                        type="button"
                        onClick={() => removeRecipient(r)}
                        className="rounded-full p-0.5 hover:bg-slate-200"
                      >
                        <X className="h-3 w-3" />
                      </button>
                    </span>
                  ))}
                  {profile.recipients.length === 0 ? (
                    <span className="text-xs text-slate-400">
                      No recipients added — falls back to global default recipients.
                    </span>
                  ) : null}
                </div>
                <div className="flex gap-2">
                  <input
                    type="email"
                    value={recipientDraft}
                    onChange={(e) => setRecipientDraft(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === "Enter") {
                        e.preventDefault();
                        addRecipient();
                      }
                    }}
                    placeholder="name@company.com"
                    className={inputClass}
                  />
                  <button
                    type="button"
                    onClick={addRecipient}
                    className="inline-flex items-center gap-1.5 rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50"
                  >
                    <Plus className="h-4 w-4" />
                    Add
                  </button>
                </div>
              </Field>
              <p className="mt-3 text-xs text-slate-500 inline-flex items-center gap-1.5">
                <MessageSquare className="h-3.5 w-3.5" />
                Teams webhook is configured globally in Settings.
              </p>
            </>
          ) : null}
        </FormCard>

        {/* Bottom action bar */}
        <div className="flex items-center justify-between gap-3 pt-2">
          <div>
            {!canSave ? (
              <p className="text-xs text-amber-700 inline-flex items-center gap-1.5">
                <AlertCircle className="h-3.5 w-3.5" />
                Fill in name, file pattern, inbound folder, and at least one named column to enable save.
              </p>
            ) : (
              <p className="text-xs text-emerald-700 inline-flex items-center gap-1.5">
                <CheckCircle2 className="h-3.5 w-3.5" />
                Ready to save — {profile.columns.length} column{profile.columns.length === 1 ? "" : "s"}, {profile.crossColumnRules.length} cross-column rule{profile.crossColumnRules.length === 1 ? "" : "s"}.
              </p>
            )}
          </div>
          <div className="flex items-center gap-2">
            <Link
              to="/profiles"
              className="inline-flex items-center gap-1.5 rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50"
            >
              Cancel
            </Link>
            <button
              type="button"
              onClick={handleSave}
              disabled={!canSave || saving}
              className="inline-flex items-center gap-2 rounded-lg bg-brand-600 px-4 py-2 text-sm font-medium text-white hover:bg-brand-700 disabled:opacity-50 disabled:cursor-not-allowed"
            >
              <Save className="h-4 w-4" />
              {saving
                ? isEditing
                  ? "Updating…"
                  : "Saving…"
                : isEditing
                ? "Update profile"
                : "Save profile"}
            </button>
          </div>
        </div>

        {saveError ? (
          <div className="rounded-lg border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-800 flex items-start gap-2">
            <AlertCircle className="h-4 w-4 flex-shrink-0 mt-0.5" />
            <div>
              <div className="font-medium">Couldn't save profile</div>
              <div className="text-rose-700 mt-0.5">{saveError}</div>
              <div className="text-xs text-rose-600 mt-1">
                Is the Flask backend running on <code>http://127.0.0.1:6500</code>?
              </div>
            </div>
          </div>
        ) : null}
        </>
        )}
      </main>
    </>
  );
}

/* ─── shared sub-components ───────────────────────────────────────────── */

const inputClass =
  "block w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm text-slate-900 placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-brand-500 focus:border-transparent";

function FormCard({
  title,
  subtitle,
  children,
  right,
}: {
  title: React.ReactNode;
  subtitle?: string;
  children: React.ReactNode;
  right?: React.ReactNode;
}) {
  return (
    <section className="rounded-xl border border-slate-200 bg-white shadow-card overflow-hidden">
      <div className="px-5 py-4 border-b border-slate-200 flex items-center justify-between gap-3">
        <div>
          <h2 className="text-sm font-semibold text-slate-900">{title}</h2>
          {subtitle ? (
            <p className="text-xs text-slate-500 mt-0.5">{subtitle}</p>
          ) : null}
        </div>
        {right}
      </div>
      <div className="p-5">{children}</div>
    </section>
  );
}

function Field({
  label,
  required = false,
  hint,
  className = "",
  children,
}: {
  label: string;
  required?: boolean;
  hint?: string;
  className?: string;
  children: React.ReactNode;
}) {
  return (
    <div className={className}>
      <label className="block text-sm font-medium text-slate-700 mb-1">
        {label}
        {required ? <span className="text-rose-500 ml-0.5">*</span> : null}
      </label>
      {children}
      {hint ? <p className="mt-1 text-xs text-slate-500">{hint}</p> : null}
    </div>
  );
}

function ToggleSwitch({
  checked,
  onChange,
}: {
  checked: boolean;
  onChange: (v: boolean) => void;
}) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      onClick={() => onChange(!checked)}
      className={`relative inline-flex h-5 w-9 items-center rounded-full transition-colors ${
        checked ? "bg-brand-600" : "bg-slate-300"
      }`}
    >
      <span
        className={`inline-block h-3.5 w-3.5 transform rounded-full bg-white shadow transition-transform ${
          checked ? "translate-x-5" : "translate-x-1"
        }`}
      />
    </button>
  );
}

function ModeTab({
  active,
  Icon,
  title,
  subtitle,
  onClick,
}: {
  active: boolean;
  Icon: React.ComponentType<{ className?: string }>;
  title: string;
  subtitle: string;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`flex items-center gap-3 rounded-lg px-4 py-3 text-left transition-colors ${
        active
          ? "bg-brand-50 text-brand-900 ring-1 ring-brand-200"
          : "text-slate-700 hover:bg-slate-50"
      }`}
    >
      <div
        className={`flex h-9 w-9 items-center justify-center rounded-lg ${
          active ? "bg-brand-600 text-white" : "bg-slate-100 text-slate-600"
        }`}
      >
        <Icon className="h-4 w-4" />
      </div>
      <div>
        <div className="text-sm font-semibold">{title}</div>
        <div className="text-xs text-slate-500">{subtitle}</div>
      </div>
    </button>
  );
}

function UploadDropzone({
  onFile,
  disabled = false,
}: {
  onFile: (file: File) => void;
  disabled?: boolean;
}) {
  const [dragging, setDragging] = useState(false);
  return (
    <section
      onDragOver={(e) => {
        e.preventDefault();
        if (!disabled) setDragging(true);
      }}
      onDragLeave={() => setDragging(false)}
      onDrop={(e) => {
        e.preventDefault();
        setDragging(false);
        if (disabled) return;
        const f = e.dataTransfer.files?.[0];
        if (f) onFile(f);
      }}
      className={`rounded-xl border-2 border-dashed bg-white p-8 text-center transition-colors ${
        disabled
          ? "border-slate-200 opacity-60"
          : dragging
          ? "border-brand-500 bg-brand-50/40"
          : "border-slate-300 hover:border-slate-400"
      }`}
    >
      <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-full bg-brand-50 text-brand-700">
        <FileText className="h-6 w-6" />
      </div>
      <p className="mt-3 text-sm font-medium text-slate-900">
        {disabled
          ? "Reading your sample…"
          : "Drop a sample CSV here, or click to browse"}
      </p>
      <p className="mt-1 text-xs text-slate-500">
        We'll read the headers and a sample of rows to infer the columns.
      </p>
      <label
        className={`mt-4 inline-flex items-center gap-2 rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm font-medium text-slate-700 ${
          disabled ? "cursor-not-allowed opacity-60" : "hover:bg-slate-50 cursor-pointer"
        }`}
      >
        <Upload className="h-4 w-4" />
        Choose file…
        <input
          type="file"
          accept=".csv,text/csv"
          className="hidden"
          disabled={disabled}
          onChange={(e) => {
            const f = e.target.files?.[0];
            if (f) onFile(f);
          }}
        />
      </label>
    </section>
  );
}

function RoutingField({
  label,
  Icon,
  tone,
  value,
  onChange,
  required = false,
  placeholder,
  hint,
}: {
  label: string;
  Icon: React.ComponentType<{ className?: string }>;
  tone: "success" | "danger" | "info";
  value: string;
  onChange: (v: string) => void;
  required?: boolean;
  placeholder?: string;
  hint?: string;
}) {
  const tones = {
    success: "bg-emerald-50 text-emerald-600",
    danger: "bg-rose-50 text-rose-600",
    info: "bg-sky-50 text-sky-600",
  };
  return (
    <div>
      <label className="flex items-center gap-1.5 text-sm font-medium text-slate-700 mb-1.5">
        <span
          className={`inline-flex h-5 w-5 items-center justify-center rounded-md ${tones[tone]}`}
        >
          <Icon className="h-3 w-3" />
        </span>
        {label}
        {required ? <span className="text-rose-500 ml-0.5">*</span> : null}
      </label>
      <input
        type="text"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        className={`${inputClass} font-mono text-xs`}
      />
      {hint ? <p className="mt-1 text-xs text-slate-500">{hint}</p> : null}
    </div>
  );
}

function FlowDiagram() {
  return (
    <div className="mb-5 rounded-lg bg-slate-50 border border-slate-200 px-4 py-3">
      <div className="flex items-center justify-between gap-2 text-xs">
        <FlowNode Icon={FolderInput} label="Inbound" tone="info" />
        <ArrowRight className="h-4 w-4 text-slate-400 flex-shrink-0" />
        <FlowNode Icon={ShieldCheck} label="Validate" tone="brand" />
        <ArrowRight className="h-4 w-4 text-slate-400 flex-shrink-0" />
        <div className="flex flex-col items-center gap-1.5">
          <div className="flex items-center gap-2">
            <FlowNode Icon={CheckCircle2} label="Good" tone="success" small />
            <FlowNode Icon={XCircle} label="Quarantine" tone="danger" small />
            <FlowNode Icon={FolderOutput} label="Review" tone="info" small />
          </div>
        </div>
      </div>
    </div>
  );
}

function FlowNode({
  Icon,
  label,
  tone,
  small = false,
}: {
  Icon: React.ComponentType<{ className?: string }>;
  label: string;
  tone: "info" | "success" | "danger" | "brand";
  small?: boolean;
}) {
  const tones = {
    info: "bg-sky-100 text-sky-700",
    success: "bg-emerald-100 text-emerald-700",
    danger: "bg-rose-100 text-rose-700",
    brand: "bg-brand-100 text-brand-700",
  };
  return (
    <div className="flex items-center gap-1.5">
      <span
        className={`inline-flex items-center justify-center rounded-md ${tones[tone]} ${
          small ? "h-5 w-5" : "h-6 w-6"
        }`}
      >
        <Icon className={small ? "h-3 w-3" : "h-3.5 w-3.5"} />
      </span>
      <span
        className={`font-medium text-slate-700 ${small ? "text-[11px]" : ""}`}
      >
        {label}
      </span>
    </div>
  );
}
