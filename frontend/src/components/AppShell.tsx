/**
 * Application shell: sidebar navigation, top bar, live status indicator.
 *
 * The sidebar is GROUPED rather than a flat list of nine links. A first-time
 * viewer opening the company side used to face nine equally-weighted nav items
 * with no idea which one was the front door; grouping them under Monitor /
 * Operate / Plan makes the product's shape legible before anything is clicked.
 */

import { NavLink, useNavigate } from "react-router-dom";
import type { ReactNode } from "react";
import { useAuth } from "../lib/auth";
import { useHealth, useSimulatorStatus } from "../lib/queries";
import { CatBadge, CatCorner } from "./Brand";

interface NavItem {
  to: string;
  label: string;
  icon: ReactNode;
  end?: boolean;
}

interface NavGroup {
  title: string;
  items: NavItem[];
}

// Inline SVGs rather than an icon package: 12 icons is not worth a dependency,
// and these inherit currentColor cleanly.
const icon = (path: ReactNode) => (
  <svg
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    strokeWidth="1.75"
    strokeLinecap="round"
    strokeLinejoin="round"
    className="w-[18px] h-[18px] shrink-0"
  >
    {path}
  </svg>
);

const ICONS = {
  tower: icon(<><path d="M3 3v18h18" /><path d="M7 15l4-5 3 3 5-7" /></>),
  map: icon(<><path d="M9 4L3 7v13l6-3 6 3 6-3V4l-6 3-6-3z" /><path d="M9 4v13M15 7v13" /></>),
  fleet: icon(<><rect x="2" y="7" width="14" height="10" rx="2" /><path d="M16 11h3l3 3v3h-6z" /><circle cx="6.5" cy="18.5" r="1.5" /><circle cx="17.5" cy="18.5" r="1.5" /></>),
  inventory: icon(<><path d="M3 7l9-4 9 4v10l-9 4-9-4z" /><path d="M3 7l9 4 9-4M12 11v10" /></>),
  rentals: icon(<><rect x="3" y="4" width="18" height="17" rx="2" /><path d="M8 2v4M16 2v4M3 10h18" /></>),
  scan: icon(<><path d="M3 8V5a2 2 0 012-2h3M16 3h3a2 2 0 012 2v3M21 16v3a2 2 0 01-2 2h-3M8 21H5a2 2 0 01-2-2v-3" /><path d="M3 12h18" /></>),
  clients: icon(<><path d="M17 21v-2a4 4 0 00-4-4H5a4 4 0 00-4 4v2" /><circle cx="9" cy="7" r="4" /><path d="M23 21v-2a4 4 0 00-3-3.87" /></>),
  alerts: icon(<><path d="M10.29 3.86L1.82 18a2 2 0 001.71 3h16.94a2 2 0 001.71-3L13.71 3.86a2 2 0 00-3.42 0z" /><path d="M12 9v4M12 17h.01" /></>),
  forecast: icon(<><path d="M3 17l6-6 4 4 8-8" /><path d="M17 7h4v4" /></>),
  overview: icon(<><rect x="3" y="3" width="7" height="9" rx="1" /><rect x="14" y="3" width="7" height="5" rx="1" /><rect x="14" y="12" width="7" height="9" rx="1" /><rect x="3" y="16" width="7" height="5" rx="1" /></>),
  employees: icon(<><path d="M16 21v-2a4 4 0 00-4-4H6a4 4 0 00-4 4v2" /><circle cx="9" cy="7" r="4" /><path d="M22 11l-3 3-2-2" /></>),
  bulb: icon(<><path d="M9 18h6M10 22h4" /><path d="M12 2a7 7 0 00-4 12.7V17h8v-2.3A7 7 0 0012 2z" /></>),
};

const COMPANY_NAV: NavGroup[] = [
  {
    title: "Monitor",
    items: [
      { to: "/company", label: "Control Tower", icon: ICONS.tower, end: true },
      { to: "/company/map", label: "Map & Sites", icon: ICONS.map },
      { to: "/company/alerts", label: "Alerts", icon: ICONS.alerts },
    ],
  },
  {
    title: "Operate",
    items: [
      { to: "/company/checkinout", label: "Check-In / Out", icon: ICONS.scan },
      { to: "/company/fleet", label: "Fleet", icon: ICONS.fleet },
      { to: "/company/inventory", label: "Inventory", icon: ICONS.inventory },
      { to: "/company/rentals", label: "Rentals", icon: ICONS.rentals },
    ],
  },
  {
    title: "Plan",
    items: [
      { to: "/company/clients", label: "Clients", icon: ICONS.clients },
      { to: "/company/forecasting", label: "Forecasting", icon: ICONS.forecast },
    ],
  },
];

const CLIENT_NAV: NavGroup[] = [
  {
    title: "My site",
    items: [
      { to: "/client", label: "Overview", icon: ICONS.overview, end: true },
      { to: "/client/assets", label: "My Equipment", icon: ICONS.fleet },
      { to: "/client/alerts", label: "Alerts", icon: ICONS.alerts },
    ],
  },
  {
    title: "Manage",
    items: [
      { to: "/client/employees", label: "Operators", icon: ICONS.employees },
      { to: "/client/recommendations", label: "Recommendations", icon: ICONS.bulb },
    ],
  },
];

