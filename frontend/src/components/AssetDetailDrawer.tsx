/**
 * Asset detail drawer.
 *
 * A right-side slide-over rather than a route: opening and closing it is
 * instant and does not lose the table's scroll position or filters -- which
 * matters when clicking through an action queue.
 */

import { useState } from "react";
import {
  Area,
  AreaChart,
  CartesianGrid,
  Line,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { AlertCard } from "./AlertCard";
import {
  AssetCode,
  EmptyState,
  ErrorState,
  FuelBar,
  HealthDot,
  RunningIndicator,
  Spinner,
  Stat,
  StatusChip,
  UtilizationBar,
} from "./ui";
import {
  formatDateTime,
  formatDue,
  minutesToHours,
  percent,
  productTypeLabel,
} from "../lib/format";
import { equipmentImage } from "../lib/equipment";
import { useAuth } from "../lib/auth";
import {
  useAlerts,
  useAsset,
  useAssetEvents,
  useAssetTelemetry,
  useAssignEmployee,
  useEmployees,
  useUnassignEmployee,
} from "../lib/queries";

type Tab = "overview" | "telemetry" | "alerts" | "events";

export function AssetDetailDrawer({
  assetId,
  onClose,
}: {
  assetId: number | null;
  onClose: () => void;
}) {
  const [tab, setTab] = useState<Tab>("overview");
  const { data: asset, isLoading, error, refetch } = useAsset(assetId);

  if (assetId === null) return null;

  return (
    <>
      <div
        className="fixed inset-0 bg-black/60 z-40 animate-fade-in"
        onClick={onClose}
        aria-hidden
      />
      <aside className="fixed right-0 top-0 bottom-0 w-full max-w-[620px] bg-surface border-l border-border z-50 flex flex-col animate-slide-in shadow-raised">
        {/* Header */}
        <div className="shrink-0 border-b border-border">
          {asset && (
            <div className="relative h-20 overflow-hidden bg-base">
              <img
                src={equipmentImage(asset.product_type, "card")}
                alt={productTypeLabel(asset.product_type)}
                className="w-full h-full object-cover opacity-60"
              />
              <div className="absolute inset-0 bg-gradient-to-t from-surface via-surface/50 to-surface/10" />
            </div>
          )}
          <div className="flex items-start justify-between gap-4 p-4 pb-3">
            <div className="min-w-0">
              {asset ? (
                <>
                  <div className="flex items-center gap-2.5 mb-1">
                    <AssetCode code={asset.asset_code} className="text-base" />
                    <StatusChip status={asset.status} />
                    {!asset.operator_match && (
                      <span className="chip bg-danger/15 text-danger border border-danger/30">
                        Operator mismatch
                      </span>
                    )}
                  </div>
                  <div className="text-xs text-muted">
                    {productTypeLabel(asset.product_type)}
                    {asset.model && ` · ${asset.model}`}
                    {asset.client_name && ` · ${asset.client_name}`}
                  </div>
                </>
              ) : (
                <div className="text-sm text-muted">Loading asset…</div>
              )}
            </div>
            <button onClick={onClose} className="btn-ghost px-1.5 shrink-0" aria-label="Close">
              <svg
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="2"
                strokeLinecap="round"
                className="w-4 h-4"
              >
                <path d="M18 6L6 18M6 6l12 12" />
              </svg>
            </button>
          </div>

          <nav className="flex gap-1 px-3">
            {(
              [
                ["overview", "Overview"],
                ["telemetry", "Telemetry"],
                ["alerts", `Alerts${asset?.alerts.length ? ` (${asset.alerts.length})` : ""}`],
                ["events", "History"],
              ] as [Tab, string][]
            ).map(([key, label]) => (
              <button
                key={key}
                onClick={() => setTab(key)}
                className={`px-3 py-2 text-xs font-medium border-b-2 transition-colors ${
                  tab === key
                    ? "border-accent text-accent"
                    : "border-transparent text-muted hover:text-ink"
                }`}
              >
                {label}
              </button>
            ))}
          </nav>
        </div>

        {/* Body */}
        <div className="flex-1 overflow-y-auto p-4">
          {isLoading && <Spinner label="Loading asset…" />}
          {error && <ErrorState error={error} onRetry={() => refetch()} />}
          {asset && !isLoading && (
            <>
              {tab === "overview" && <OverviewTab assetId={assetId} />}
              {tab === "telemetry" && <TelemetryTab assetId={assetId} />}
              {tab === "alerts" && <AlertsTab assetId={assetId} />}
              {tab === "events" && <EventsTab assetId={assetId} />}
            </>
          )}
        </div>
      </aside>
    </>
  );
}

// ---------------------------------------------------------------------------

function OverviewTab({ assetId }: { assetId: number }) {
  const { data: asset } = useAsset(assetId);
  if (!asset) return null;

  return (
    <div className="space-y-4">
      {/* Operator authorisation. Given its own panel because the assigned-vs-
          reported distinction is the single most important thing on this screen
          when it disagrees. */}
      <OperatorPanel assetId={assetId} />

      <div className="card p-3.5">
        <div className="text-2xs uppercase tracking-wider text-faint mb-3">Live state</div>
        <div className="grid grid-cols-3 gap-4">
          <Stat label="Engine" value={<RunningIndicator running={asset.is_running} />} />
          <Stat label="Fuel" value={<FuelBar level={asset.fuel_level} />} />
          <Stat label="Engine temp" value={`${asset.engine_temp_c.toFixed(0)}°C`} />
          <Stat
            label="Condition"
            value={
              <div className="flex gap-3">
                <HealthDot state={asset.tire_condition} label="Tire" />
                <HealthDot state={asset.engine_condition} label="Engine" />
              </div>
            }
            className="col-span-2"
          />
          <Stat label="Last seen" value={formatDateTime(asset.last_seen_at)} />
        </div>
      </div>

      <div className="card p-3.5">
        <div className="text-2xs uppercase tracking-wider text-faint mb-3">Utilization today</div>
        <div className="grid grid-cols-3 gap-4 mb-3">
          <Stat label="Runtime" value={minutesToHours(asset.runtime_minutes_today)} />
          <Stat label="Idle" value={minutesToHours(asset.idle_minutes_today)} />
          <Stat
            label="Continuous run"
            value={minutesToHours(asset.continuous_runtime_minutes)}
            hint={asset.continuous_runtime_minutes >= 360 ? "Past review threshold" : undefined}
          />
        </div>
        <UtilizationBar value={asset.utilization} />
        <div className="text-2xs text-faint mt-2">
          Lifetime: {minutesToHours(asset.runtime_minutes, 0)} runtime ·{" "}
          {percent(asset.lifetime_utilization)} utilization
        </div>
      </div>

      <div className="card p-3.5">
        <div className="text-2xs uppercase tracking-wider text-faint mb-3">Deployment</div>
        <div className="grid grid-cols-2 gap-4">
          <Stat label="Site" value={asset.site_name ?? <span className="text-danger">Not assigned</span>} />
          <Stat label="Client" value={asset.client_name ?? "—"} />
          <Stat
            label="Rental deadline"
            value={
              asset.expected_return_at ? (
                <span
                  className={
                    asset.hours_until_due !== null && asset.hours_until_due < 0
                      ? "text-danger"
                      : asset.hours_until_due !== null && asset.hours_until_due < 48
                        ? "text-warn"
                        : ""
                  }
                >
                  {formatDateTime(asset.expected_return_at)}
                </span>
              ) : (
                "—"
              )
            }
            hint={asset.hours_until_due !== null ? formatDue(asset.hours_until_due) : undefined}
          />
          <Stat label="Daily rate" value={`₹${asset.daily_rate.toLocaleString()}`} />
        </div>
      </div>

      <div className="card p-3.5">
        <div className="text-2xs uppercase tracking-wider text-faint mb-3">Identity</div>
        <div className="grid grid-cols-2 gap-4">
          <Stat label="Serial" value={asset.serial_number ?? "—"} />
          <Stat
            label="QR / RFID token"
            value={<span className="font-mono text-xs">{asset.qr_token}</span>}
            hint="Scannable at check-in / check-out"
          />
        </div>
      </div>
    </div>
  );
}

/** Assigned vs reported operator, with assign/unassign controls. */
function OperatorPanel({ assetId }: { assetId: number }) {
  const { data: asset } = useAsset(assetId);
  const { isClient } = useAuth();
  const { data: employees } = useEmployees(
    !isClient && asset?.current_client_id ? asset.current_client_id : undefined,
  );
  const assign = useAssignEmployee();
  const unassign = useUnassignEmployee();
  const [selected, setSelected] = useState<string>("");

  if (!asset) return null;

  const mismatch = !asset.operator_match;
  const canAssign = asset.current_client_id !== null;

  return (
    <div className={`card p-3.5 ${mismatch ? "border-danger/40" : ""}`}>
      <div className="text-2xs uppercase tracking-wider text-faint mb-3">Operator</div>

      <div className="grid grid-cols-2 gap-4 mb-3">
        <Stat
          label="Assigned (authorised)"
          value={
            asset.assigned_employee_code ? (
              <span>
                <span className="font-mono text-xs">{asset.assigned_employee_code}</span>
                <span className="text-muted"> — {asset.assigned_employee_name}</span>
              </span>
            ) : (
              <span className="text-warn">None assigned</span>
            )
          }
        />
        <Stat
          label="Reported by telemetry"
          value={
            asset.current_operator_code ? (
              <span className={mismatch ? "text-danger" : ""}>
                <span className="font-mono text-xs">{asset.current_operator_code}</span>
                <span className={mismatch ? "text-danger/80" : "text-muted"}>
                  {" "}
                  — {asset.current_operator_name}
                </span>
              </span>
            ) : (
              <span className="text-faint">Nobody in cab</span>
            )
          }
        />
      </div>

      {mismatch && (
        <div className="bg-danger/10 border border-danger/25 rounded-md p-2.5 mb-3">
          <p className="text-xs text-danger leading-relaxed">
            This machine is running under an operator who is not the registered one. Verify who is
            operating it, or update the assignment below.
          </p>
        </div>
      )}

      {canAssign && (
        <div className="flex items-center gap-2">
          <select
            value={selected}
            onChange={(e) => setSelected(e.target.value)}
            className="bg-base border border-border rounded-md px-2.5 py-1.5 text-xs text-ink flex-1"
          >
            <option value="">Select an operator…</option>
            {(employees ?? [])
              .filter((e) => e.active)
              .map((employee) => (
                <option key={employee.id} value={employee.id}>
                  {employee.employee_code} — {employee.name}
                </option>
              ))}
          </select>
          <button
            className="btn-primary text-xs py-1.5"
            disabled={!selected || assign.isPending}
            onClick={() =>
              assign.mutate(
                { assetId, employeeId: Number(selected) },
                { onSuccess: () => setSelected("") },
              )
            }
          >
            {assign.isPending ? "Assigning…" : "Assign"}
          </button>
          {asset.assigned_employee_id && (
            <button
              className="btn-secondary text-xs py-1.5"
              disabled={unassign.isPending}
              onClick={() => unassign.mutate(assetId)}
            >
              Clear
            </button>
          )}
        </div>
      )}

      {assign.error && (
        <p className="text-xs text-danger mt-2">{(assign.error as Error).message}</p>
      )}
    </div>
  );
}

function TelemetryTab({ assetId }: { assetId: number }) {
  const { data, isLoading, error, refetch } = useAssetTelemetry(assetId, 24);

  if (isLoading) return <Spinner label="Loading telemetry…" />;
  if (error) return <ErrorState error={error} onRetry={() => refetch()} />;
  if (!data || data.length === 0) {
    return (
      <EmptyState
        title="No telemetry in the last 24 hours"
        hint="Telemetry appears once the simulator has ticked for this asset."
      />
    );
  }

  const chartData = data.map((point) => ({
    time: new Date(point.timestamp).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
    fuel: Number(point.fuel_level.toFixed(1)),
    runtime: point.runtime_delta_minutes,
    temp: Number(point.engine_temp_c.toFixed(1)),
  }));

  const totalRuntime = data.reduce((sum, p) => sum + p.runtime_delta_minutes, 0);
  const totalIdle = data.reduce((sum, p) => sum + p.idle_delta_minutes, 0);

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-3 gap-3">
        <div className="card p-3">
          <Stat label="Readings (24h)" value={data.length} />
        </div>
        <div className="card p-3">
          <Stat label="Runtime (24h)" value={minutesToHours(totalRuntime)} />
        </div>
        <div className="card p-3">
          <Stat label="Idle (24h)" value={minutesToHours(totalIdle)} />
        </div>
      </div>

      <ChartCard title="Fuel level" subtitle="Falls while running; rises only on a refuel event">
        <AreaChart data={chartData}>
          <defs>
            <linearGradient id="fuelFill" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="#FFB020" stopOpacity={0.35} />
              <stop offset="100%" stopColor="#FFB020" stopOpacity={0} />
            </linearGradient>
          </defs>
          <CartesianGrid stroke="#242B38" strokeDasharray="3 3" vertical={false} />
          <XAxis dataKey="time" tick={{ fill: "#5C6678", fontSize: 10 }} interval="preserveStartEnd" minTickGap={40} />
          <YAxis tick={{ fill: "#5C6678", fontSize: 10 }} domain={[0, 100]} width={32} />
          <Tooltip content={<ChartTooltip unit="%" />} />
          <Area type="monotone" dataKey="fuel" stroke="#FFB020" strokeWidth={1.5} fill="url(#fuelFill)" />
        </AreaChart>
      </ChartCard>

      <ChartCard title="Engine temperature" subtitle="Rises under load, falls when parked">
        <AreaChart data={chartData}>
          <CartesianGrid stroke="#242B38" strokeDasharray="3 3" vertical={false} />
          <XAxis dataKey="time" tick={{ fill: "#5C6678", fontSize: 10 }} interval="preserveStartEnd" minTickGap={40} />
          <YAxis tick={{ fill: "#5C6678", fontSize: 10 }} width={32} />
          <Tooltip content={<ChartTooltip unit="°C" />} />
          <Line type="monotone" dataKey="temp" stroke="#3B82F6" strokeWidth={1.5} dot={false} />
        </AreaChart>
      </ChartCard>
    </div>
  );
}

