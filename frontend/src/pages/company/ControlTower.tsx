/**
 * Company control tower.
 *
 * The layout answers four questions top to bottom, and a first-time viewer
 * should be able to follow them without being told:
 *
 *   KPI row        -> WHAT IS HAPPENING?      four figures, no truncated labels
 *   fleet strip    -> WHAT DO WE HAVE?        the machines themselves
 *   map + queue    -> WHAT IS WRONG?          located, then triaged
 *   charts         -> WHAT HAPPENS NEXT?
 *
 * The eight-across KPI row this replaced truncated every label past the fourth
 * tile, so the top of the most important screen read as gibberish.
 */

import { useNavigate } from "react-router-dom";
import { useState } from "react";
import { PageHeader } from "../../components/AppShell";
import { AlertCard } from "../../components/AlertCard";
import { AssetDetailDrawer } from "../../components/AssetDetailDrawer";
import { FleetCompositionChart, UtilizationTrendChart } from "../../components/Charts";
import { FleetStrip } from "../../components/FleetStrip";
import { KpiCard } from "../../components/KpiCard";
import { SiteMap } from "../../components/SiteMap";
import { Card, EmptyState, ErrorState, SectionHeader, Spinner } from "../../components/ui";
import { alertTypeLabel, percent, productTypeLabel } from "../../lib/format";
import { useCompanyDashboard, useSimulatorControl, useSimulatorStatus } from "../../lib/queries";
import type { Alert } from "../../lib/types";

