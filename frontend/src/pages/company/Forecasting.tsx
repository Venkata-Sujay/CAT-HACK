/**
 * Demand forecasting.
 *
 * The screen is built around one question a planner actually asks: "when do I
 * run short, and where?" So the page opens ON the worst shortfall rather than
 * on an empty selector -- a first-time viewer sees the finding before they
 * touch a control.
 *
 * Three layers, in the order they get read:
 *   1. headline  -- the single worst gap, in a sentence
 *   2. timeline  -- history flowing into forecast for that site+type
 *   3. detail    -- every site x type, and the pre-positioning moves it implies
 */

import { useEffect, useMemo, useState } from "react";
import { PageHeader } from "../../components/AppShell";
import { ForecastChart, ForecastTimelineChart } from "../../components/Charts";
import { RecommendationCard } from "../../components/RecommendationCard";
import { Card, EmptyState, ErrorState, SectionHeader, Spinner } from "../../components/ui";
import { equipmentImage } from "../../lib/equipment";
import { formatDate, productTypeLabel } from "../../lib/format";
import {
  useForecast,
  useForecastTimeline,
  useRecommendations,
  useRegenerateForecast,
  useSites,
} from "../../lib/queries";
import type { Forecast, ProductType } from "../../lib/types";

const HORIZON = 14;

