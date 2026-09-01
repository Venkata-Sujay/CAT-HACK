/**
 * Demand forecasting.
 *
 * Shows predicted demand against currently-available stock per site and
 * equipment type, plus the pre-positioning recommendations that shortfall
 * drives. This is the PREDICT -> RECOMMEND half of the product loop.
 */

import { useMemo, useState } from "react";
import { PageHeader } from "../../components/AppShell";
import { ForecastChart } from "../../components/Charts";
import { RecommendationCard } from "../../components/RecommendationCard";
import { Card, EmptyState, ErrorState, SectionHeader, Spinner } from "../../components/ui";
import { formatDate, productTypeLabel } from "../../lib/format";
import {
  useForecast,
  useRecommendations,
  useRegenerateForecast,
  useSites,
} from "../../lib/queries";
import type { ProductType } from "../../lib/types";

export function Forecasting() {
  const [siteFilter, setSiteFilter] = useState("");
  const [typeFilter, setTypeFilter] = useState("");

  const { data: forecasts, isLoading, error, refetch } = useForecast({
    site_id: siteFilter ? Number(siteFilter) : undefined,
    product_type: (typeFilter as ProductType) || undefined,
  });
  const { data: sites } = useSites();
  const { data: recommendations } = useRecommendations();
  const regenerate = useRegenerateForecast();

  const chartData = useMemo(
    () =>
      (forecasts ?? [])
        .slice()
        .sort((a, b) => b.expected_shortfall - a.expected_shortfall)
        .slice(0, 12)
        .map((forecast) => ({
          label: `${forecast.site_code} · ${productTypeLabel(forecast.product_type).slice(0, 10)}`,
          demand: Number(forecast.predicted_demand.toFixed(1)),
          available: forecast.currently_available,
          shortfall: forecast.expected_shortfall,
        })),
    [forecasts],
  );

  const shortfalls = (forecasts ?? []).filter((f) => f.expected_shortfall > 0.05);
  const prepositioning = (recommendations ?? []).filter(
    (r) => r.type === "PREPOSITION_ASSET" && r.status === "OPEN",
  );
  const forecastDate = forecasts?.[0]?.forecast_date;
  const modelVersion = forecasts?.[0]?.model_version;

  const selectClass =
    "bg-base border border-border rounded-md px-2.5 py-1.5 text-xs text-ink focus:border-accent/50 transition-colors";

  return (
    <div className="p-6">
      <PageHeader
        title="Demand forecasting"
        subtitle={
          forecastDate
            ? `Predicted demand for ${formatDate(forecastDate)} · model ${modelVersion ?? "—"}`
            : "Predicted equipment demand by site and type"
        }
        actions={
          <button
            className="btn-secondary text-xs py-1.5"
            disabled={regenerate.isPending}
            onClick={() => regenerate.mutate()}
          >
            {regenerate.isPending ? "Recomputing…" : "Regenerate forecast"}
          </button>
        }
      />

      <div className="flex flex-wrap items-center gap-2 mb-4">
        <select value={siteFilter} onChange={(e) => setSiteFilter(e.target.value)} className={selectClass}>
          <option value="">All sites</option>
          {(sites ?? [])
            .filter((site) => !site.is_warehouse)
            .map((site) => (
              <option key={site.id} value={site.id}>
                {site.code} — {site.name}
              </option>
            ))}
        </select>

        <select value={typeFilter} onChange={(e) => setTypeFilter(e.target.value)} className={selectClass}>
          <option value="">All equipment types</option>
          <option value="EXCAVATOR">Excavator</option>
          <option value="BULLDOZER">Bulldozer</option>
          <option value="CRANE">Crane</option>
          <option value="GRADER">Grader</option>
          <option value="WHEEL_LOADER">Wheel Loader</option>
        </select>

        {shortfalls.length > 0 && (
          <span className="chip bg-danger/15 text-danger border border-danger/30 ml-auto">
            {shortfalls.length} shortfall{shortfalls.length > 1 ? "s" : ""} predicted
          </span>
        )}
      </div>

      {isLoading && <Card><Spinner label="Loading forecast…" /></Card>}
      {error && <Card><ErrorState error={error} onRetry={() => refetch()} /></Card>}

      {forecasts && forecasts.length === 0 && (
        <Card>
          <EmptyState
            title="No forecast available"
            hint="Click Regenerate forecast, or train the demand model with: python ml/train_demand_model.py"
          />
        </Card>
      )}

      {forecasts && forecasts.length > 0 && (
        <>
          <Card className="mb-4">
            <SectionHeader
              title="Forecast demand vs available stock"
              subtitle="Red bars mark where predicted demand exceeds what is deployed at that site"
            />
            <ForecastChart data={chartData} height={230} />
          </Card>

          <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">
            <Card padded={false}>
              <div className="p-4 pb-2">
                <SectionHeader title="Forecast detail" subtitle="Every site and equipment type" />
              </div>
              <div className="overflow-x-auto max-h-[420px] overflow-y-auto">
                <table className="w-full border-collapse">
                  <thead className="sticky top-0 bg-surface">
                    <tr className="border-b border-border">
                      <th className="th">Site</th>
                      <th className="th">Type</th>
                      <th className="th text-right">Predicted</th>
                      <th className="th text-right">Available</th>
                      <th className="th text-right">Shortfall</th>
                    </tr>
                  </thead>
                  <tbody>
                    {forecasts
                      .slice()
                      .sort((a, b) => b.expected_shortfall - a.expected_shortfall)
                      .map((forecast) => (
                        <tr
                          key={forecast.id}
                          className="border-b border-border/60 hover:bg-elevated transition-colors"
                        >
                          <td className="td font-mono text-xs text-muted">{forecast.site_code}</td>
                          <td className="td text-ink">{productTypeLabel(forecast.product_type)}</td>
                          <td className="td text-right text-ink tnum">
                            {forecast.predicted_demand.toFixed(1)}
                          </td>
                          <td className="td text-right text-muted tnum">
                            {forecast.currently_available}
                          </td>
                          <td className="td text-right tnum">
                            {forecast.expected_shortfall > 0.05 ? (
                              <span className="text-danger font-semibold">
                                −{forecast.expected_shortfall.toFixed(1)}
                              </span>
                            ) : (
                              <span className="text-ok">covered</span>
                            )}
                          </td>
                        </tr>
                      ))}
                  </tbody>
                </table>
              </div>
            </Card>

            <div>
              <div className="flex items-center gap-2 mb-2.5">
                <h2 className="text-xs font-semibold uppercase tracking-wider text-faint">
                  Pre-positioning recommendations
                </h2>
                <div className="flex-1 h-px bg-border" />
              </div>

              {prepositioning.length === 0 ? (
                <Card>
                  <EmptyState
                    title="No pre-positioning needed"
                    hint="Current stock placement covers the forecast demand."
                  />
                </Card>
              ) : (
                <div className="space-y-3 max-h-[420px] overflow-y-auto pr-1">
                  {prepositioning.map((recommendation) => (
                    <RecommendationCard key={recommendation.id} recommendation={recommendation} />
                  ))}
                </div>
              )}
            </div>
          </div>

          <p className="text-2xs text-faint mt-4 leading-relaxed max-w-3xl">
            Forecasts come from a gradient-boosting model trained on synthetic historical rental
            demand with a time-aware train/test split. Metrics measure fit to that generated data,
            not real-world accuracy.
          </p>
        </>
      )}
    </div>
  );
}
