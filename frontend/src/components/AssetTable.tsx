/**
 * Asset table, shared by the client asset list and the company fleet view.
 *
 * `showClient` is the only difference between the two: a client already knows
 * the assets are theirs, so the column would be noise.
 */

import {
  AssetCode,
  FuelBar,
  HealthDot,
  SeverityChip,
  StatusChip,
  UtilizationBar,
} from "./ui";
import { formatDue, minutesToHours, productTypeLabel } from "../lib/format";
import type { Asset } from "../lib/types";

export function AssetTable({
  assets,
  onSelect,
  showClient = false,
}: {
  assets: Asset[];
  onSelect: (assetId: number) => void;
  showClient?: boolean;
}) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full border-collapse">
        <thead>
          <tr className="border-b border-border">
            <th className="th">Asset</th>
            <th className="th">Type</th>
            {showClient && <th className="th">Client</th>}
            <th className="th">Site</th>
            <th className="th">Operator</th>
            <th className="th">Status</th>
            <th className="th">Runtime</th>
            <th className="th">Idle</th>
            <th className="th">Utilization</th>
            <th className="th">Fuel</th>
            <th className="th">Condition</th>
            <th className="th">Due</th>
            <th className="th">Alerts</th>
          </tr>
        </thead>
        <tbody>
          {assets.map((asset) => (
            <tr
              key={asset.id}
              onClick={() => onSelect(asset.id)}
              className="border-b border-border/60 hover:bg-elevated cursor-pointer transition-colors"
            >
              <td className="td">
                <div className="flex items-center gap-2">
                  <span
                    className={`w-1.5 h-1.5 rounded-full shrink-0 ${
                      asset.is_running ? "bg-ok animate-pulse-dot" : "bg-faint"
                    }`}
                    title={asset.is_running ? "Running" : "Stopped"}
                  />
                  <AssetCode code={asset.asset_code} />
                </div>
              </td>

              <td className="td text-muted">{productTypeLabel(asset.product_type)}</td>

              {showClient && (
                <td className="td text-muted max-w-[150px] truncate">{asset.client_name ?? "—"}</td>
              )}

              <td className="td">
                {asset.site_code ? (
                  <span className="text-muted">{asset.site_code}</span>
                ) : (
                  // No site on a rented machine is itself the finding, so it is
                  // called out rather than shown as a blank cell.
                  <span className="text-danger text-xs font-medium">No site</span>
                )}
              </td>

              <td className="td">
                {asset.assigned_employee_code ? (
                  <div className="flex items-center gap-1.5">
                    <span className="text-muted text-xs font-mono">
                      {asset.assigned_employee_code}
                    </span>
                    {!asset.operator_match && (
                      <span
                        className="chip bg-danger/15 text-danger border border-danger/30"
                        title={`Telemetry reports ${asset.current_operator_code ?? "an unregistered operator"}`}
                      >
                        Mismatch
                      </span>
                    )}
                  </div>
                ) : (
                  <span className="text-faint text-xs">Unassigned</span>
                )}
              </td>

              <td className="td">
                <StatusChip status={asset.status} />
              </td>

              <td className="td text-muted tnum">{minutesToHours(asset.runtime_minutes_today)}</td>
              <td className="td text-muted tnum">{minutesToHours(asset.idle_minutes_today)}</td>

              <td className="td">
                <UtilizationBar value={asset.utilization} />
              </td>

              <td className="td">
                <FuelBar level={asset.fuel_level} />
              </td>

              <td className="td">
                <div className="flex items-center gap-3">
                  <HealthDot state={asset.tire_condition} label="Tire" />
                  <HealthDot state={asset.engine_condition} label="Eng" />
                </div>
              </td>

              <td className="td">
                <span
                  className={`text-xs tnum ${
                    asset.hours_until_due === null
                      ? "text-faint"
                      : asset.hours_until_due < 0
                        ? "text-danger font-medium"
                        : asset.hours_until_due < 48
                          ? "text-warn"
                          : "text-muted"
                  }`}
                >
                  {formatDue(asset.hours_until_due)}
                </span>
              </td>

              <td className="td">
                {asset.alert_count > 0 && asset.max_severity ? (
                  <div className="flex items-center gap-1.5">
                    <SeverityChip severity={asset.max_severity} />
                    {asset.alert_count > 1 && (
                      <span className="text-2xs text-faint tnum">+{asset.alert_count - 1}</span>
                    )}
                  </div>
                ) : (
                  <span className="text-faint text-xs">—</span>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/** Filter bar shared by the asset list views. */
export function AssetFilters({
  status,
  onStatus,
  productType,
  onProductType,
  siteId,
  onSiteId,
  search,
  onSearch,
  sites,
  resultCount,
}: {
  status: string;
  onStatus: (value: string) => void;
  productType: string;
  onProductType: (value: string) => void;
  siteId: string;
  onSiteId: (value: string) => void;
  search: string;
  onSearch: (value: string) => void;
  sites?: { id: number; code: string; name: string }[];
  resultCount?: number;
}) {
  const selectClass =
    "bg-base border border-border rounded-md px-2.5 py-1.5 text-xs text-ink focus:border-accent/50 transition-colors";

  const hasFilters = status || productType || siteId || search;

  return (
    <div className="flex flex-wrap items-center gap-2 mb-3">
      <input
        value={search}
        onChange={(e) => onSearch(e.target.value)}
        placeholder="Search asset code or model…"
        className={`${selectClass} w-56 placeholder:text-faint`}
      />

      <select value={status} onChange={(e) => onStatus(e.target.value)} className={selectClass}>
        <option value="">All statuses</option>
        <option value="ACTIVE">Active</option>
        <option value="IDLE">Idle</option>
        <option value="RENTED">Rented</option>
        <option value="OVERDUE">Overdue</option>
        <option value="AVAILABLE">Available</option>
        <option value="MAINTENANCE">Maintenance</option>
      </select>

      <select
        value={productType}
        onChange={(e) => onProductType(e.target.value)}
        className={selectClass}
      >
        <option value="">All types</option>
        <option value="EXCAVATOR">Excavator</option>
        <option value="BULLDOZER">Bulldozer</option>
        <option value="CRANE">Crane</option>
        <option value="GRADER">Grader</option>
        <option value="WHEEL_LOADER">Wheel Loader</option>
      </select>

      {sites && sites.length > 0 && (
        <select value={siteId} onChange={(e) => onSiteId(e.target.value)} className={selectClass}>
          <option value="">All sites</option>
          {sites.map((site) => (
            <option key={site.id} value={site.id}>
              {site.code} — {site.name}
            </option>
          ))}
        </select>
      )}

      {hasFilters && (
        <button
          onClick={() => {
            onStatus("");
            onProductType("");
            onSiteId("");
            onSearch("");
          }}
          className="btn-ghost text-xs py-1.5"
        >
          Clear
        </button>
      )}

      {resultCount !== undefined && (
        <span className="text-xs text-faint ml-auto tnum">{resultCount} assets</span>
      )}
    </div>
  );
}
