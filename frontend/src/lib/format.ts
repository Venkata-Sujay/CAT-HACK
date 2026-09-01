/** Display formatters. Kept in one place so units read consistently. */

import type { AlertSeverity, AssetStatus, HealthState, ProductType } from "./types";

export function minutesToHours(minutes: number, digits = 1): string {
  return `${(minutes / 60).toFixed(digits)}h`;
}

export function percent(value: number, digits = 0): string {
  return `${(value * 100).toFixed(digits)}%`;
}

export function productTypeLabel(type: ProductType | string): string {
  return type
    .split("_")
    .map((word) => word.charAt(0) + word.slice(1).toLowerCase())
    .join(" ");
}

export function alertTypeLabel(type: string): string {
  return type
    .split("_")
    .map((word) => word.charAt(0) + word.slice(1).toLowerCase())
    .join(" ");
}

/** "in 3d 4h" / "5h overdue" -- relative deadlines read faster than timestamps. */
export function formatDue(hours: number | null): string {
  if (hours === null || hours === undefined) return "—";
  const overdue = hours < 0;
  const abs = Math.abs(hours);
  const days = Math.floor(abs / 24);
  const remainder = Math.floor(abs % 24);

  const text = days > 0 ? `${days}d ${remainder}h` : `${remainder}h`;
  return overdue ? `${text} overdue` : `in ${text}`;
}

export function formatDateTime(iso: string | null): string {
  if (!iso) return "—";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "—";
  return date.toLocaleString(undefined, {
    day: "2-digit",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function formatDate(iso: string | null): string {
  if (!iso) return "—";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "—";
  return date.toLocaleDateString(undefined, { day: "2-digit", month: "short", year: "numeric" });
}

/** "just now" / "4m ago" -- for last-seen freshness. */
export function timeAgo(iso: string | null): string {
  if (!iso) return "never";
  const then = new Date(iso).getTime();
  if (Number.isNaN(then)) return "never";

  const seconds = Math.max(0, Math.floor((Date.now() - then) / 1000));
  if (seconds < 45) return "just now";
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m ago`;
  if (seconds < 86400) return `${Math.floor(seconds / 3600)}h ago`;
  return `${Math.floor(seconds / 86400)}d ago`;
}

// ---------------------------------------------------------------------------
// Status -> colour. Centralised so a status never renders two different colours
// in two different components.
// ---------------------------------------------------------------------------

export const STATUS_STYLES: Record<AssetStatus, string> = {
  ACTIVE: "bg-ok/15 text-ok border border-ok/25",
  IDLE: "bg-neutral/15 text-neutral border border-neutral/30",
  RENTED: "bg-info/15 text-info border border-info/25",
  AVAILABLE: "bg-elevated text-muted border border-border",
  OVERDUE: "bg-danger/15 text-danger border border-danger/30",
  MAINTENANCE: "bg-warn/15 text-warn border border-warn/25",
  UNKNOWN: "bg-elevated text-faint border border-border",
};

export const SEVERITY_STYLES: Record<AlertSeverity, string> = {
  CRITICAL: "bg-danger/15 text-danger border border-danger/30",
  HIGH: "bg-warn/15 text-warn border border-warn/30",
  MEDIUM: "bg-info/15 text-info border border-info/25",
  LOW: "bg-neutral/15 text-neutral border border-neutral/30",
  INFO: "bg-elevated text-muted border border-border",
};

export const SEVERITY_RANK: Record<AlertSeverity, number> = {
  CRITICAL: 0,
  HIGH: 1,
  MEDIUM: 2,
  LOW: 3,
  INFO: 4,
};

export const HEALTH_STYLES: Record<HealthState, string> = {
  GOOD: "text-ok",
  WARNING: "text-warn",
  CRITICAL: "text-danger",
};

/** Fuel bar colour. Mirrors the backend LOW_FUEL threshold (20%). */
export function fuelColor(level: number): string {
  if (level < 10) return "bg-danger";
  if (level < 20) return "bg-warn";
  if (level < 40) return "bg-accent";
  return "bg-ok";
}

export function utilizationColor(value: number): string {
  if (value >= 0.85) return "text-warn"; // at capacity -- may need more equipment
  if (value >= 0.4) return "text-ok";
  if (value > 0) return "text-neutral";
  return "text-faint";
}
