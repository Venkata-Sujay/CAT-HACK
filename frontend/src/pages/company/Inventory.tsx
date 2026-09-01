/** Inventory: stock levels by equipment type, plus adding an asset to the fleet. */

import { useState } from "react";
import { PageHeader } from "../../components/AppShell";
import { FleetCompositionChart } from "../../components/Charts";
import { Card, ErrorState, SectionHeader, Spinner, UtilizationBar } from "../../components/ui";
import { productTypeLabel } from "../../lib/format";
import { useCompanyDashboard, useCreateAsset } from "../../lib/queries";
import type { ProductType } from "../../lib/types";

const PRODUCT_TYPES: ProductType[] = [
  "EXCAVATOR",
  "BULLDOZER",
  "CRANE",
  "GRADER",
  "WHEEL_LOADER",
];

export function Inventory() {
  const { data, isLoading, error, refetch } = useCompanyDashboard();
  const [showForm, setShowForm] = useState(false);

  if (isLoading) return <div className="p-6"><Spinner label="Loading inventory…" /></div>;
  if (error) return <div className="p-6"><ErrorState error={error} onRetry={() => refetch()} /></div>;
  if (!data) return null;

  const { by_product_type, kpis } = data;

  return (
    <div className="p-6">
      <PageHeader
        title="Inventory"
        subtitle={`${kpis.total_fleet} machines across ${by_product_type.length} equipment types`}
        actions={
          <button className="btn-primary text-xs py-1.5" onClick={() => setShowForm((v) => !v)}>
            {showForm ? "Cancel" : "Add asset"}
          </button>
        }
      />

      {showForm && (
        <div className="mb-5">
          <AddAssetForm onDone={() => setShowForm(false)} />
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4 mb-5">
        <Card className="lg:col-span-2" padded={false}>
          <div className="p-4 pb-2">
            <SectionHeader title="Stock by equipment type" />
          </div>
          <div className="overflow-x-auto">
            <table className="w-full border-collapse">
              <thead>
                <tr className="border-b border-border">
                  <th className="th">Type</th>
                  <th className="th text-right">Total</th>
                  <th className="th text-right">Deployed</th>
                  <th className="th text-right">Warehouse</th>
                  <th className="th text-right">Maintenance</th>
                  <th className="th text-right">Active</th>
                  <th className="th">Utilization</th>
                </tr>
              </thead>
              <tbody>
                {by_product_type.map((stat) => (
                  <tr key={stat.product_type} className="border-b border-border/60 hover:bg-elevated transition-colors">
                    <td className="td text-ink font-medium">{productTypeLabel(stat.product_type)}</td>
                    <td className="td text-right text-ink tnum">{stat.total}</td>
                    <td className="td text-right text-accent tnum">{stat.deployed}</td>
                    <td className="td text-right text-muted tnum">{stat.warehouse}</td>
                    <td className="td text-right tnum">
                      <span className={stat.maintenance > 0 ? "text-warn" : "text-faint"}>
                        {stat.maintenance}
                      </span>
                    </td>
                    <td className="td text-right text-ok tnum">{stat.active}</td>
                    <td className="td w-32">
                      <UtilizationBar value={stat.utilization} />
                    </td>
                  </tr>
                ))}
              </tbody>
              <tfoot>
                <tr className="border-t border-border bg-base/50">
                  <td className="td text-ink font-semibold">Total</td>
                  <td className="td text-right text-ink font-semibold tnum">{kpis.total_fleet}</td>
                  <td className="td text-right text-accent font-semibold tnum">
                    {by_product_type.reduce((sum, s) => sum + s.deployed, 0)}
                  </td>
                  <td className="td text-right text-muted font-semibold tnum">
                    {by_product_type.reduce((sum, s) => sum + s.warehouse, 0)}
                  </td>
                  <td className="td text-right text-warn font-semibold tnum">
                    {by_product_type.reduce((sum, s) => sum + s.maintenance, 0)}
                  </td>
                  <td className="td text-right text-ok font-semibold tnum">
                    {by_product_type.reduce((sum, s) => sum + s.active, 0)}
                  </td>
                  <td className="td" />
                </tr>
              </tfoot>
            </table>
          </div>
        </Card>

        <Card>
          <SectionHeader title="Composition" subtitle="Deployed vs available stock" />
          <FleetCompositionChart data={by_product_type} height={240} />
        </Card>
      </div>
    </div>
  );
}

function AddAssetForm({ onDone }: { onDone: () => void }) {
  const create = useCreateAsset();
  const [productType, setProductType] = useState<ProductType>("EXCAVATOR");
  const [model, setModel] = useState("");
  const [rate, setRate] = useState("18500");
  const [error, setError] = useState<string | null>(null);

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    create.mutate(
      {
        product_type: productType,
        model: model.trim() || undefined,
        daily_rate: Number(rate) || 0,
      },
      {
        onSuccess: onDone,
        onError: (err) => setError(err instanceof Error ? err.message : "Could not add asset"),
      },
    );
  };

  return (
    <Card>
      <SectionHeader
        title="Add asset to fleet"
        subtitle="An EQX code and QR token are generated automatically"
      />
      <form onSubmit={submit} className="flex flex-wrap items-end gap-3">
        <div className="w-44">
          <label className="block text-2xs uppercase tracking-wider text-faint mb-1.5">Type</label>
          <select
            value={productType}
            onChange={(e) => setProductType(e.target.value as ProductType)}
            className="input"
          >
            {PRODUCT_TYPES.map((type) => (
              <option key={type} value={type}>
                {productTypeLabel(type)}
              </option>
            ))}
          </select>
        </div>

        <div className="w-48">
          <label className="block text-2xs uppercase tracking-wider text-faint mb-1.5">
            Model <span className="normal-case tracking-normal">(optional)</span>
          </label>
          <input value={model} onChange={(e) => setModel(e.target.value)} className="input" placeholder="e.g. CAT 320" />
        </div>

        <div className="w-36">
          <label className="block text-2xs uppercase tracking-wider text-faint mb-1.5">Daily rate</label>
          <input
            type="number"
            min={0}
            value={rate}
            onChange={(e) => setRate(e.target.value)}
            className="input tnum"
          />
        </div>

        <button type="submit" className="btn-primary" disabled={create.isPending}>
          {create.isPending ? "Adding…" : "Add asset"}
        </button>
      </form>

      {error && <p className="text-xs text-danger mt-3">{error}</p>}
    </Card>
  );
}
