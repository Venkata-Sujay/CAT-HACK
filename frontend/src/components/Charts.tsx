/**
 * Shared chart components. Recharts, themed to the Caterpillar dark palette.
 *
 * ---------------------------------------------------------------------------
 * EVERY chart here sets `isAnimationActive={false}`. This is not a style
 * preference, it is a correctness fix.
 *
 * These screens poll every 5s. Each poll hands Recharts a new data array, which
 * restarts the enter animation. On a <Bar> that has <Cell> children the cells
 * remount mid-animation and the bar freezes at whatever fraction of its height
 * it had reached -- measured at ~21% on the forecast chart, so a predicted
 * demand of 3.3 rendered SHORTER than an availability of 1. The table said one
 * thing and the chart said the opposite, which reads as "the model is broken"
 * when the model was fine.
 *
 * Do not re-enable animation on a polled chart.
 * ---------------------------------------------------------------------------
 */

import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  ComposedChart,
  Legend,
  Line,
  ReferenceLine,
  ResponsiveContainer,
  Scatter,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { ChartTooltip } from "./AssetDetailDrawer";
import { productTypeLabel } from "../lib/format";
import type { ProductTypeStat, UtilizationPoint } from "../lib/types";

const AXIS = { fill: "#697384", fontSize: 10 };
const GRID = "#282C33";
const STEEL = "#3A414D";

export function UtilizationTrendChart({
  data,
  height = 180,
}: {
  data: UtilizationPoint[];
  height?: number;
}) {
  const chartData = data.map((point) => ({
    label: point.label,
    utilization: Math.round(point.utilization * 100),
    runtime: point.runtime_hours,
    idle: point.idle_hours,
  }));

  return (
    <ResponsiveContainer width="100%" height={height}>
      <AreaChart data={chartData} margin={{ top: 4, right: 4, left: -18, bottom: 0 }}>
        <defs>
          <linearGradient id="utilFill" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#3DD68C" stopOpacity={0.34} />
            <stop offset="100%" stopColor="#3DD68C" stopOpacity={0} />
          </linearGradient>
        </defs>
        <CartesianGrid stroke={GRID} strokeDasharray="3 3" vertical={false} />
        <XAxis dataKey="label" tick={AXIS} interval="preserveStartEnd" minTickGap={44} />
        <YAxis tick={AXIS} domain={[0, 100]} width={38} />
        <Tooltip content={<ChartTooltip unit="%" />} />
        <Area
          type="monotone"
          dataKey="utilization"
          name="Utilization"
          stroke="#3DD68C"
          strokeWidth={1.75}
          fill="url(#utilFill)"
          isAnimationActive={false}
        />
      </AreaChart>
    </ResponsiveContainer>
  );
}

/** Runtime vs idle hours, stacked -- shows where the fleet's time actually went. */
export function RuntimeIdleChart({
  data,
  height = 180,
}: {
  data: UtilizationPoint[];
  height?: number;
}) {
  const chartData = data.map((point) => ({
    label: point.label,
    Runtime: point.runtime_hours,
    Idle: point.idle_hours,
  }));

  return (
    <ResponsiveContainer width="100%" height={height}>
      <BarChart data={chartData} margin={{ top: 4, right: 4, left: -18, bottom: 0 }}>
        <CartesianGrid stroke={GRID} strokeDasharray="3 3" vertical={false} />
        <XAxis dataKey="label" tick={AXIS} interval="preserveStartEnd" minTickGap={44} />
        <YAxis tick={AXIS} width={38} />
        <Tooltip content={<ChartTooltip unit="h" />} cursor={{ fill: "#1C1F24" }} />
        <Legend wrapperStyle={{ fontSize: 11, color: "#98A0AD" }} iconType="circle" iconSize={7} />
        <Bar dataKey="Runtime" stackId="a" fill="#3DD68C" isAnimationActive={false} />
        <Bar
          dataKey="Idle"
          stackId="a"
          fill={STEEL}
          radius={[2, 2, 0, 0]}
          isAnimationActive={false}
        />
      </BarChart>
    </ResponsiveContainer>
  );
}

