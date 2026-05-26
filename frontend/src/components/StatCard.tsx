import type { LucideIcon } from "lucide-react";
import clsx from "clsx";

export function StatCard({
  label,
  value,
  Icon,
  trend,
  tone = "neutral",
}: {
  label: string;
  value: string | number;
  Icon: LucideIcon;
  trend?: string;
  tone?: "neutral" | "success" | "danger" | "warning" | "info";
}) {
  const tones: Record<string, string> = {
    neutral: "bg-slate-50 text-slate-600",
    success: "bg-emerald-50 text-emerald-600",
    danger: "bg-rose-50 text-rose-600",
    warning: "bg-amber-50 text-amber-600",
    info: "bg-sky-50 text-sky-600",
  };
  return (
    <div className="rounded-xl border border-slate-200 bg-white p-5 shadow-card">
      <div className="flex items-center justify-between">
        <div className="text-sm text-slate-500">{label}</div>
        <div
          className={clsx(
            "flex h-9 w-9 items-center justify-center rounded-lg",
            tones[tone]
          )}
        >
          <Icon className="h-4 w-4" />
        </div>
      </div>
      <div className="mt-2 text-2xl font-semibold text-slate-900">{value}</div>
      {trend ? (
        <div className="mt-1 text-xs text-slate-500">{trend}</div>
      ) : null}
    </div>
  );
}