export function AppShell({ children }: { children: ReactNode }) {
  const { user, isAdmin, logout } = useAuth();
  const navigate = useNavigate();
  const groups = isAdmin ? COMPANY_NAV : CLIENT_NAV;

  const handleLogout = () => {
    logout();
    navigate("/login", { replace: true });
  };

  return (
    <div className="flex h-full bg-base">
      {/* ---- Sidebar ---- */}
      <aside className="w-[236px] shrink-0 border-r border-border bg-surface flex flex-col">
        <div className="h-14 flex items-center gap-2.5 px-4 border-b border-border">
          <CatBadge height={20} />
          <div className="min-w-0 border-l border-border pl-2.5">
            <div className="text-[13px] font-semibold text-ink leading-tight">Smart Rental</div>
            <div className="text-2xs text-faint leading-tight">Fleet Intelligence</div>
          </div>
        </div>

        <nav className="flex-1 p-2 overflow-y-auto">
          {groups.map((group) => (
            <div key={group.title} className="mb-3 last:mb-0">
              <div className="label text-[9px] px-2.5 mb-1.5">{group.title}</div>
              <div className="space-y-0.5">
                {group.items.map((item) => (
                  <NavLink
                    key={item.to}
                    to={item.to}
                    end={item.end}
                    className={({ isActive }) =>
                      `relative flex items-center gap-2.5 px-2.5 py-2 rounded-lg text-sm transition-colors ${
                        isActive
                          ? "bg-accent/12 text-accent font-medium"
                          : "text-muted hover:text-ink hover:bg-elevated"
                      }`
                    }
                  >
                    {({ isActive }) => (
                      <>
                        {isActive && (
                          <span className="absolute left-0 top-1.5 bottom-1.5 w-[2px] rounded-full bg-accent" />
                        )}
                        {item.icon}
                        <span className="truncate">{item.label}</span>
                      </>
                    )}
                  </NavLink>
                ))}
              </div>
            </div>
          ))}
        </nav>

        {/* Tenant badge: makes it unmistakable whose data is on screen -- the
            point of Demo Scene 3. */}
        <div className="p-2 border-t border-border space-y-2">
          <div className="px-2.5 py-2 rounded-lg bg-elevated border border-border">
            <div className="label text-[9px] mb-1">
              {isAdmin ? "Rental Company" : "Client Account"}
            </div>
            <div className="text-xs font-medium text-ink truncate">
              {isAdmin ? "Fleet Operations" : (user?.client?.name ?? "—")}
            </div>
          </div>
          <CatCorner />
        </div>
      </aside>

      {/* ---- Main ---- */}
      <div className="flex-1 flex flex-col min-w-0">
        <TopBar onLogout={handleLogout} />
        <main className="flex-1 overflow-y-auto">{children}</main>
      </div>
    </div>
  );
}

function TopBar({ onLogout }: { onLogout: () => void }) {
  const { user, isAdmin } = useAuth();
  const { data: health } = useHealth();
  // Simulator status is admin-only; requesting it as a client would 403 on loop.
  const { data: sim } = useSimulatorStatus(isAdmin);

  const initials = (user?.full_name ?? "?")
    .split(" ")
    .map((part) => part[0])
    .slice(0, 2)
    .join("")
    .toUpperCase();

  const live = sim?.running || health?.simulator_running;

  return (
    <header className="h-14 shrink-0 border-b border-border bg-surface flex items-center justify-between px-5 gap-4">
      <div className="flex items-center gap-4 min-w-0">
        {/* Live telemetry indicator -- the visible proof the simulator is running. */}
        <div
          className={`flex items-center gap-2 rounded-full border px-2.5 py-1 ${
            live ? "border-ok/30 bg-ok/10" : "border-border bg-elevated"
          }`}
        >
          <span
            className={`w-1.5 h-1.5 rounded-full ${live ? "bg-ok animate-pulse-dot" : "bg-faint"}`}
          />
          <span className={`text-2xs font-medium ${live ? "text-ok" : "text-faint"}`}>
            {live ? "Live telemetry" : "Telemetry paused"}
          </span>
        </div>

        {sim?.running && (
          <span className="text-2xs text-faint tnum hidden md:inline">
            tick {sim.tick_count} · +{sim.simulated_minutes_per_tick}min every {sim.tick_seconds}s
          </span>
        )}
      </div>

      <div className="flex items-center gap-3">
        {health && !health.anomaly_model_loaded && (
          <span
            className="chip bg-warn/15 text-warn border border-warn/30"
            title="Run: python ml/train_anomaly_model.py"
          >
            Model missing
          </span>
        )}

        <div className="flex items-center gap-2.5">
          <div className="text-right hidden sm:block">
            <div className="text-xs font-medium text-ink leading-tight">{user?.full_name}</div>
            <div className="text-2xs text-faint leading-tight">
              {user?.role.replace("_", " ").toLowerCase()}
            </div>
          </div>
          <div className="w-8 h-8 rounded-lg bg-elevated border border-borderlight flex items-center justify-center text-2xs font-semibold text-muted">
            {initials}
          </div>
        </div>

        <button onClick={onLogout} className="btn-ghost px-2" title="Sign out">
          <svg
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="1.75"
            strokeLinecap="round"
            className="w-[18px] h-[18px]"
          >
            <path d="M9 21H5a2 2 0 01-2-2V5a2 2 0 012-2h4M16 17l5-5-5-5M21 12H9" />
          </svg>
        </button>
      </div>
    </header>
  );
}

export function PageHeader({
  title,
  subtitle,
  actions,
}: {
  title: string;
  subtitle?: string;
  actions?: ReactNode;
}) {
  return (
    <div className="flex items-start justify-between gap-4 mb-5">
      <div className="min-w-0">
        <h1 className="text-xl font-semibold text-ink tracking-tight">{title}</h1>
        {subtitle && <p className="text-sm text-muted mt-1">{subtitle}</p>}
      </div>
      {actions && <div className="flex items-center gap-2 shrink-0">{actions}</div>}
    </div>
  );
}
