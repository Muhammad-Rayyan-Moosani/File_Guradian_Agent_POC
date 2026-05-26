import { useState } from "react";
import {
  ChevronDown,
  ChevronRight,
  GripVertical,
  Trash2,
  X,
  Sparkles,
} from "lucide-react";
import type {
  ColumnConstraints,
  ColumnType,
  ProfileColumn,
} from "../types";

const COLUMN_TYPES: ColumnType[] = [
  "string",
  "integer",
  "decimal",
  "date",
  "datetime",
  "email",
  "boolean",
];

interface Props {
  column: ProfileColumn;
  aiSuggested?: boolean;
  onChange: (next: ProfileColumn) => void;
  onDelete: () => void;
}

export function ColumnConstraintRow({
  column,
  aiSuggested = false,
  onChange,
  onDelete,
}: Props) {
  const [expanded, setExpanded] = useState(false);
  const c = column.constraints;

  function updateConstraints(patch: Partial<ColumnConstraints>) {
    onChange({
      ...column,
      constraints: { ...column.constraints, ...patch },
    });
  }

  return (
    <div
      className={`rounded-lg border bg-white transition-colors ${
        expanded
          ? "border-brand-300 ring-1 ring-brand-100"
          : "border-slate-200 hover:border-slate-300"
      }`}
    >
      {/* Main row */}
      <div className="flex items-center gap-3 px-3 py-2.5">
        <GripVertical className="h-4 w-4 text-slate-300 flex-shrink-0 cursor-grab" />

        <input
          type="text"
          value={column.name}
          onChange={(e) => onChange({ ...column, name: e.target.value })}
          placeholder="Column name"
          className="w-48 rounded-md border border-slate-200 bg-white px-2.5 py-1.5 text-sm font-mono text-slate-900 focus:outline-none focus:ring-2 focus:ring-brand-500 focus:border-transparent"
        />

        <select
          value={c.type ?? ""}
          onChange={(e) =>
            updateConstraints({
              type: (e.target.value || undefined) as ColumnType | undefined,
            })
          }
          className="rounded-md border border-slate-200 bg-white px-2.5 py-1.5 text-sm text-slate-900 focus:outline-none focus:ring-2 focus:ring-brand-500 focus:border-transparent"
        >
          <option value="">— type —</option>
          {COLUMN_TYPES.map((t) => (
            <option key={t} value={t}>
              {t}
            </option>
          ))}
        </select>

        <ToggleChip
          label="Required"
          active={!!c.required}
          onClick={() => updateConstraints({ required: !c.required })}
        />
        <ToggleChip
          label="Unique"
          active={!!c.unique}
          onClick={() => updateConstraints({ unique: !c.unique })}
        />

        <div className="flex-1" />

        <select
          value={c.severity}
          onChange={(e) =>
            updateConstraints({
              severity: e.target.value as "error" | "warning",
            })
          }
          className={`rounded-md px-2 py-1 text-xs font-medium uppercase tracking-wider focus:outline-none focus:ring-2 focus:ring-brand-500 ${
            c.severity === "error"
              ? "bg-rose-50 text-rose-700"
              : "bg-amber-50 text-amber-700"
          }`}
        >
          <option value="error">error</option>
          <option value="warning">warning</option>
        </select>

        {aiSuggested ? (
          <span
            title="AI-suggested constraints — review before saving"
            className="inline-flex items-center gap-1 rounded-full bg-gradient-to-r from-violet-500 to-fuchsia-600 px-2 py-0.5 text-[10px] font-medium text-white"
          >
            <Sparkles className="h-2.5 w-2.5" />
            AI
          </span>
        ) : null}

        <button
          type="button"
          onClick={() => setExpanded((v) => !v)}
          className="inline-flex items-center gap-1 rounded-md px-2 py-1 text-xs text-slate-600 hover:bg-slate-100"
        >
          {expanded ? (
            <ChevronDown className="h-3.5 w-3.5" />
          ) : (
            <ChevronRight className="h-3.5 w-3.5" />
          )}
          Advanced
        </button>

        <button
          type="button"
          onClick={onDelete}
          className="rounded-md p-1.5 text-slate-400 hover:bg-rose-50 hover:text-rose-600"
          aria-label="Delete column"
        >
          <Trash2 className="h-4 w-4" />
        </button>
      </div>

      {/* Advanced section */}
      {expanded ? (
        <div className="border-t border-slate-100 px-3 py-3 bg-slate-50/40">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            {/* Description */}
            <div className="md:col-span-2">
              <Label>Description (optional)</Label>
              <input
                type="text"
                value={column.description ?? ""}
                onChange={(e) =>
                  onChange({ ...column, description: e.target.value })
                }
                placeholder="What does this column represent?"
                className="block w-full rounded-md border border-slate-200 bg-white px-2.5 py-1.5 text-sm text-slate-900 focus:outline-none focus:ring-2 focus:ring-brand-500 focus:border-transparent"
              />
            </div>

            {/* Min */}
            <div>
              <Label>Min</Label>
              <input
                type="text"
                value={c.min ?? ""}
                onChange={(e) =>
                  updateConstraints({
                    min: e.target.value === "" ? undefined : e.target.value,
                  })
                }
                placeholder={
                  c.type === "date" || c.type === "datetime"
                    ? "2025-01-01"
                    : "e.g. 0.01"
                }
                className="block w-full rounded-md border border-slate-200 bg-white px-2.5 py-1.5 text-sm font-mono text-slate-900 focus:outline-none focus:ring-2 focus:ring-brand-500 focus:border-transparent"
              />
            </div>

            {/* Max */}
            <div>
              <Label>Max</Label>
              <input
                type="text"
                value={c.max ?? ""}
                onChange={(e) =>
                  updateConstraints({
                    max: e.target.value === "" ? undefined : e.target.value,
                  })
                }
                placeholder={
                  c.type === "date" || c.type === "datetime"
                    ? "2099-12-31"
                    : "e.g. 1000000"
                }
                className="block w-full rounded-md border border-slate-200 bg-white px-2.5 py-1.5 text-sm font-mono text-slate-900 focus:outline-none focus:ring-2 focus:ring-brand-500 focus:border-transparent"
              />
            </div>

            {/* Regex */}
            <div className="md:col-span-2">
              <Label>Regex pattern</Label>
              <input
                type="text"
                value={c.regex ?? ""}
                onChange={(e) =>
                  updateConstraints({
                    regex: e.target.value === "" ? undefined : e.target.value,
                  })
                }
                placeholder="^INV-\\d{6}$"
                className="block w-full rounded-md border border-slate-200 bg-white px-2.5 py-1.5 text-sm font-mono text-slate-900 focus:outline-none focus:ring-2 focus:ring-brand-500 focus:border-transparent"
              />
            </div>

            {/* Allowed values */}
            <div className="md:col-span-2">
              <Label>Allowed values (enum)</Label>
              <AllowedValuesInput
                values={c.allowedValues ?? []}
                onChange={(next) =>
                  updateConstraints({
                    allowedValues: next.length === 0 ? undefined : next,
                  })
                }
              />
            </div>
          </div>

          {/* Hint for present-only */}
          {!c.type &&
          !c.required &&
          !c.unique &&
          c.min === undefined &&
          c.max === undefined &&
          !c.regex &&
          (!c.allowedValues || c.allowedValues.length === 0) ? (
            <p className="mt-3 text-xs text-violet-700 bg-violet-50 rounded-md px-2.5 py-1.5">
              No constraints set — this column is{" "}
              <strong>present-only</strong>. The validator will only check that
              the header exists; content is not inspected.
            </p>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}

function Label({ children }: { children: React.ReactNode }) {
  return (
    <label className="block text-[11px] font-medium uppercase tracking-wider text-slate-500 mb-1">
      {children}
    </label>
  );
}

function ToggleChip({
  label,
  active,
  onClick,
}: {
  label: string;
  active: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`inline-flex items-center gap-1 rounded-full px-2.5 py-1 text-xs font-medium transition-colors ${
        active
          ? "bg-emerald-50 text-emerald-700 ring-1 ring-inset ring-emerald-200"
          : "bg-slate-100 text-slate-500 hover:bg-slate-200"
      }`}
    >
      <span
        className={`h-1.5 w-1.5 rounded-full ${
          active ? "bg-emerald-500" : "bg-slate-400"
        }`}
      />
      {label}
    </button>
  );
}

function AllowedValuesInput({
  values,
  onChange,
}: {
  values: string[];
  onChange: (next: string[]) => void;
}) {
  const [draft, setDraft] = useState("");
  function add() {
    const v = draft.trim();
    if (!v) return;
    if (values.includes(v)) {
      setDraft("");
      return;
    }
    onChange([...values, v]);
    setDraft("");
  }
  function remove(v: string) {
    onChange(values.filter((x) => x !== v));
  }
  return (
    <div>
      <div className="flex flex-wrap gap-1.5 mb-2">
        {values.map((v) => (
          <span
            key={v}
            className="inline-flex items-center gap-1 rounded-md bg-slate-200/70 pl-2 pr-1 py-0.5 text-xs font-mono text-slate-700"
          >
            {v}
            <button
              type="button"
              onClick={() => remove(v)}
              className="rounded-full p-0.5 hover:bg-slate-300/60"
            >
              <X className="h-3 w-3" />
            </button>
          </span>
        ))}
        {values.length === 0 ? (
          <span className="text-xs text-slate-400">No allowed values set.</span>
        ) : null}
      </div>
      <input
        type="text"
        value={draft}
        onChange={(e) => setDraft(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter" || e.key === ",") {
            e.preventDefault();
            add();
          }
        }}
        onBlur={add}
        placeholder="Type a value and press Enter…"
        className="block w-full rounded-md border border-slate-200 bg-white px-2.5 py-1.5 text-sm text-slate-900 focus:outline-none focus:ring-2 focus:ring-brand-500 focus:border-transparent"
      />
    </div>
  );
}