export function ControlTower() {
  const { data, isLoading, error, refetch } = useCompanyDashboard();
  const [selectedAsset, setSelectedAsset] = useState<number | null>(null);
  const navigate = useNavigate();

  if (isLoading)
    return (
      <div className="p-6">
        <Spinner label="Loading control tower…" />
      </div>
    );
  if (error)
    return (
      <div className="p-6">
        <ErrorState error={error} onRetry={() => refetch()} />
      </div>
    );
  if (!data) return null;

  const { kpis, sites, action_queue, utilization_trend, by_product_type, forecasts } = data;
  const shortfalls = forecasts
    .filter((f) => f.expected_shortfall > 0.5)
    .sort((a, b) => a.horizon_days - b.horizon_days || b.expected_shortfall - a.expected_shortfall);

  // The queue is dominated by a handful of repeated alert types, so a summary
  // strip above it stops "37 red cards" reading as one undifferentiated wall.
  const queueByType = summariseQueue(action_queue);
  const attention = kpis.critical_alerts + kpis.overdue;

  return (
    <div className="p-6">
      <PageHeader
        title="Control Tower"
        subtitle="Live picture of every machine, across every client and site"
        actions={<SimulatorControls />}
      />

      {/* ---- WHAT IS HAPPENING ---- */}
      <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-3 mb-4">
        <KpiCard
          label="Fleet"
          value={kpis.total_fleet}
          breakdown={[
            { label: "on hire", value: kpis.rented, tone: "info" },
            { label: "in depot", value: kpis.in_warehouse },
            { label: "in workshop", value: kpis.maintenance, tone: "warn" },
          ]}
        />
        <KpiCard
          label="Working right now"
          value={kpis.active}
          tone="ok"
          breakdown={[
            { label: "engines running", value: kpis.active, tone: "ok" },
            { label: "on site but idle", value: kpis.idle },
          ]}
        />
        <KpiCard
          label="Needs attention"
          value={attention}
          tone={attention > 0 ? "danger" : "ok"}
          onClick={() => navigate("/company/alerts")}
          breakdown={[
            { label: "urgent alerts (high + critical)", value: kpis.critical_alerts, tone: "danger" },
            { label: "overdue returns", value: kpis.overdue, tone: "danger" },
          ]}
        />
        <KpiCard
          label="Fleet utilization"
          value={percent(kpis.avg_utilization)}
          tone="accent"
          breakdown={[{ label: "engine time ÷ time on site, today", value: "" }]}
        />
      </div>

      {/* ---- WHAT DO WE HAVE ---- */}
      <div className="mb-5">
        <div className="flex items-center gap-2 mb-2.5">
          <h2 className="label text-[11px]">Equipment classes</h2>
          <div className="flex-1 h-px bg-border" />
          <span className="text-2xs text-faint">click a class to filter the fleet</span>
        </div>
        <FleetStrip stats={by_product_type} />
      </div>

      {/* ---- WHAT IS WRONG ---- */}
      <div className="grid grid-cols-1 xl:grid-cols-3 gap-4 mb-5">
        <Card className="xl:col-span-2" padded={false}>
          <div className="p-4 pb-3">
            <SectionHeader
              title="Where the fleet is"
              subtitle={`${sites.length} locations · the number on a marker is machines on site, the red badge is open anomalies`}
              action={
                <button onClick={() => navigate("/company/map")} className="btn-ghost text-xs py-1">
                  Expand →
                </button>
              }
            />
          </div>
          <div className="px-4 pb-4">
            <SiteMap
              sites={sites}
              height={340}
              onSelectSite={(siteId) => navigate(`/company/fleet?site=${siteId}`)}
            />
          </div>
        </Card>

        <Card padded={false} className="flex flex-col max-h-[494px] rail rail-danger">
          <div className="p-4 pl-5 pb-3 shrink-0">
            <SectionHeader
              title="Action queue"
              subtitle="Most severe first"
              action={
                <button
                  onClick={() => navigate("/company/alerts")}
                  className="btn-ghost text-xs py-1"
                >
                  All →
                </button>
              }
            />
            {queueByType.length > 0 && (
              <div className="flex flex-wrap gap-1.5">
                {queueByType.map((group) => (
                  <button
                    key={group.type}
                    onClick={() => navigate(`/company/alerts?type=${group.type}`)}
                    className="chip bg-elevated text-muted border border-border normal-case
                               tracking-normal hover:border-accent/50 hover:text-ink transition-colors"
                  >
                    <span className="tnum font-semibold text-ink">{group.count}</span>
                    {alertTypeLabel(group.type)}
                  </button>
                ))}
              </div>
            )}
          </div>
          <div className="flex-1 overflow-y-auto px-4 pl-5 pb-4 space-y-2">
            {action_queue.length === 0 ? (
              <EmptyState title="Nothing needs attention" hint="No open alerts across the fleet." />
            ) : (
              action_queue
                .slice(0, 12)
                .map((alert) => (
                  <AlertCard key={alert.id} alert={alert} compact onOpenAsset={setSelectedAsset} />
                ))
            )}
          </div>
        </Card>
      </div>

      {/* ---- WHAT HAPPENS NEXT ---- */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <Card>
          <SectionHeader title="Fleet utilization" subtitle="Last 24 hours" />
          {utilization_trend.length > 0 ? (
            <UtilizationTrendChart data={utilization_trend} />
          ) : (
            <EmptyState
              title="No telemetry yet"
              hint="Start the simulator to populate this chart."
            />
          )}
        </Card>

        <Card>
          <SectionHeader title="Fleet composition" subtitle="By equipment type" />
          <FleetCompositionChart data={by_product_type} />
        </Card>

        <Card padded={false} className="flex flex-col">
          <div className="p-4 pb-3">
            <SectionHeader
              title="Coming up short"
              subtitle="Sites where forecast demand beats stock, soonest first"
              action={
                <button
                  onClick={() => navigate("/company/forecasting")}
                  className="btn-ghost text-xs py-1"
                >
                  Details →
                </button>
              }
            />
          </div>
          <div className="flex-1 overflow-y-auto px-4 pb-4">
            {shortfalls.length === 0 ? (
              <EmptyState
                title="No shortfalls predicted"
                hint="Current stock covers forecast demand at every site."
              />
            ) : (
              <div className="space-y-2">
                {shortfalls.slice(0, 6).map((forecast) => (
                  <button
                    key={forecast.id}
                    onClick={() => navigate("/company/forecasting")}
                    className="w-full flex items-center gap-3 bg-base border border-border rounded-lg
                               px-2.5 py-2 hover:border-accent/40 transition-colors text-left"
                  >
                    <div className="min-w-0 flex-1">
                      <div className="text-xs font-medium text-ink truncate">
                        {productTypeLabel(forecast.product_type)}
                      </div>
                      <div className="text-2xs text-faint">
                        {forecast.site_code} · in {forecast.horizon_days}d
                      </div>
                    </div>
                    <div className="text-right shrink-0">
                      <div className="text-xs text-danger font-semibold tnum">
                        −{forecast.expected_shortfall.toFixed(1)}
                      </div>
                      <div className="text-2xs text-faint tnum">
                        need {forecast.predicted_demand.toFixed(1)} · have{" "}
                        {forecast.currently_available}
                      </div>
                    </div>
                  </button>
                ))}
              </div>
            )}
          </div>
        </Card>
      </div>

      <AssetDetailDrawer assetId={selectedAsset} onClose={() => setSelectedAsset(null)} />
    </div>
  );
}

function summariseQueue(queue: Alert[]): { type: string; count: number }[] {
  const counts = new Map<string, number>();
  for (const alert of queue) counts.set(alert.type, (counts.get(alert.type) ?? 0) + 1);
  return [...counts.entries()]
    .map(([type, count]) => ({ type, count }))
    .sort((a, b) => b.count - a.count)
    .slice(0, 5);
}

/**
 * Simulator controls.
 *
 * "Tick once" is here on purpose: it lets a presenter advance the simulation on
 * cue rather than waiting for the timer to fire mid-sentence.
 */
function SimulatorControls() {
  const { data: status } = useSimulatorStatus();
  const control = useSimulatorControl();

  return (
    <div className="flex items-center gap-2">
      <button
        className="btn-secondary text-xs py-1.5"
        disabled={control.isPending}
        onClick={() => control.mutate("tick")}
        title="Advance the simulation by one interval"
      >
        Tick once
      </button>
      <button
        className="btn-secondary text-xs py-1.5"
        disabled={control.isPending}
        onClick={() => control.mutate(status?.running ? "stop" : "start")}
      >
        {status?.running ? "Pause telemetry" : "Resume telemetry"}
      </button>
    </div>
  );
}