/** Fleet composition by product type: deployed / warehouse / maintenance. */
export function FleetCompositionChart({
  data,
  height = 190,
}: {
  data: ProductTypeStat[];
  height?: number;
}) {
  const chartData = data.map((stat) => ({
    type: productTypeLabel(stat.product_type),
    Deployed: stat.deployed,
    Warehouse: stat.warehouse,
    Maintenance: stat.maintenance,
  }));

  return (
    <ResponsiveContainer width="100%" height={height}>
      <BarChart data={chartData} margin={{ top: 4, right: 4, left: -18, bottom: 0 }}>
        <CartesianGrid stroke={GRID} strokeDasharray="3 3" vertical={false} />
        <XAxis dataKey="type" tick={{ ...AXIS, fontSize: 9 }} interval={0} />
        <YAxis tick={AXIS} width={38} allowDecimals={false} />
        <Tooltip content={<ChartTooltip />} cursor={{ fill: "#1C1F24" }} />
        <Legend wrapperStyle={{ fontSize: 11, color: "#98A0AD" }} iconType="circle" iconSize={7} />
        <Bar dataKey="Deployed" stackId="a" fill="#FFCD11" isAnimationActive={false} />
        <Bar dataKey="Warehouse" stackId="a" fill={STEEL} isAnimationActive={false} />
        <Bar
          dataKey="Maintenance"
          stackId="a"
          fill="#F5A524"
          radius={[2, 2, 0, 0]}
          isAnimationActive={false}
        />
      </BarChart>
    </ResponsiveContainer>
  );
}

/**
 * Forecast timeline for one site + equipment type.
 *
 * The single most important chart in the product, so it is built to be read in
 * one glance rather than decoded:
 *
 *   - grey step area  = machines that will actually BE on site that day,
 *                       stepping down as rentals come off hire
 *   - solid line      = what demand HAS been (history)
 *   - dashed line     = what the model says demand WILL be
 *   - red dot         = a day where forecast demand exceeds projected supply
 *   - "TODAY" rule    = the boundary between measured and predicted
 *
 * History and forecast share the point at TODAY so the line is continuous.
 */
export interface TimelinePoint {
  date: string;
  actual: number | null;
  predicted: number | null;
  available: number | null;
  is_forecast: boolean;
}

export function ForecastTimelineChart({
  points,
  today,
  height = 260,
}: {
  points: TimelinePoint[];
  today: string;
  height?: number;
}) {
  const data = points.map((point) => {
    const short =
      point.predicted !== null &&
      point.available !== null &&
      point.predicted - point.available > 0.05;
    return {
      ...point,
      // Only shortfall days get a scatter dot; nulls are skipped by Recharts.
      shortfallDot: short ? point.predicted : null,
    };
  });

  const dayLabel = (iso: string) => {
    const parsed = new Date(`${iso}T00:00:00`);
    return Number.isNaN(parsed.getTime())
      ? iso
      : parsed.toLocaleDateString(undefined, { day: "2-digit", month: "short" });
  };

  return (
    <ResponsiveContainer width="100%" height={height}>
      <ComposedChart data={data} margin={{ top: 8, right: 8, left: -20, bottom: 0 }}>
        <defs>
          <linearGradient id="supplyFill" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#5B9DFF" stopOpacity={0.18} />
            <stop offset="100%" stopColor="#5B9DFF" stopOpacity={0.02} />
          </linearGradient>
        </defs>

        <CartesianGrid stroke={GRID} strokeDasharray="3 3" vertical={false} />
        <XAxis
          dataKey="date"
          tickFormatter={dayLabel}
          tick={{ ...AXIS, fontSize: 9 }}
          interval="preserveStartEnd"
          minTickGap={28}
        />
        <YAxis tick={AXIS} width={34} allowDecimals={false} />
        <Tooltip content={<ForecastTooltip />} cursor={{ stroke: "#363B44" }} />
        <Legend wrapperStyle={{ fontSize: 11, color: "#98A0AD" }} iconType="plainline" iconSize={14} />

        <ReferenceLine
          x={today}
          stroke="#FFCD11"
          strokeDasharray="2 3"
          strokeOpacity={0.7}
          label={{ value: "TODAY", position: "top", fill: "#FFCD11", fontSize: 9 }}
        />

        <Area
          type="stepAfter"
          dataKey="available"
          name="On site"
          stroke="#5B9DFF"
          strokeWidth={1.5}
          fill="url(#supplyFill)"
          connectNulls
          isAnimationActive={false}
        />
        <Line
          type="monotone"
          dataKey="actual"
          name="Actual demand"
          stroke="#98A0AD"
          strokeWidth={2}
          dot={false}
          isAnimationActive={false}
        />
        <Line
          type="monotone"
          dataKey="predicted"
          name="Forecast demand"
          stroke="#FFCD11"
          strokeWidth={2.25}
          strokeDasharray="5 4"
          dot={false}
          isAnimationActive={false}
        />
        <Scatter
          dataKey="shortfallDot"
          name="Shortfall"
          fill="#F0555A"
          shape="circle"
          isAnimationActive={false}
        />
      </ComposedChart>
    </ResponsiveContainer>
  );
}