function AlertsTab({ assetId }: { assetId: number }) {
  const { data: asset } = useAsset(assetId);
  const { data: allAlerts } = useAlerts();

  const alerts = (allAlerts ?? []).filter((a) => a.asset_id === assetId);

  if (!asset) return null;
  if (alerts.length === 0) {
    return <EmptyState title="No open alerts" hint="This asset is operating within normal parameters." />;
  }

  return (
    <div className="space-y-2.5">
      {alerts.map((alert) => (
        <AlertCard key={alert.id} alert={alert} />
      ))}
    </div>
  );
}

function EventsTab({ assetId }: { assetId: number }) {
  const { data, isLoading, error, refetch } = useAssetEvents(assetId);

  if (isLoading) return <Spinner label="Loading history…" />;
  if (error) return <ErrorState error={error} onRetry={() => refetch()} />;
  if (!data || data.length === 0) return <EmptyState title="No recorded events" />;

  return (
    <ol className="relative border-l border-border ml-2 space-y-4">
      {data.map((event) => (
        <li key={event.id} className="ml-4">
          <span className="absolute -left-[5px] w-2.5 h-2.5 rounded-full bg-elevated border-2 border-border" />
          <div className="flex items-center gap-2 flex-wrap">
            <span className="chip bg-elevated text-muted border border-border normal-case tracking-normal">
              {event.event_type.replace(/_/g, " ").toLowerCase()}
            </span>
            <span className="text-2xs text-faint">{formatDateTime(event.timestamp)}</span>
          </div>
          {event.description && (
            <p className="text-xs text-muted mt-1 leading-relaxed">{event.description}</p>
          )}
          {event.actor_name && <p className="text-2xs text-faint mt-0.5">by {event.actor_name}</p>}
        </li>
      ))}
    </ol>
  );
}

