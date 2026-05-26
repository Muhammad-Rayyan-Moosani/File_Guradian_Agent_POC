import type { RunStatus } from "../types";
import {
  CheckCircle2,
  XCircle,
  Loader2,
  AlertTriangle,
  HelpCircle,
} from "lucide-react";

const config: Record<
  RunStatus,
  { label: string; classes: string; Icon: React.ComponentType<{ className?: string }> }
> = {
  passed: {
    label: "Passed",
    classes: "bg-emerald-50 text-emerald-700 ring-emerald-200",
    Icon: CheckCircle2,
  },
  failed: {
    label: "Failed",
    classes: "bg-rose-50 text-rose-700 ring-rose-200",
    Icon: XCircle,
  },
  processing: {
    label: "Processing",
    classes: "bg-sky-50 text-sky-700 ring-sky-200",
    Icon: Loader2,
  },
  quarantined: {
    label: "Quarantined",
    classes: "bg-amber-50 text-amber-800 ring-amber-200",
    Icon: AlertTriangle,
  },
  review: {
    label: "Review",
    classes: "bg-violet-50 text-violet-700 ring-violet-200",
    Icon: HelpCircle,
  },
};

export function StatusBadge({
  status,
  size = "md",
}: {
  status: RunStatus;
  size?: "sm" | "md";
}) {
  const { label, classes, Icon } = config[status];
  const padding = size === "sm" ? "px-2 py-0.5 text-xs" : "px-2.5 py-1 text-xs";
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full font-medium ring-1 ring-inset ${classes} ${padding}`}
    >
      <Icon
        className={`h-3.5 w-3.5 ${
          status === "processing" ? "animate-spin" : ""
        }`}
      />
      {label}
    </span>
  );
}
