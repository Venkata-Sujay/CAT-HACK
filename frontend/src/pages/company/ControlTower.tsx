/**
 * Company control tower.
 *
 * The layout answers four questions top to bottom:
 *   KPI row      -> WHAT IS HAPPENING?
 *   map + queue  -> WHAT IS WRONG?
 *   charts       -> WHAT WILL HAPPEN NEXT?
 *   queue action -> WHAT SHOULD I DO?
 */

import { useNavigate } from "react-router-dom";
import { useState } from "react";
import { PageHeader } from "../../components/AppShell";
import { AlertCard } from "../../components/AlertCard";
import { AssetDetailDrawer } from "../../components/AssetDetailDrawer";
import { FleetCompositionChart, UtilizationTrendChart } from "../../components/Charts";
import { KpiCard } from "../../components/KpiCard";
import { SiteMap } from "../../components/SiteMap";
import { Card, EmptyState, ErrorState, SectionHeader, Spinner } from "../../components/ui";
import { percent, productTypeLabel } from "../../lib/format";
import { useCompanyDashboard, useSimulatorControl, useSimulatorStatus } from "../../lib/queries";

export function ControlTower() {
  const { data, isLoading, error, refetch } = useCompanyDashboard();
  const [selectedAsset, setSelectedAsset] = useState<number | null>(null);
  const navigate = useNavigate();

  if (isLoading) return <div className="p-6"><Spinner label="Loading control tower…" /></div>;
  if (error) return <div className="p-6"><ErrorState error={error} onRetry={() => refetch()} /></div>;
  if (!data) return null;

  const { kpis, sites, action_queue, utilization_trend, by_product_type, forecasts } = data;
  const shortfalls = forecasts.filter((f) => f.expected_shortfall > 0.5);

  return (
    <div className="p-6">
      <PageHeader
        title="Control Tower"
        subtitle="Fleet-wide operational picture across all clients and sites"
        actions={<SimulatorControls />}
      />

      {/* ---- WHAT IS HAPPENING ---- */}
      <div className="grid grid-cols-2 md:grid-cols-4 xl:grid-cols-8 gap-3 mb-5">
        <KpiCard label="Total fleet" value={kpis.total_fleet} />
        <KpiCard label="Rented out" value={kpis.rented} tone="info" />
        <KpiCard label="Active now" value={kpis.active} tone="ok" />
        <KpiCard label="Idle" value={kpis.idle} tone="default" />
        <KpiCard label="In warehouse" value={kpis.in_warehouse} />
        <KpiCard
          label="Overdue"
          value={kpis.overdue}
          tone={kpis.overdue > 0 ? "danger" : "default"}
          onClick={() => navigate("/company/rentals")}
        />
        <KpiCard
          label="Critical alerts"
          value={kpis.critical_alerts}
          tone={kpis.critical_alerts > 0 ? "danger" : "ok"}
          onClick={() => navigate("/company/alerts")}
        />
        <KpiCard label="Avg utilization" value={percent(kpis.avg_utilization)} tone="accent" />
      </div>

      {/* ---- WHAT IS WRONG ---- */}
      <div className="grid grid-cols-1 xl:grid-cols-3 gap-4 mb-5">
        <Card className="xl:col-span-2" padded={false}>
          <div className="p-4 pb-3">
            <SectionHeader
              title="Site map"
              subtitle={`${sites.length} locations · marker shows deployed assets, red badge shows open anomalies`}
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

        <Card padded={false} className="flex flex-col max-h-[460px]">
          <div className="p-4 pb-3 shrink-0">
            <SectionHeader
              title="Action queue"
              subtitle="Highest severity first"
              action={
                <button onClick={() => navigate("/company/alerts")} className="btn-ghost text-xs py-1">
                  All →
                </button>
              }
            />
          </div>
          <div className="flex-1 overflow-y-auto px-4 pb-4 space-y-2">
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

      {/* ---- WHAT WILL HAPPEN NEXT ---- */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <Card>
          <SectionHeader title="Fleet utilization" subtitle="Last 24 hours" />
          {utilization_trend.length > 0 ? (
            <UtilizationTrendChart data={utilization_trend} />
          ) : (
            <EmptyState title="No telemetry yet" hint="Start the simulator to populate this chart." />
          )}
        </Card>

        <Card>
          <SectionHeader title="Fleet composition" subtitle="By equipment type" />
          <FleetCompositionChart data={by_product_type} />
        </Card>

        <Card padded={false} className="flex flex-col">
          <div className="p-4 pb-3">
            <SectionHeader
              title="Forecast shortfalls"
              subtitle="Predicted demand exceeding available stock"
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
                  <div
                    key={forecast.id}
                    className="flex items-center justify-between gap-3 bg-base border border-border rounded-md px-3 py-2"
                  >
                    <div className="min-w-0">
                      <div className="text-xs font-medium text-ink truncate">
                        {productTypeLabel(forecast.product_type)}
                      </div>
                      <div className="text-2xs text-faint">{forecast.site_code}</div>
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
                  </div>
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
