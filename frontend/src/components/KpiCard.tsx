/** KPI tile. The top row of both dashboards. */

import type { ReactNode } from "react";

type Tone = "default" | "ok" | "warn" | "danger" | "accent" | "info";

const TONES: Record<Tone, { value: string; accent: string }> = {
  default: { value: "text-ink", accent: "bg-border" },
  ok: { value: "text-ok", accent: "bg-ok" },
  warn: { value: "text-warn", accent: "bg-warn" },
  danger: { value: "text-danger", accent: "bg-danger" },
  accent: { value: "text-accent", accent: "bg-accent" },
  info: { value: "text-info", accent: "bg-info" },
};

export function KpiCard({
  label,
  value,
  tone = "default",
  hint,
  onClick,
}: {
  label: string;
  value: ReactNode;
  tone?: Tone;
  hint?: string;
  onClick?: () => void;
}) {
  const styles = TONES[tone];
  const interactive = Boolean(onClick);

  return (
    <div
      onClick={onClick}
      role={interactive ? "button" : undefined}
      tabIndex={interactive ? 0 : undefined}
      onKeyDown={
        interactive
          ? (e) => {
              if (e.key === "Enter" || e.key === " ") {
                e.preventDefault();
                onClick?.();
              }
            }
          : undefined
      }
      className={`card p-3.5 relative overflow-hidden ${
        interactive ? "cursor-pointer hover:bg-elevated transition-colors" : ""
      }`}
    >
      {/* Thin colour rail rather than a coloured card: keeps the grid calm
          while still coding severity at a glance. */}
      <div className={`absolute left-0 top-0 bottom-0 w-[3px] ${styles.accent}`} />
      <div className="pl-1.5">
        <div className="text-2xs uppercase tracking-wider text-faint mb-1.5 truncate">{label}</div>
        <div className={`text-2xl font-semibold tnum leading-none ${styles.value}`}>{value}</div>
        {hint && <div className="text-2xs text-faint mt-1.5 truncate">{hint}</div>}
      </div>
    </div>
  );
}
