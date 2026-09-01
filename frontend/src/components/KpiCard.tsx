/**
 * KPI tile. The top row of both dashboards.
 *
 * Deliberately FOUR of these, not eight. The previous eight-across row
 * truncated its own labels ("IN WAREHO…", "CRITICAL A…", "AVG UTILIZ…"), which
 * makes a first-time viewer stop and decode instead of read. Secondary numbers
 * now live in `breakdown` underneath the headline figure, where they carry
 * context rather than competing for it.
 */

import type { ReactNode } from "react";

type Tone = "default" | "ok" | "warn" | "danger" | "accent" | "info";

const TONES: Record<Tone, { value: string; rail: string }> = {
  default: { value: "text-ink", rail: "bg-borderlight" },
  ok: { value: "text-ok", rail: "bg-ok" },
  warn: { value: "text-warn", rail: "bg-warn" },
  danger: { value: "text-danger", rail: "bg-danger" },
  accent: { value: "text-accent", rail: "bg-accent" },
  info: { value: "text-info", rail: "bg-info" },
};

export interface KpiPart {
  label: string;
  value: ReactNode;
  tone?: Tone;
}

export function KpiCard({
  label,
  value,
  tone = "default",
  hint,
  breakdown,
  onClick,
}: {
  label: string;
  value: ReactNode;
  tone?: Tone;
  hint?: string;
  /** Secondary figures. Rendered as a small labelled row under the headline. */
  breakdown?: KpiPart[];
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
      className={`card p-4 relative overflow-hidden ${
        interactive ? "cursor-pointer hover:bg-elevated hover:border-borderlight transition-colors" : ""
      }`}
    >
      {/* Thin colour rail rather than a coloured card: keeps the grid calm
          while still coding severity at a glance. */}
      <div className={`absolute left-0 top-0 bottom-0 w-[3px] ${styles.rail}`} />
      <div className="pl-2">
        <div className="label text-[10px] mb-2">{label}</div>
        <div className={`text-[28px] font-semibold tnum leading-none ${styles.value}`}>{value}</div>

        {breakdown && breakdown.length > 0 && (
          <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1 mt-3 pt-2.5 border-t border-border">
            {breakdown.map((part) => (
              <span key={part.label} className="text-2xs text-faint whitespace-nowrap">
                <span
                  className={`tnum font-semibold ${
                    part.tone ? TONES[part.tone].value : "text-muted"
                  }`}
                >
                  {part.value}
                </span>{" "}
                {part.label}
              </span>
            ))}
          </div>
        )}

        {hint && !breakdown && <div className="text-2xs text-faint mt-2">{hint}</div>}
      </div>
    </div>
  );
}
