/**
 * Client overview.
 *
 * Deliberately simpler than the control tower: a client cares about their own
 * machines, their own deadlines and their own alerts. Everything on this page
 * is scoped by the backend to the caller's tenant.
 */

import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { PageHeader } from "../../components/AppShell";
import { AlertCard } from "../../components/AlertCard";
import { AssetDetailDrawer } from "../../components/AssetDetailDrawer";
import { AssetTable } from "../../components/AssetTable";
import { RuntimeIdleChart, UtilizationTrendChart } from "../../components/Charts";
import { FleetStrip } from "../../components/FleetStrip";
import { KpiCard } from "../../components/KpiCard";
import { RecommendationCard } from "../../components/RecommendationCard";
import { Card, EmptyState, ErrorState, SectionHeader, Spinner } from "../../components/ui";
import { useAuth } from "../../lib/auth";
import { percent } from "../../lib/format";
import { useClientDashboard } from "../../lib/queries";

export function ClientOverview() {
  const { user } = useAuth();
  const { data, isLoading, error, refetch } = useClientDashboard();
  const [selectedAsset, setSelectedAsset] = useState<number | null>(null);
  const navigate = useNavigate();

  if (isLoading) return <div className="p-6"><Spinner label="Loading your fleet…" /></div>;
  if (error) return <div className="p-6"><ErrorState error={error} onRetry={() => refetch()} /></div>;
  if (!data) return null;

  const { kpis, assets, alerts, utilization_trend, recommendations, by_product_type } = data;
  const topRecommendation = recommendations.find((r) => r.status === "OPEN");

  return (
    <div className="p-6">
      <PageHeader
        title={`${user?.client?.name ?? "My"} operations`}
        subtitle="Equipment currently rented to your organisation"
      />

      <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-3 mb-4">
        <KpiCard
          label="My equipment"
          value={kpis.total_assets}
          breakdown={[
            { label: "working now", value: kpis.active_assets, tone: "ok" },
            { label: "on site, idle", value: kpis.idle_assets },
          ]}
        />
        <KpiCard
          label="Returns coming up"
          value={kpis.due_soon + kpis.overdue}
          tone={kpis.overdue > 0 ? "danger" : kpis.due_soon > 0 ? "warn" : "default"}
          breakdown={[
            { label: "due within 48h", value: kpis.due_soon, tone: "warn" },
            { label: "already overdue", value: kpis.overdue, tone: "danger" },
          ]}
        />
        <KpiCard
          label="Needs attention"
          value={kpis.critical_alerts}
          tone={kpis.critical_alerts > 0 ? "danger" : "ok"}
          onClick={() => navigate("/client/alerts")}
          breakdown={[{ label: "high and critical alerts on your machines", value: "" }]}
        />
        <KpiCard
          label="Fleet utilization"
          value={percent(kpis.avg_utilization)}
          tone="accent"
          breakdown={[{ label: "engine time ÷ time on site, today", value: "" }]}
        />
      </div>

      {by_product_type.length > 0 && (
        <div className="mb-5">
          <div className="flex items-center gap-2 mb-2.5">
            <h2 className="label text-[11px]">What you have on hire</h2>
            <div className="flex-1 h-px bg-border" />
          </div>
          <FleetStrip stats={by_product_type} basePath="/client/assets" />
        </div>
      )}

      {topRecommendation && (
        <div className="mb-5">
          <RecommendationCard recommendation={topRecommendation} />
        </div>
      )}

      <div className="grid grid-cols-1 xl:grid-cols-3 gap-4 mb-5">
        <Card className="xl:col-span-2" padded={false}>
          <div className="p-4 pb-2">
            <SectionHeader
              title="My assets"
              subtitle={`${assets.length} machines on rental`}
              action={
                <button onClick={() => navigate("/client/assets")} className="btn-ghost text-xs py-1">
                  View all →
                </button>
              }
            />
          </div>
          {assets.length === 0 ? (
            <EmptyState title="No equipment on rental" hint="Rented machines will appear here." />
          ) : (
            <div className="max-h-[420px] overflow-y-auto">
              <AssetTable assets={assets.slice(0, 12)} onSelect={setSelectedAsset} />
            </div>
          )}
        </Card>

        <Card padded={false} className="flex flex-col max-h-[480px]">
          <div className="p-4 pb-3 shrink-0">
            <SectionHeader
              title="Alerts"
              subtitle="Issues affecting your equipment"
              action={
                <button onClick={() => navigate("/client/alerts")} className="btn-ghost text-xs py-1">
                  All →
                </button>
              }
            />
          </div>
          <div className="flex-1 overflow-y-auto px-4 pb-4 space-y-2">
            {alerts.length === 0 ? (
              <EmptyState title="No open alerts" hint="Your equipment is operating normally." />
            ) : (
              alerts
                .slice(0, 10)
                .map((alert) => (
                  <AlertCard key={alert.id} alert={alert} compact onOpenAsset={setSelectedAsset} />
                ))
            )}
          </div>
        </Card>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <Card>
          <SectionHeader title="Utilization trend" subtitle="Last 24 hours across your fleet" />
          {utilization_trend.length > 0 ? (
            <UtilizationTrendChart data={utilization_trend} />
          ) : (
            <EmptyState title="No telemetry yet" />
          )}
        </Card>

        <Card>
          <SectionHeader title="Runtime vs idle" subtitle="Where your rented hours went" />
          {utilization_trend.length > 0 ? (
            <RuntimeIdleChart data={utilization_trend} />
          ) : (
            <EmptyState title="No telemetry yet" />
          )}
        </Card>
      </div>

      <AssetDetailDrawer assetId={selectedAsset} onClose={() => setSelectedAsset(null)} />
    </div>
  );
}
