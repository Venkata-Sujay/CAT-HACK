/** Shared chart components. Recharts, themed to the dark palette. */

import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { ChartTooltip } from "./AssetDetailDrawer";
import { productTypeLabel } from "../lib/format";
import type { ProductTypeStat, UtilizationPoint } from "../lib/types";

const AXIS = { fill: "#5C6678", fontSize: 10 };
const GRID = "#242B38";

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
            <stop offset="0%" stopColor="#22C55E" stopOpacity={0.32} />
            <stop offset="100%" stopColor="#22C55E" stopOpacity={0} />
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
          stroke="#22C55E"
          strokeWidth={1.75}
          fill="url(#utilFill)"
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
        <Tooltip content={<ChartTooltip unit="h" />} />
        <Legend wrapperStyle={{ fontSize: 11, color: "#8D97AA" }} iconType="circle" iconSize={7} />
        <Bar dataKey="Runtime" stackId="a" fill="#22C55E" radius={[0, 0, 0, 0]} />
        <Bar dataKey="Idle" stackId="a" fill="#334155" radius={[2, 2, 0, 0]} />
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
        <XAxis dataKey="type" tick={AXIS} interval={0} />
        <YAxis tick={AXIS} width={38} allowDecimals={false} />
        <Tooltip content={<ChartTooltip />} cursor={{ fill: "#1A1F28" }} />
        <Legend wrapperStyle={{ fontSize: 11, color: "#8D97AA" }} iconType="circle" iconSize={7} />
        <Bar dataKey="Deployed" stackId="a" fill="#FFB020" />
        <Bar dataKey="Warehouse" stackId="a" fill="#334155" />
        <Bar dataKey="Maintenance" stackId="a" fill="#F59E0B" radius={[2, 2, 0, 0]} />
      </BarChart>
    </ResponsiveContainer>
  );
}

/** Forecast demand vs availability. Bars turn red where a shortfall exists. */
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
        <XAxis dataKey="label" tick={{ ...AXIS, fontSize: 9 }} interval={0} angle={-25} textAnchor="end" height={54} />
        <YAxis tick={AXIS} width={38} allowDecimals={false} />
        <Tooltip content={<ChartTooltip />} cursor={{ fill: "#1A1F28" }} />
        <Legend wrapperStyle={{ fontSize: 11, color: "#8D97AA" }} iconType="circle" iconSize={7} />
        <Bar dataKey="available" name="Available" fill="#334155" radius={[2, 2, 0, 0]} />
        <Bar dataKey="demand" name="Forecast demand" radius={[2, 2, 0, 0]}>
          {data.map((entry, index) => (
            // Colour encodes the finding: red means the forecast exceeds stock.
            <Cell key={index} fill={entry.shortfall > 0 ? "#EF4444" : "#FFB020"} />
          ))}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}
