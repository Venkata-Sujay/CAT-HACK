/** Rentals: active, overdue and returned agreements. */

import { useState } from "react";
import { PageHeader } from "../../components/AppShell";
import { AssetDetailDrawer } from "../../components/AssetDetailDrawer";
import { AssetCode, Card, EmptyState, ErrorState, Spinner } from "../../components/ui";
import { formatDate, formatDue, productTypeLabel } from "../../lib/format";
import { useRentals } from "../../lib/queries";

const TABS = [
  { key: "ACTIVE", label: "Active" },
  { key: "OVERDUE", label: "Overdue" },
  { key: "RETURNED", label: "Returned" },
  { key: "", label: "All" },
] as const;

export function RentalsPage() {
  const [tab, setTab] = useState<string>("ACTIVE");
  const [selected, setSelected] = useState<number | null>(null);
  const { data, isLoading, error, refetch } = useRentals(tab || undefined);

  return (
    <div className="p-6">
      <PageHeader title="Rentals" subtitle="Check-out agreements and their return status" />

      <div className="flex items-center gap-1 mb-4 border-b border-border">
        {TABS.map((option) => (
          <button
            key={option.key}
            onClick={() => setTab(option.key)}
            className={`px-3 py-2 text-xs font-medium border-b-2 -mb-px transition-colors ${
              tab === option.key
                ? "border-accent text-accent"
                : "border-transparent text-muted hover:text-ink"
            }`}
          >
            {option.label}
          </button>
        ))}
        {data && <span className="text-xs text-faint ml-auto tnum pb-2">{data.length} rentals</span>}
      </div>

      <Card padded={false}>
        {isLoading && <Spinner label="Loading rentals…" />}
        {error && <ErrorState error={error} onRetry={() => refetch()} />}
        {data && data.length === 0 && <EmptyState title={`No ${tab.toLowerCase() || ""} rentals`} />}

        {data && data.length > 0 && (
          <div className="overflow-x-auto">
            <table className="w-full border-collapse">
              <thead>
                <tr className="border-b border-border">
                  <th className="th">Asset</th>
                  <th className="th">Type</th>
                  <th className="th">Client</th>
                  <th className="th">Site</th>
                  <th className="th">Checked out</th>
                  <th className="th">Expected return</th>
                  <th className="th">Due</th>
                  <th className="th">Status</th>
                  <th className="th text-right">Rate / day</th>
                </tr>
              </thead>
              <tbody>
                {data.map((rental) => {
                  const overdue = rental.status === "OVERDUE";
                  return (
                    <tr
                      key={rental.id}
                      onClick={() => setSelected(rental.asset_id)}
                      className="border-b border-border/60 hover:bg-elevated cursor-pointer transition-colors"
                    >
                      <td className="td">
                        <AssetCode code={rental.asset_code ?? "—"} />
                      </td>
                      <td className="td text-muted">
                        {rental.product_type ? productTypeLabel(rental.product_type) : "—"}
                      </td>
                      <td className="td text-muted max-w-[170px] truncate">{rental.client_name}</td>
                      <td className="td text-muted">{rental.site_code ?? "—"}</td>
                      <td className="td text-muted text-xs">{formatDate(rental.checkout_at)}</td>
                      <td className="td text-muted text-xs">{formatDate(rental.expected_return_at)}</td>
                      <td className="td">
                        <span
                          className={`text-xs tnum ${
                            rental.actual_return_at
                              ? "text-faint"
                              : overdue
                                ? "text-danger font-medium"
                                : rental.hours_until_due !== null && rental.hours_until_due < 48
                                  ? "text-warn"
                                  : "text-muted"
                          }`}
                        >
                          {rental.actual_return_at
                            ? `returned ${formatDate(rental.actual_return_at)}`
                            : formatDue(rental.hours_until_due)}
                        </span>
                      </td>
                      <td className="td">
                        <span
                          className={`chip ${
                            rental.status === "ACTIVE"
                              ? "bg-ok/15 text-ok border border-ok/25"
                              : rental.status === "OVERDUE"
                                ? "bg-danger/15 text-danger border border-danger/30"
                                : "bg-elevated text-muted border border-border"
                          }`}
                        >
                          {rental.status}
                        </span>
                      </td>
                      <td className="td text-right text-muted tnum">
                        ₹{rental.rental_rate.toLocaleString()}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      <AssetDetailDrawer assetId={selected} onClose={() => setSelected(null)} />
    </div>
  );
}
