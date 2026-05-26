import { NavLink } from "react-router-dom";
import { LayoutDashboard, ShieldCheck, Settings, Shield } from "lucide-react";
import clsx from "clsx";

const links = [
  { to: "/", label: "Dashboard", Icon: LayoutDashboard, end: true },
  { to: "/profiles", label: "Validation Profiles", Icon: ShieldCheck },
  { to: "/settings", label: "Settings", Icon: Settings },
];

export function Sidebar() {
  return (
    <aside className="hidden md:flex md:w-64 md:flex-col md:border-r md:border-slate-200 md:bg-white">
      <div className="flex h-16 items-center gap-2.5 px-6 border-b border-slate-200">
        <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-gradient-to-br from-brand-600 to-brand-800 text-white shadow-card">
          <Shield className="h-5 w-5" />
        </div>
        <div className="leading-tight">
          <div className="text-sm font-semibold text-slate-900">
            File Guardian
          </div>
          <div className="text-xs text-slate-500">Agent POC</div>
        </div>
      </div>

      <nav className="flex-1 px-3 py-4 space-y-1">
        {links.map(({ to, label, Icon, end }) => (
          <NavLink
            key={to}
            to={to}
            end={end}
            className={({ isActive }) =>
              clsx(
                "flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition-colors",
                isActive
                  ? "bg-brand-50 text-brand-700"
                  : "text-slate-600 hover:bg-slate-50 hover:text-slate-900"
              )
            }
          >
            <Icon className="h-4 w-4" />
            {label}
          </NavLink>
        ))}
      </nav>

      <div className="p-4 border-t border-slate-200">
        <div className="rounded-lg bg-slate-50 px-3 py-2.5">
          <div className="flex items-center gap-2">
            <div className="h-2 w-2 rounded-full bg-emerald-500 ring-4 ring-emerald-100" />
            <span className="text-xs font-medium text-slate-700">
              Monitor running
            </span>
          </div>
          <div className="mt-1 text-[11px] text-slate-500">
            Watching inbound folder
          </div>
        </div>
      </div>
    </aside>
  );
}
