import { Plus, Trash2, GitCompareArrows } from "lucide-react";
import type {
  CrossColumnOp,
  CrossColumnRule,
  ProfileColumn,
} from "../types";

const OPS: { value: CrossColumnOp; label: string }[] = [
  { value: "gt", label: "> (greater than)" },
  { value: "gte", label: "≥ (greater or equal)" },
  { value: "lt", label: "< (less than)" },
  { value: "lte", label: "≤ (less or equal)" },
  { value: "eq", label: "= (equal)" },
  { value: "neq", label: "≠ (not equal)" },
];

interface Props {
  rules: CrossColumnRule[];
  columns: ProfileColumn[];
  onChange: (next: CrossColumnRule[]) => void;
}

export function CrossColumnRuleEditor({ rules, columns, onChange }: Props) {
  function add() {
    const newRule: CrossColumnRule = {
      id: `ccr_${Date.now()}`,
      name: "New rule",
      leftColumn: columns[0]?.name ?? "",
      op: "gt",
      rightColumn: columns[1]?.name ?? columns[0]?.name ?? "",
      severity: "error",
    };
    onChange([...rules, newRule]);
  }

  function update(id: string, patch: Partial<CrossColumnRule>) {
    onChange(rules.map((r) => (r.id === id ? { ...r, ...patch } : r)));
  }

  function remove(id: string) {
    onChange(rules.filter((r) => r.id !== id));
  }

  return (
    <div className="space-y-3">
      {rules.length === 0 ? (
        <div className="rounded-lg border border-dashed border-slate-300 px-4 py-6 text-center">
          <GitCompareArrows className="mx-auto h-6 w-6 text-slate-400" />
          <p className="mt-2 text-sm text-slate-600">
            No cross-column rules yet.
          </p>
          <p className="text-xs text-slate-500">
            Add a rule like <code>DueDate &gt; InvoiceDate</code> to compare two
            columns row-by-row.
          </p>
        </div>
      ) : (
        rules.map((rule) => (
          <div
            key={rule.id}
            className="rounded-lg border border-slate-200 bg-white p-3 space-y-2"
          >
            <input
              type="text"
              value={rule.name}
              onChange={(e) => update(rule.id, { name: e.target.value })}
              placeholder="Rule name"
              className="block w-full rounded-md border border-slate-200 bg-white px-2.5 py-1.5 text-sm font-medium text-slate-900 focus:outline-none focus:ring-2 focus:ring-brand-500 focus:border-transparent"
            />
            <div className="flex flex-wrap items-center gap-2">
              <ColumnSelect
                value={rule.leftColumn}
                columns={columns}
                onChange={(v) => update(rule.id, { leftColumn: v })}
              />
              <select
                value={rule.op}
                onChange={(e) =>
                  update(rule.id, { op: e.target.value as CrossColumnOp })
                }
                className="rounded-md border border-slate-200 bg-white px-2.5 py-1.5 text-sm text-slate-900 focus:outline-none focus:ring-2 focus:ring-brand-500 focus:border-transparent"
              >
                {OPS.map((o) => (
                  <option key={o.value} value={o.value}>
                    {o.label}
                  </option>
                ))}
              </select>
              <ColumnSelect
                value={rule.rightColumn}
                columns={columns}
                onChange={(v) => update(rule.id, { rightColumn: v })}
              />
              <div className="flex-1" />
              <select
                value={rule.severity}
                onChange={(e) =>
                  update(rule.id, {
                    severity: e.target.value as "error" | "warning",
                  })
                }
                className={`rounded-md px-2 py-1 text-xs font-medium uppercase tracking-wider focus:outline-none focus:ring-2 focus:ring-brand-500 ${
                  rule.severity === "error"
                    ? "bg-rose-50 text-rose-700"
                    : "bg-amber-50 text-amber-700"
                }`}
              >
                <option value="error">error</option>
                <option value="warning">warning</option>
              </select>
              <button
                type="button"
                onClick={() => remove(rule.id)}
                className="rounded-md p-1.5 text-slate-400 hover:bg-rose-50 hover:text-rose-600"
                aria-label="Delete rule"
              >
                <Trash2 className="h-4 w-4" />
              </button>
            </div>
          </div>
        ))
      )}

      <button
        type="button"
        onClick={add}
        disabled={columns.length === 0}
        className="inline-flex items-center gap-1.5 rounded-lg border border-dashed border-slate-300 bg-white px-3 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50 disabled:opacity-50 disabled:cursor-not-allowed"
      >
        <Plus className="h-4 w-4" />
        Add cross-column rule
      </button>
      {columns.length === 0 ? (
        <p className="text-xs text-slate-500">
          Add at least one column above before creating cross-column rules.
        </p>
      ) : null}
    </div>
  );
}

function ColumnSelect({
  value,
  columns,
  onChange,
}: {
  value: string;
  columns: ProfileColumn[];
  onChange: (v: string) => void;
}) {
  return (
    <select
      value={value}
      onChange={(e) => onChange(e.target.value)}
      className="rounded-md border border-slate-200 bg-white px-2.5 py-1.5 text-sm font-mono text-slate-900 focus:outline-none focus:ring-2 focus:ring-brand-500 focus:border-transparent"
    >
      {columns.map((c) => (
        <option key={c.id} value={c.name}>
          {c.name}
        </option>
      ))}
    </select>
  );
}
