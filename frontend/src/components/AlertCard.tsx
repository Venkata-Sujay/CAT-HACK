/**
 * Alert card -- the unit of the action queue.
 *
 * Every alert answers four questions: what happened, why it matters, how severe
 * it is, and what to do. The `reasons` and `recommended_action` fields come
 * straight from the backend; a raw model score is never the whole story shown
 * to a user.
 */

import { useState } from "react";
import { AlertTypeChip, SeverityChip } from "./ui";
import { timeAgo } from "../lib/format";
import { useAcknowledgeAlert, useResolveAlert } from "../lib/queries";
import type { Alert } from "../lib/types";

export function AlertCard({
  alert,
  onOpenAsset,
  compact = false,
}: {
  alert: Alert;
  onOpenAsset?: (assetId: number) => void;
  compact?: boolean;
}) {
  const [expanded, setExpanded] = useState(!compact);
  const acknowledge = useAcknowledgeAlert();
  const resolve = useResolveAlert();

  const busy = acknowledge.isPending || resolve.isPending;
  const isAcknowledged = alert.status === "ACKNOWLEDGED";

  const leftRail =
    alert.severity === "CRITICAL"
      ? "bg-danger"
      : alert.severity === "HIGH"
        ? "bg-warn"
        : alert.severity === "MEDIUM"
          ? "bg-info"
          : "bg-neutral";

  return (
    <div className="card relative overflow-hidden">
      <div className={`absolute left-0 top-0 bottom-0 w-[3px] ${leftRail}`} />
      <div className="p-3 pl-4">
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0 flex-1">
            <div className="flex items-center gap-2 flex-wrap mb-1.5">
              <SeverityChip severity={alert.severity} />
              <AlertTypeChip type={alert.type} />
              {alert.source === "ML" && (
                <span
                  className="chip bg-accent/10 text-accent border border-accent/25"
                  title="Detected by the anomaly model, not a fixed threshold"
                >
                  AI
                </span>
              )}
              {isAcknowledged && (
                <span className="chip bg-elevated text-faint border border-border">Acknowledged</span>
              )}
            </div>

            <button
              onClick={() => alert.asset_id && onOpenAsset?.(alert.asset_id)}
              disabled={!alert.asset_id || !onOpenAsset}
              className="text-sm font-medium text-ink text-left hover:text-accent transition-colors disabled:hover:text-ink disabled:cursor-default"
            >
              {alert.title}
            </button>

            <div className="flex items-center gap-2 mt-1 text-2xs text-faint">
              {alert.client_name && <span className="truncate">{alert.client_name}</span>}
              {alert.site_code && (
                <>
                  <span>·</span>
                  <span>{alert.site_code}</span>
                </>
              )}
              <span>·</span>
              <span>{timeAgo(alert.created_at)}</span>
            </div>
          </div>

          {compact && (
            <button
              onClick={() => setExpanded((v) => !v)}
              className="btn-ghost px-1.5 py-1 shrink-0"
              aria-label={expanded ? "Collapse" : "Expand"}
            >
              <svg
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="2"
                strokeLinecap="round"
                className={`w-4 h-4 transition-transform ${expanded ? "rotate-180" : ""}`}
              >
                <path d="M6 9l6 6 6-6" />
              </svg>
            </button>
          )}
        </div>

        {expanded && (
          <div className="mt-3 space-y-3 animate-fade-in">
            <p className="text-xs text-muted leading-relaxed">{alert.description}</p>

            {alert.reasons.length > 0 && (
              <div>
                <div className="text-2xs uppercase tracking-wider text-faint mb-1.5">
                  Why this was flagged
                </div>
                <ul className="space-y-1">
                  {alert.reasons.map((reason, index) => (
                    <li key={index} className="text-xs text-muted flex gap-2">
                      <span className="text-faint mt-[3px] shrink-0">
                        <svg viewBox="0 0 6 6" className="w-1 h-1 fill-current">
                          <circle cx="3" cy="3" r="3" />
                        </svg>
                      </span>
                      <span>{reason}</span>
                    </li>
                  ))}
                </ul>
              </div>
            )}

            {alert.recommended_action && (
              <div className="bg-base border border-border rounded-md p-2.5">
                <div className="text-2xs uppercase tracking-wider text-faint mb-1">
                  Recommended action
                </div>
                <p className="text-xs text-ink leading-relaxed">{alert.recommended_action}</p>
              </div>
            )}

            <div className="flex items-center gap-2 pt-0.5">
              {!isAcknowledged && (
                <button
                  className="btn-secondary text-xs py-1.5"
                  disabled={busy}
                  onClick={() => acknowledge.mutate(alert.id)}
                >
                  Acknowledge
                </button>
              )}
              <button
                className="btn-secondary text-xs py-1.5"
                disabled={busy}
                onClick={() => resolve.mutate(alert.id)}
              >
                Resolve
              </button>
              {alert.asset_id && onOpenAsset && (
                <button
                  className="btn-ghost text-xs py-1.5"
                  onClick={() => onOpenAsset(alert.asset_id!)}
                >
                  Investigate →
                </button>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