export function Forecasting() {
  const [siteFilter, setSiteFilter] = useState("");
  const [typeFilter, setTypeFilter] = useState("");

  // The whole horizon, for the summary and the picker.
  const { data: forecasts, isLoading, error, refetch } = useForecast({ horizon: HORIZON });
  const { data: sites } = useSites();
  const { data: recommendations } = useRecommendations();
  const regenerate = useRegenerateForecast();

  /** For each (site, type), the FIRST day it goes short -- the actionable one. */
  const firstShortfalls = useMemo(() => {
    const byPair = new Map<string, Forecast>();
    for (const f of forecasts ?? []) {
      if (f.expected_shortfall <= 0.05) continue;
      const key = `${f.site_id}:${f.product_type}`;
      const seen = byPair.get(key);
      if (!seen || f.horizon_days < seen.horizon_days) byPair.set(key, f);
    }
    return [...byPair.values()].sort(
      (a, b) => a.horizon_days - b.horizon_days || b.expected_shortfall - a.expected_shortfall,
    );
  }, [forecasts]);

  const worst = firstShortfalls[0];

  // Land on the worst shortfall the first time real data arrives, then leave
  // the user's selection alone -- re-steering the chart under someone every
  // 30s poll would be maddening.
  const [pinned, setPinned] = useState(false);
  useEffect(() => {
    if (pinned || !worst) return;
    setSiteFilter(String(worst.site_id));
    setTypeFilter(worst.product_type);
    setPinned(true);
  }, [worst, pinned]);

  const selectedSite = siteFilter ? Number(siteFilter) : undefined;
  const selectedType = (typeFilter as ProductType) || undefined;
  const { data: timeline, isLoading: timelineLoading } = useForecastTimeline(
    selectedSite,
    selectedType,
  );

  /** Day-7 snapshot across every pair -- the "where" view. */
  const chartData = useMemo(() => {
    const day7 = (forecasts ?? []).filter((f) => f.horizon_days === 7);
    return day7
      .slice()
      .sort((a, b) => b.expected_shortfall - a.expected_shortfall)
      .slice(0, 12)
      .map((f) => ({
        label: `${f.site_code} · ${productTypeLabel(f.product_type).slice(0, 10)}`,
        demand: Number(f.predicted_demand.toFixed(1)),
        available: f.currently_available,
        shortfall: f.expected_shortfall,
      }));
  }, [forecasts]);

  const prepositioning = (recommendations ?? []).filter(
    (r) => r.type === "PREPOSITION_ASSET" && r.status === "OPEN",
  );
  const modelVersion = forecasts?.[0]?.model_version;
  const siteName = (id: number) => sites?.find((s) => s.id === id)?.name ?? `Site ${id}`;

  const selectClass =
    "bg-base border border-border rounded-lg px-2.5 py-1.5 text-xs text-ink focus:border-accent/60 transition-colors";

  return (
    <div className="p-6">
      <PageHeader
        title="Demand forecasting"
        subtitle={`Next ${HORIZON} days, per site and equipment type · model ${modelVersion ?? "—"}`}
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

      {isLoading && (
        <Card>
          <Spinner label="Loading forecast…" />
        </Card>
      )}
      {error && (
        <Card>
          <ErrorState error={error} onRetry={() => refetch()} />
        </Card>
      )}

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
          {/* ---- 1. The headline finding ---- */}
          {worst && (
            <div className="card rail mb-4 overflow-hidden">
              <div className="flex flex-col md:flex-row">
                <img
                  src={equipmentImage(worst.product_type, "card")}
                  alt={productTypeLabel(worst.product_type)}
                  className="w-full md:w-52 h-28 md:h-auto object-cover shrink-0"
                />
                <div className="p-4 pl-5 flex-1 min-w-0">
                  <div className="label text-[10px] mb-1.5">Earliest shortfall</div>
                  <p className="text-base text-ink leading-snug">
                    <span className="font-semibold">{siteName(worst.site_id)}</span> runs short of{" "}
                    <span className="font-semibold">
                      {productTypeLabel(worst.product_type)}s
                    </span>{" "}
                    in{" "}
                    <span className="text-accent font-semibold tnum">
                      {worst.horizon_days} day{worst.horizon_days === 1 ? "" : "s"}
                    </span>
                    .
                  </p>
                  <p className="text-sm text-muted mt-1.5 leading-relaxed">
                    Forecast demand{" "}
                    <span className="text-ink tnum font-medium">
                      {worst.predicted_demand.toFixed(1)}
                    </span>{" "}
                    against{" "}
                    <span className="text-ink tnum font-medium">
                      {worst.currently_available}
                    </span>{" "}
                    projected on site on {formatDate(worst.forecast_date)} — short by{" "}
                    <span className="text-danger tnum font-semibold">
                      {worst.expected_shortfall.toFixed(1)}
                    </span>
                    .
                  </p>
                  <div className="flex flex-wrap items-center gap-2 mt-3">
                    <span className="chip bg-danger/15 text-danger border border-danger/30">
                      {firstShortfalls.length} shortfall
                      {firstShortfalls.length === 1 ? "" : "s"} across the horizon
                    </span>
                    <span className="chip bg-elevated text-muted border border-border">
                      {prepositioning.length} move
                      {prepositioning.length === 1 ? "" : "s"} suggested
                    </span>
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* ---- 2. The timeline ---- */}
          <Card className="mb-4">
            <div className="flex flex-wrap items-start justify-between gap-3 mb-3">
              <SectionHeader
                title="Demand over time"
                subtitle="Solid line is what happened. Dashed line is what the model predicts. Blue band is what will actually be on site."
              />
              <div className="flex items-center gap-2 shrink-0">
                <select
                  value={siteFilter}
                  onChange={(e) => setSiteFilter(e.target.value)}
                  className={selectClass}
                  aria-label="Site"
                >
                  <option value="">Select a site…</option>
                  {(sites ?? [])
                    .filter((site) => !site.is_warehouse)
                    .map((site) => (
                      <option key={site.id} value={site.id}>
                        {site.code} — {site.name}
                      </option>
                    ))}
                </select>
                <select
                  value={typeFilter}
                  onChange={(e) => setTypeFilter(e.target.value)}
                  className={selectClass}
                  aria-label="Equipment type"
                >
                  <option value="">Select a type…</option>
                  <option value="EXCAVATOR">Excavator</option>
                  <option value="BULLDOZER">Bulldozer</option>
                  <option value="CRANE">Crane</option>
                  <option value="GRADER">Grader</option>
                  <option value="WHEEL_LOADER">Wheel Loader</option>
                </select>
              </div>
            </div>

            {!selectedSite || !selectedType ? (
              <EmptyState
                title="Pick a site and an equipment type"
                hint="The chart shows three weeks of recorded demand flowing into the next two weeks of prediction."
              />
            ) : timelineLoading ? (
              <Spinner label="Loading timeline…" />
            ) : timeline && timeline.points.length > 0 ? (
              <ForecastTimelineChart points={timeline.points} today={timeline.today} height={270} />
            ) : (
              <EmptyState
                title="No history for this combination"
                hint="This site has never rented this equipment type."
              />
            )}
          </Card>

          {/* ---- 3. Detail ---- */}
          <Card className="mb-4">
            <SectionHeader
              title="Where the gaps are"
              subtitle="Forecast demand vs on-site stock one week out. Red bars mark a shortfall."
            />
            <ForecastChart data={chartData} height={230} />
          </Card>

          <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">
            <Card padded={false}>
              <div className="p-4 pb-2">
                <SectionHeader
                  title="First day short"
                  subtitle="Every site and type that goes short inside the horizon, soonest first"
                />
              </div>
              <div className="overflow-x-auto max-h-[420px] overflow-y-auto">
                {firstShortfalls.length === 0 ? (
                  <div className="p-4">
                    <EmptyState
                      title="Nothing goes short"
                      hint="Projected stock covers forecast demand at every site for the whole horizon."
                    />
                  </div>
                ) : (
                  <table className="w-full border-collapse">
                    <thead className="sticky top-0 bg-surface z-10">
                      <tr className="border-b border-border">
                        <th className="th">Site</th>
                        <th className="th">Type</th>
                        <th className="th text-right">In</th>
                        <th className="th text-right">Need</th>
                        <th className="th text-right">Have</th>
                        <th className="th text-right">Short</th>
                      </tr>
                    </thead>
                    <tbody>
                      {firstShortfalls.map((f) => {
                        const selected =
                          String(f.site_id) === siteFilter && f.product_type === typeFilter;
                        return (
                          <tr
                            key={`${f.site_id}:${f.product_type}`}
                            onClick={() => {
                              setSiteFilter(String(f.site_id));
                              setTypeFilter(f.product_type);
                            }}
                            className={`border-b border-border/60 cursor-pointer transition-colors ${
                              selected ? "bg-accent/10" : "hover:bg-elevated"
                            }`}
                          >
                            <td className="td font-mono text-xs text-muted">{f.site_code}</td>
                            <td className="td text-ink">
                              <span className="inline-flex items-center gap-2">
                                <img
                                  src={equipmentImage(f.product_type, "thumb")}
                                  alt=""
                                  className="w-8 h-5 rounded object-cover shrink-0"
                                />
                                {productTypeLabel(f.product_type)}
                              </span>
                            </td>
                            <td className="td text-right text-muted tnum">{f.horizon_days}d</td>
                            <td className="td text-right text-ink tnum">
                              {f.predicted_demand.toFixed(1)}
                            </td>
                            <td className="td text-right text-muted tnum">
                              {f.currently_available}
                            </td>
                            <td className="td text-right tnum text-danger font-semibold">
                              −{f.expected_shortfall.toFixed(1)}
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                )}
              </div>
            </Card>

            <div>
              <div className="flex items-center gap-2 mb-2.5">
                <h2 className="label text-[11px]">Pre-positioning recommendations</h2>
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
            Forecasts come from a gradient-boosting regressor run <strong>recursively</strong>: each
            day's prediction feeds the next day's lag features, so accuracy degrades with distance
            from today. The model was trained on synthetic historical demand with a time-aware
            train/test split and beats a 7-day rolling-mean baseline by 27.6% MAE. Those metrics
            measure fit to the generated data, <strong>not</strong> real-world accuracy.
          </p>
        </>
      )}
    </div>
  );
}