function ForecastTooltip({
  active,
  payload,
  label,
}: {
  active?: boolean;
  payload?: { payload: TimelinePoint & { shortfallDot: number | null } }[];
  label?: string;
}) {
  if (!active || !payload?.length) return null;
  const point = payload[0].payload;
  const demand = point.predicted ?? point.actual;
  const gap =
    point.predicted !== null && point.available !== null
      ? point.predicted - point.available
      : null;

  return (
    <div className="bg-elevated border border-borderlight rounded-lg px-3 py-2 shadow-raised min-w-[168px]">
      <div className="text-2xs text-faint mb-1.5 flex items-center justify-between gap-3">
        <span>{label}</span>
        <span className={point.is_forecast ? "text-accent" : "text-muted"}>
          {point.is_forecast ? "forecast" : "actual"}
        </span>
      </div>
      <div className="text-xs text-ink tnum space-y-0.5">
        <div className="flex justify-between gap-4">
          <span className="text-muted">Demand</span>
          <span>{demand !== null ? demand.toFixed(1) : "—"}</span>
        </div>
        <div className="flex justify-between gap-4">
          <span className="text-muted">On site</span>
          <span>{point.available ?? "—"}</span>
        </div>
        {gap !== null && gap > 0.05 && (
          <div className="flex justify-between gap-4 pt-1 mt-1 border-t border-border">
            <span className="text-danger">Short by</span>
            <span className="text-danger font-semibold">{gap.toFixed(1)}</span>
          </div>
        )}
      </div>
    </div>
  );
}

/**
 * Forecast demand vs availability across every site+type, as paired bars.
 * Kept alongside the timeline: the timeline answers "when", this answers
 * "where", and a planner needs both.
 */
export function ForecastChart({
  data,
  height = 200,
}: {
  data: { label: string; demand: number; available: number; shortfall: number }[];
  height?: number;
}) {
  return (
    <ResponsiveContainer width="100%" height={height}>
      <BarChart data={data} margin={{ top: 4, right: 4, left: -18, bottom: 0 }}>
        <CartesianGrid stroke={GRID} strokeDasharray="3 3" vertical={false} />
        <XAxis
          dataKey="label"
          tick={{ ...AXIS, fontSize: 9 }}
          interval={0}
          angle={-25}
          textAnchor="end"
          height={54}
        />
        <YAxis tick={AXIS} width={38} allowDecimals={false} />
        <Tooltip content={<ChartTooltip />} cursor={{ fill: "#1C1F24" }} />
        <Legend wrapperStyle={{ fontSize: 11, color: "#98A0AD" }} iconType="circle" iconSize={7} />
        <Bar
          dataKey="available"
          name="On site"
          fill={STEEL}
          radius={[2, 2, 0, 0]}
          isAnimationActive={false}
        />
        <Bar
          dataKey="demand"
          name="Forecast demand"
          radius={[2, 2, 0, 0]}
          isAnimationActive={false}
        >
          {data.map((entry, index) => (
            // Colour encodes the finding: red means the forecast exceeds stock.
            <Cell key={index} fill={entry.shortfall > 0.05 ? "#F0555A" : "#FFCD11"} />
          ))}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}