// ---------------------------------------------------------------------------

export function ChartCard({
  title,
  subtitle,
  children,
  height = 160,
}: {
  title: string;
  subtitle?: string;
  children: React.ReactElement;
  height?: number;
}) {
  return (
    <div className="card p-3.5">
      <div className="mb-3">
        <div className="text-xs font-medium text-ink">{title}</div>
        {subtitle && <div className="text-2xs text-faint mt-0.5">{subtitle}</div>}
      </div>
      <ResponsiveContainer width="100%" height={height}>
        {children}
      </ResponsiveContainer>
    </div>
  );
}

export function ChartTooltip({
  active,
  payload,
  label,
  unit = "",
}: {
  active?: boolean;
  payload?: { name: string; value: number; color: string }[];
  label?: string;
  unit?: string;
}) {
  if (!active || !payload?.length) return null;
  return (
    <div className="bg-elevated border border-border rounded-md px-2.5 py-1.5 shadow-raised">
      {label && <div className="text-2xs text-faint mb-1">{label}</div>}
      {payload.map((entry) => (
        <div key={entry.name} className="text-xs text-ink tnum flex items-center gap-2">
          <span className="w-1.5 h-1.5 rounded-full" style={{ background: entry.color }} />
          {entry.value}
          {unit}
        </div>
      ))}
    </div>
  );
}
