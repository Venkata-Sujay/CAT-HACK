/**
 * Shared alerts view, used by both the client and company alert pages.
 *
 * Grouped by severity rather than shown as a flat list: an operator working a
 * queue needs the criticals visually separated, not sorted-but-adjacent.
 */

import { useState } from "react";
import { AlertCard } from "./AlertCard";
import { Card, EmptyState, ErrorState, Spinner, Toggle } from "./ui";
import { SEVERITY_RANK } from "../lib/format";
import { useAlerts } from "../lib/queries";
import type { AlertSeverity } from "../lib/types";

const SEVERITY_ORDER: AlertSeverity[] = ["CRITICAL", "HIGH", "MEDIUM", "LOW", "INFO"];

const SEVERITY_HEADING: Record<AlertSeverity, string> = {
  CRITICAL: "text-danger",
  HIGH: "text-warn",
  MEDIUM: "text-info",
  LOW: "text-neutral",
  INFO: "text-muted",
};

export function AlertsView({ onOpenAsset }: { onOpenAsset?: (assetId: number) => void }) {
  const [severity, setSeverity] = useState<AlertSeverity | "">("");
  const [typeFilter, setTypeFilter] = useState("");
  const [includeResolved, setIncludeResolved] = useState(false);

  const { data, isLoading, error, refetch } = useAlerts({
    severity: severity || undefined,
    type: typeFilter || undefined,
    status: includeResolved ? "RESOLVED" : undefined,
  });

  const selectClass =
    "bg-base border border-border rounded-md px-2.5 py-1.5 text-xs text-ink focus:border-accent/50 transition-colors";

  const grouped = SEVERITY_ORDER.map((level) => ({
    severity: level,
    alerts: (data ?? [])
      .filter((alert) => alert.severity === level)
      .sort((a, b) => SEVERITY_RANK[a.severity] - SEVERITY_RANK[b.severity]),
  })).filter((group) => group.alerts.length > 0);

  return (
    <>
      <div className="flex flex-wrap items-center gap-2 mb-4">
        <select
          value={severity}
          onChange={(e) => setSeverity(e.target.value as AlertSeverity | "")}
          className={selectClass}
        >
          <option value="">All severities</option>
          {SEVERITY_ORDER.map((level) => (
            <option key={level} value={level}>
              {level}
            </option>
          ))}
        </select>

        <select value={typeFilter} onChange={(e) => setTypeFilter(e.target.value)} className={selectClass}>
          <option value="">All types</option>
          <option value="UNAUTHORIZED_OPERATOR">Unauthorized operator</option>
          <option value="UNASSIGNED_EQUIPMENT">Unassigned equipment</option>
          <option value="ENGINE_WARNING">Engine warning</option>
          <option value="TIRE_WARNING">Tire warning</option>
          <option value="LOW_FUEL">Low fuel</option>
          <option value="OVERDUE">Overdue</option>
          <option value="DUE_SOON">Due soon</option>
          <option value="UNDERUTILIZED">Under-utilized</option>
          <option value="CONTINUOUS_USAGE">Continuous usage</option>
          <option value="ML_ANOMALY">AI anomaly</option>
        </select>

        <Toggle checked={includeResolved} onChange={setIncludeResolved} label="Show resolved" />

        {data && <span className="text-xs text-faint ml-auto tnum">{data.length} alerts</span>}
      </div>

      {isLoading && (
        <Card>
          <Spinner label="Loading alerts…" />
        </Card>
      )}
      {error && (
        <Card>
          <ErrorState error={error} onRetry={() => refetch()} />
        </Card>
      )}

      {data && data.length === 0 && (
        <Card>
          <EmptyState
            title={includeResolved ? "No resolved alerts" : "No open alerts"}
            hint={
              includeResolved
                ? "Resolved alerts will appear here once conditions clear."
                : "Everything is operating within normal parameters."
            }
          />
        </Card>
      )}

      <div className="space-y-6">
        {grouped.map((group) => (
          <section key={group.severity}>
            <div className="flex items-center gap-2 mb-2.5">
              <h2 className={`text-xs font-semibold uppercase tracking-wider ${SEVERITY_HEADING[group.severity]}`}>
                {group.severity}
              </h2>
              <span className="text-2xs text-faint tnum">({group.alerts.length})</span>
              <div className="flex-1 h-px bg-border" />
            </div>
            <div className="grid grid-cols-1 xl:grid-cols-2 gap-2.5">
              {group.alerts.map((alert) => (
                <AlertCard key={alert.id} alert={alert} onOpenAsset={onOpenAsset} compact />
              ))}
            </div>
          </section>
        ))}
      </div>
    </>
  );
}
