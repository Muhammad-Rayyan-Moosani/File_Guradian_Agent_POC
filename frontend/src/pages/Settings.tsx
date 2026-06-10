import { useEffect, useState } from "react";
import {
  FolderCheck,
  FolderX,
  FolderSearch,
  Mail,
  MessageSquare,
  Save,
  X,
  Plus,
  Clock,
  Loader2,
  CheckCircle2,
  Sparkles,
  Plug,
} from "lucide-react";
import { Topbar } from "../components/Topbar";
import { api } from "../lib/api";
import type { AiStatus } from "../lib/api";
import type { AppSettings } from "../types";

const EMPTY_SETTINGS: AppSettings = {
  processedFolder: "",
  quarantineFolder: "",
  reviewFolder: "",
  pollIntervalSeconds: 5,
  notificationChannel: "email",
  smtpHost: "",
  smtpPort: 587,
  smtpFrom: "",
  teamsWebhookUrl: "",
  defaultRecipients: [],
  aiProvider: "off",
  aiModel: "",
  aiBaseUrl: "",
  vertexProject: "",
  vertexLocation: "",
};

export function Settings() {
  const [settings, setSettings] = useState<AppSettings>(EMPTY_SETTINGS);
  const [newRecipient, setNewRecipient] = useState("");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [aiStatus, setAiStatus] = useState<AiStatus | null>(null);
  const [testing, setTesting] = useState(false);
  const [testResult, setTestResult] = useState<{ ok: boolean; message: string } | null>(null);

  useEffect(() => {
    let cancelled = false;
    api
      .getSettings()
      .then((s) => !cancelled && setSettings(s))
      .catch((e: Error) => !cancelled && setError(e.message))
      .finally(() => !cancelled && setLoading(false));
    api
      .aiStatus()
      .then((s) => !cancelled && setAiStatus(s))
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, []);

  async function testAiConnection() {
    setTesting(true);
    setTestResult(null);
    try {
      // Test uses the saved settings, so save first if there are pending edits.
      await api.updateSettings(settings);
      const result = await api.aiTest();
      setTestResult(result);
      const fresh = await api.aiStatus();
      setAiStatus(fresh);
    } catch (e) {
      setTestResult({ ok: false, message: e instanceof Error ? e.message : String(e) });
    } finally {
      setTesting(false);
    }
  }

  function update<K extends keyof AppSettings>(key: K, value: AppSettings[K]) {
    setSettings((s) => ({ ...s, [key]: value }));
    setSaved(false);
  }

  async function handleSave() {
    setSaving(true);
    setError(null);
    setSaved(false);
    try {
      const updated = await api.updateSettings(settings);
      setSettings(updated);
      setSaved(true);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setSaving(false);
    }
  }

  function addRecipient() {
    if (!newRecipient.trim()) return;
    if (settings.defaultRecipients.includes(newRecipient.trim())) return;
    update("defaultRecipients", [
      ...settings.defaultRecipients,
      newRecipient.trim(),
    ]);
    setNewRecipient("");
  }

  function removeRecipient(r: string) {
    update(
      "defaultRecipients",
      settings.defaultRecipients.filter((x) => x !== r)
    );
  }

  return (
    <>
      <Topbar
        title="Settings"
        subtitle="Configure folder paths and notifications"
        actions={
          <button
            onClick={handleSave}
            disabled={saving || loading}
            className="hidden md:inline-flex items-center gap-2 rounded-lg bg-brand-600 px-3.5 py-2 text-sm font-medium text-white hover:bg-brand-700 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            <Save className="h-4 w-4" />
            {saving ? "Saving…" : "Save changes"}
          </button>
        }
      />

      <main className="flex-1 px-6 py-6 max-w-4xl space-y-6">
        {loading ? (
          <div className="rounded-xl border border-slate-200 bg-white p-12 text-center shadow-card">
            <Loader2 className="mx-auto h-6 w-6 animate-spin text-slate-400" />
            <p className="mt-2 text-sm text-slate-500">Loading settings…</p>
          </div>
        ) : (
        <>
        {/* Default destination folders */}
        <section className="rounded-xl border border-slate-200 bg-white shadow-card overflow-hidden">
          <div className="px-6 py-4 border-b border-slate-200">
            <h2 className="text-sm font-semibold text-slate-900">
              Default destination folders
            </h2>
            <p className="text-xs text-slate-500 mt-0.5">
              These defaults pre-fill into new validation profiles. Each profile
              has its own <strong>inbound folder</strong> — configured in the
              profile editor.
            </p>
          </div>
          <div className="p-6 space-y-5">
            <FolderField
              Icon={FolderCheck}
              tone="success"
              label="Good (processed) folder"
              description="Default destination for files that pass validation."
              value={settings.processedFolder}
              onChange={(v) => update("processedFolder", v)}
            />
            <FolderField
              Icon={FolderX}
              tone="danger"
              label="Quarantine folder"
              description="Default destination for files that fail validation."
              value={settings.quarantineFolder}
              onChange={(v) => update("quarantineFolder", v)}
            />
            <FolderField
              Icon={FolderSearch}
              tone="warning"
              label="Review folder"
              description="Default destination for files with no matching validation profile."
              value={settings.reviewFolder}
              onChange={(v) => update("reviewFolder", v)}
            />
          </div>
        </section>

        {/* Monitor */}
        <section className="rounded-xl border border-slate-200 bg-white shadow-card overflow-hidden">
          <div className="px-6 py-4 border-b border-slate-200">
            <h2 className="text-sm font-semibold text-slate-900">
              Monitor behavior
            </h2>
            <p className="text-xs text-slate-500 mt-0.5">
              How often the watcher polls for new files (only used if event
              watching is unavailable).
            </p>
          </div>
          <div className="p-6">
            <label className="block text-sm font-medium text-slate-700 mb-1.5">
              <span className="inline-flex items-center gap-1.5">
                <Clock className="h-4 w-4 text-slate-500" />
                Poll interval (seconds)
              </span>
            </label>
            <input
              type="number"
              min={1}
              max={60}
              value={settings.pollIntervalSeconds}
              onChange={(e) =>
                update("pollIntervalSeconds", Number(e.target.value))
              }
              className="block w-32 rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm text-slate-900 focus:outline-none focus:ring-2 focus:ring-brand-500 focus:border-transparent"
            />
          </div>
        </section>

        {/* AI provider */}
        <section className="rounded-xl border border-slate-200 bg-white shadow-card overflow-hidden">
          <div className="px-6 py-4 border-b border-slate-200">
            <h2 className="inline-flex items-center gap-2 text-sm font-semibold text-slate-900">
              <Sparkles className="h-4 w-4 text-violet-500" />
              AI provider
            </h2>
            <p className="text-xs text-slate-500 mt-0.5">
              Used to write plain-English failure summaries and to suggest
              constraints when you upload a sample. API keys are read from the{" "}
              <code className="font-mono">.env</code> file next to the app — they
              are never stored here.
            </p>
          </div>
          <div className="p-6 space-y-5">
            <div>
              <label className="block text-sm font-medium text-slate-700 mb-1.5">
                Provider
              </label>
              <select
                value={settings.aiProvider}
                onChange={(e) =>
                  update("aiProvider", e.target.value as AppSettings["aiProvider"])
                }
                className="block w-full sm:w-72 rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm text-slate-900 focus:outline-none focus:ring-2 focus:ring-brand-500 focus:border-transparent"
              >
                <option value="off">Off — use the built-in template (no AI)</option>
                <option value="anthropic">Anthropic (Claude)</option>
                <option value="openai">OpenAI</option>
                <option value="local">Local / self-hosted (OpenAI-compatible)</option>
                <option value="vertex">Google Vertex AI</option>
              </select>
            </div>

            {settings.aiProvider !== "off" ? (
              <>
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                  <TextField
                    label="Model"
                    value={settings.aiModel}
                    onChange={(v) => update("aiModel", v)}
                    placeholder="e.g. claude-haiku-4-5 / gpt-4o-mini"
                  />
                  {settings.aiProvider === "local" ||
                  settings.aiProvider === "vertex" ? (
                    <TextField
                      label="Base URL (OpenAI-compatible endpoint)"
                      value={settings.aiBaseUrl}
                      onChange={(v) => update("aiBaseUrl", v)}
                      placeholder="http://localhost:11434/v1"
                      mono
                    />
                  ) : null}
                </div>

                {settings.aiProvider === "vertex" ? (
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                    <TextField
                      label="GCP project"
                      value={settings.vertexProject}
                      onChange={(v) => update("vertexProject", v)}
                    />
                    <TextField
                      label="Region / location"
                      value={settings.vertexLocation}
                      onChange={(v) => update("vertexLocation", v)}
                      placeholder="us-central1"
                    />
                  </div>
                ) : null}

                <AiKeyHint provider={settings.aiProvider} aiStatus={aiStatus} />

                <div className="flex flex-wrap items-center gap-3 pt-1">
                  <button
                    type="button"
                    onClick={testAiConnection}
                    disabled={testing}
                    className="inline-flex items-center gap-2 rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50 disabled:opacity-50"
                  >
                    {testing ? (
                      <Loader2 className="h-4 w-4 animate-spin" />
                    ) : (
                      <Plug className="h-4 w-4" />
                    )}
                    {testing ? "Testing…" : "Save & test connection"}
                  </button>
                  {testResult ? (
                    <span
                      className={`text-sm ${
                        testResult.ok ? "text-emerald-700" : "text-rose-700"
                      }`}
                    >
                      {testResult.message}
                    </span>
                  ) : null}
                </div>
              </>
            ) : null}
          </div>
        </section>

        {/* Notifications */}
        <section className="rounded-xl border border-slate-200 bg-white shadow-card overflow-hidden">
          <div className="px-6 py-4 border-b border-slate-200">
            <h2 className="text-sm font-semibold text-slate-900">
              Notifications
            </h2>
            <p className="text-xs text-slate-500 mt-0.5">
              How the system alerts recipients when a file fails validation.
            </p>
          </div>
          <div className="p-6 space-y-6">
            <div>
              <label className="block text-sm font-medium text-slate-700 mb-2">
                Channel
              </label>
              <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                {(["email", "teams", "both"] as const).map((ch) => (
                  <button
                    key={ch}
                    onClick={() => update("notificationChannel", ch)}
                    className={`flex items-center gap-3 rounded-lg border px-4 py-3 text-left transition-all ${
                      settings.notificationChannel === ch
                        ? "border-brand-500 bg-brand-50 ring-2 ring-brand-100"
                        : "border-slate-200 bg-white hover:bg-slate-50"
                    }`}
                  >
                    {ch === "email" ? (
                      <Mail className="h-5 w-5 text-slate-700" />
                    ) : ch === "teams" ? (
                      <MessageSquare className="h-5 w-5 text-slate-700" />
                    ) : (
                      <div className="flex">
                        <Mail className="h-5 w-5 text-slate-700" />
                        <MessageSquare className="h-5 w-5 text-slate-700 -ml-1" />
                      </div>
                    )}
                    <div>
                      <div className="text-sm font-medium text-slate-900 capitalize">
                        {ch === "both" ? "Email + Teams" : ch}
                      </div>
                      <div className="text-xs text-slate-500">
                        {ch === "email"
                          ? "SMTP email alerts"
                          : ch === "teams"
                          ? "Microsoft Teams webhook"
                          : "Send to both channels"}
                      </div>
                    </div>
                  </button>
                ))}
              </div>
            </div>

            {(settings.notificationChannel === "email" ||
              settings.notificationChannel === "both") && (
              <div className="rounded-lg border border-slate-200 bg-slate-50/60 p-5 space-y-4">
                <h3 className="text-sm font-semibold text-slate-900">
                  SMTP configuration
                </h3>
                <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
                  <TextField
                    label="SMTP host"
                    value={settings.smtpHost}
                    onChange={(v) => update("smtpHost", v)}
                  />
                  <div>
                    <label className="block text-xs font-medium text-slate-600 mb-1">
                      Port
                    </label>
                    <input
                      type="number"
                      value={settings.smtpPort}
                      onChange={(e) =>
                        update("smtpPort", Number(e.target.value))
                      }
                      className="block w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm text-slate-900 focus:outline-none focus:ring-2 focus:ring-brand-500 focus:border-transparent"
                    />
                  </div>
                  <TextField
                    label="From address"
                    value={settings.smtpFrom}
                    onChange={(v) => update("smtpFrom", v)}
                  />
                </div>
              </div>
            )}

            {(settings.notificationChannel === "teams" ||
              settings.notificationChannel === "both") && (
              <div className="rounded-lg border border-slate-200 bg-slate-50/60 p-5">
                <TextField
                  label="Microsoft Teams webhook URL"
                  value={settings.teamsWebhookUrl}
                  onChange={(v) => update("teamsWebhookUrl", v)}
                  placeholder="https://outlook.office.com/webhook/…"
                  mono
                />
              </div>
            )}

            <div>
              <label className="block text-sm font-medium text-slate-700 mb-2">
                Default recipients
              </label>
              <p className="text-xs text-slate-500 mb-3">
                Recipients added here will receive alerts for every profile
                unless overridden.
              </p>
              <div className="flex flex-wrap gap-2 mb-3">
                {settings.defaultRecipients.map((r) => (
                  <span
                    key={r}
                    className="inline-flex items-center gap-1.5 rounded-full bg-slate-100 pl-3 pr-1.5 py-1 text-sm text-slate-700"
                  >
                    {r}
                    <button
                      onClick={() => removeRecipient(r)}
                      className="rounded-full p-0.5 hover:bg-slate-200"
                    >
                      <X className="h-3 w-3" />
                    </button>
                  </span>
                ))}
              </div>
              <div className="flex gap-2">
                <input
                  type="email"
                  value={newRecipient}
                  onChange={(e) => setNewRecipient(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter") {
                      e.preventDefault();
                      addRecipient();
                    }
                  }}
                  placeholder="name@company.com"
                  className="flex-1 rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm text-slate-900 focus:outline-none focus:ring-2 focus:ring-brand-500 focus:border-transparent"
                />
                <button
                  onClick={addRecipient}
                  className="inline-flex items-center gap-1.5 rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50"
                >
                  <Plus className="h-4 w-4" />
                  Add
                </button>
              </div>
            </div>
          </div>
        </section>

        <div className="flex items-center justify-end gap-3">
          {error ? (
            <span className="text-sm text-rose-700">{error}</span>
          ) : null}
          {saved ? (
            <span className="inline-flex items-center gap-1.5 text-sm text-emerald-700">
              <CheckCircle2 className="h-4 w-4" />
              Saved
            </span>
          ) : null}
          <button
            onClick={handleSave}
            disabled={saving}
            className="inline-flex items-center gap-2 rounded-lg bg-brand-600 px-4 py-2.5 text-sm font-medium text-white hover:bg-brand-700 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            <Save className="h-4 w-4" />
            {saving ? "Saving…" : "Save changes"}
          </button>
        </div>
        </>
        )}
      </main>
    </>
  );
}

