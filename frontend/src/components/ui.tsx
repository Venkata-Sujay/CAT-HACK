/** Shared UI primitives. Small, unstyled-by-default building blocks. */

import type { ReactNode } from "react";
import {
  HEALTH_STYLES,
  SEVERITY_STYLES,
  STATUS_STYLES,
  alertTypeLabel,
  fuelColor,
} from "../lib/format";
import type { AlertSeverity, AssetStatus, HealthState } from "../lib/types";

export function Card({
  children,
  className = "",
  padded = true,
}: {
  children: ReactNode;
  className?: string;
  padded?: boolean;
}) {
  return <div className={`card ${padded ? "p-4" : ""} ${className}`}>{children}</div>;
}

export function SectionHeader({
  title,
  subtitle,
  action,
}: {
  title: string;
  subtitle?: string;
  action?: ReactNode;
}) {
  return (
    <div className="flex items-start justify-between gap-4 mb-3">
      <div className="min-w-0">
        <h2 className="text-sm font-semibold text-ink">{title}</h2>
        {subtitle && <p className="text-xs text-muted mt-0.5">{subtitle}</p>}
      </div>
      {action}
    </div>
  );
}

export function StatusChip({ status }: { status: AssetStatus }) {
  return <span className={`chip ${STATUS_STYLES[status] ?? STATUS_STYLES.UNKNOWN}`}>{status}</span>;
}

export function SeverityChip({ severity }: { severity: AlertSeverity }) {
  return <span className={`chip ${SEVERITY_STYLES[severity]}`}>{severity}</span>;
}

export function AlertTypeChip({ type }: { type: string }) {
  return (
    <span className="chip bg-elevated text-muted border border-border normal-case tracking-normal">
      {alertTypeLabel(type)}
    </span>
  );
}

export function HealthDot({ state, label }: { state: HealthState; label: string }) {
  const dot =
    state === "GOOD" ? "bg-ok" : state === "WARNING" ? "bg-warn" : "bg-danger animate-pulse-dot";
  return (
    <span className="inline-flex items-center gap-1.5" title={`${label}: ${state}`}>
      <span className={`w-1.5 h-1.5 rounded-full ${dot}`} />
      <span className={`text-xs ${HEALTH_STYLES[state]}`}>{label}</span>
    </span>
  );
}

/** Fuel gauge. Colour thresholds mirror the backend LOW_FUEL rule. */
export function FuelBar({ level, showLabel = true }: { level: number; showLabel?: boolean }) {
  return (
    <div className="flex items-center gap-2 min-w-[76px]">
      <div className="flex-1 h-1.5 bg-base rounded-full overflow-hidden border border-border/50">
        <div
          className={`h-full rounded-full transition-all duration-500 ${fuelColor(level)}`}
          style={{ width: `${Math.max(2, Math.min(100, level))}%` }}
        />
      </div>
      {showLabel && <span className="text-xs text-muted tnum w-8 text-right">{level.toFixed(0)}%</span>}
    </div>
  );
}

export function UtilizationBar({ value }: { value: number }) {
  const pct = Math.max(0, Math.min(1, value)) * 100;
  // >85% is the "at capacity" threshold that drives the request-more-assets
  // recommendation, so it is coloured as a warning rather than as success.
  const color = pct >= 85 ? "bg-warn" : pct >= 40 ? "bg-ok" : pct > 0 ? "bg-neutral" : "bg-border";
  return (
    <div className="flex items-center gap-2 min-w-[76px]">
      <div className="flex-1 h-1.5 bg-base rounded-full overflow-hidden border border-border/50">
        <div className={`h-full rounded-full transition-all duration-500 ${color}`} style={{ width: `${pct}%` }} />
      </div>
      <span className="text-xs text-muted tnum w-9 text-right">{pct.toFixed(0)}%</span>
    </div>
  );
}

export function RunningIndicator({ running }: { running: boolean }) {
  return (
    <span className="inline-flex items-center gap-1.5">
      <span className={`w-1.5 h-1.5 rounded-full ${running ? "bg-ok animate-pulse-dot" : "bg-faint"}`} />
      <span className={`text-xs ${running ? "text-ok" : "text-faint"}`}>
        {running ? "Running" : "Stopped"}
      </span>
    </span>
  );
}

export function AssetCode({ code, className = "" }: { code: string; className?: string }) {
  return <span className={`font-mono text-sm font-medium text-ink ${className}`}>{code}</span>;
}

export function Spinner({ label }: { label?: string }) {
  return (
    <div className="flex items-center justify-center gap-3 py-12 text-muted">
      <span className="w-4 h-4 border-2 border-border border-t-accent rounded-full animate-spin" />
      {label && <span className="text-sm">{label}</span>}
    </div>
  );
}

export function EmptyState({ title, hint, icon }: { title: string; hint?: string; icon?: ReactNode }) {
  return (
    <div className="flex flex-col items-center justify-center py-12 px-4 text-center">
      {icon && <div className="text-faint mb-3">{icon}</div>}
      <p className="text-sm text-muted font-medium">{title}</p>
      {hint && <p className="text-xs text-faint mt-1 max-w-sm">{hint}</p>}
    </div>
  );
}

export function ErrorState({ error, onRetry }: { error: unknown; onRetry?: () => void }) {
  const message = error instanceof Error ? error.message : "Something went wrong";
  return (
    <div className="flex flex-col items-center justify-center py-12 px-4 text-center">
      <div className="w-9 h-9 rounded-full bg-danger/15 border border-danger/30 flex items-center justify-center mb-3">
        <span className="text-danger text-lg leading-none">!</span>
      </div>
      <p className="text-sm text-ink font-medium">Could not load this view</p>
      <p className="text-xs text-muted mt-1 max-w-md">{message}</p>
      {onRetry && (
        <button className="btn-secondary mt-4" onClick={onRetry}>
          Try again
        </button>
      )}
    </div>
  );
}

/** Small labelled value, used throughout the asset drawer. */
export function Stat({
  label,
  value,
  hint,
  className = "",
}: {
  label: string;
  value: ReactNode;
  hint?: string;
  className?: string;
}) {
  return (
    <div className={className}>
      <div className="text-2xs uppercase tracking-wider text-faint mb-1">{label}</div>
      <div className="text-sm text-ink tnum">{value}</div>
      {hint && <div className="text-2xs text-faint mt-0.5">{hint}</div>}
    </div>
  );
}

export function Toggle({
  checked,
  onChange,
  label,
}: {
  checked: boolean;
  onChange: (next: boolean) => void;
  label: string;
}) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      onClick={() => onChange(!checked)}
      className="inline-flex items-center gap-2 text-sm text-muted hover:text-ink transition-colors"
    >
      <span
        className={`w-8 h-[18px] rounded-full transition-colors relative ${
          checked ? "bg-accent" : "bg-border"
        }`}
      >
        <span
          className={`absolute top-[2px] w-3.5 h-3.5 rounded-full bg-base transition-transform ${
            checked ? "translate-x-[16px]" : "translate-x-[2px]"
          }`}
        />
      </span>
      {label}
    </button>
  );
}