function FolderField({
  Icon,
  tone,
  label,
  description,
  value,
  onChange,
}: {
  Icon: React.ComponentType<{ className?: string }>;
  tone: "info" | "success" | "danger" | "warning";
  label: string;
  description: string;
  value: string;
  onChange: (v: string) => void;
}) {
  const tones = {
    info: "bg-sky-50 text-sky-600",
    success: "bg-emerald-50 text-emerald-600",
    danger: "bg-rose-50 text-rose-600",
    warning: "bg-amber-50 text-amber-600",
  };
  return (
    <div className="flex items-start gap-4">
      <div
        className={`flex h-10 w-10 items-center justify-center rounded-lg flex-shrink-0 ${tones[tone]}`}
      >
        <Icon className="h-5 w-5" />
      </div>
      <div className="flex-1 min-w-0">
        <label className="block text-sm font-medium text-slate-900">
          {label}
        </label>
        <p className="text-xs text-slate-500 mb-2">{description}</p>
        <input
          type="text"
          value={value}
          onChange={(e) => onChange(e.target.value)}
          className="block w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm font-mono text-slate-900 focus:outline-none focus:ring-2 focus:ring-brand-500 focus:border-transparent"
        />
      </div>
    </div>
  );
}

function TextField({
  label,
  value,
  onChange,
  placeholder,
  mono = false,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  placeholder?: string;
  mono?: boolean;
}) {
  return (
    <div>
      <label className="block text-xs font-medium text-slate-600 mb-1">
        {label}
      </label>
      <input
        type="text"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        className={`block w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm text-slate-900 focus:outline-none focus:ring-2 focus:ring-brand-500 focus:border-transparent ${
          mono ? "font-mono text-xs" : ""
        }`}
      />
    </div>
  );
}

function AiKeyHint({
  provider,
  aiStatus,
}: {
  provider: AppSettings["aiProvider"];
  aiStatus: AiStatus | null;
}) {
  if (provider === "local") {
    return (
      <p className="text-xs text-slate-500">
        No API key needed for a local server — just set the Base URL above (e.g.
        Ollama or LM Studio).
      </p>
    );
  }

  const keyNames: Record<string, string> = {
    anthropic: "ANTHROPIC_API_KEY",
    openai: "OPENAI_API_KEY",
    vertex: "VERTEX_ACCESS_TOKEN",
  };
  const keyName = keyNames[provider];
  const present = aiStatus
    ? aiStatus.keysPresent[provider as "anthropic" | "openai" | "vertex"]
    : false;

  return (
    <p className="text-xs">
      <span className="text-slate-500">API key </span>
      <code className="font-mono">{keyName}</code>
      {present ? (
        <span className="ml-1 text-emerald-700">— detected in .env ✓</span>
      ) : (
        <span className="ml-1 text-rose-700">
          — not found. Add it to the .env next to the app, then restart.
        </span>
      )}
    </p>
  );
}
