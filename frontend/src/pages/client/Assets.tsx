/** Client asset list -- filterable view of the tenant's own equipment. */

import { useState } from "react";
import { useSearchParams } from "react-router-dom";
import { PageHeader } from "../../components/AppShell";
import { AssetDetailDrawer } from "../../components/AssetDetailDrawer";
import { AssetFilters, AssetTable } from "../../components/AssetTable";
import { Card, EmptyState, ErrorState, Spinner } from "../../components/ui";
import { useAssets, useSites } from "../../lib/queries";
import type { ProductType } from "../../lib/types";

export function ClientAssets() {
  // The overview's equipment strip deep-links here with ?type=<PRODUCT_TYPE>.
  const [searchParams, setSearchParams] = useSearchParams();
  const [status, setStatus] = useState("");
  const [productType, setProductType] = useState(searchParams.get("type") ?? "");
  const [siteId, setSiteId] = useState("");
  const [search, setSearch] = useState("");
  const [selected, setSelected] = useState<number | null>(null);

  const { data, isLoading, error, refetch } = useAssets({
    status: status || undefined,
    product_type: (productType as ProductType) || undefined,
    site_id: siteId ? Number(siteId) : undefined,
    q: search || undefined,
  });
  const { data: sites } = useSites();

  return (
    <div className="p-6">
      <PageHeader title="My equipment" subtitle="Machines currently on hire to your organisation" />

      <AssetFilters
        status={status}
        onStatus={setStatus}
        productType={productType}
        onProductType={(value) => {
          setProductType(value);
          setSearchParams(value ? { type: value } : {});
        }}
        siteId={siteId}
        onSiteId={setSiteId}
        search={search}
        onSearch={setSearch}
        sites={sites}
        resultCount={data?.total}
      />

      <Card padded={false}>
        {isLoading && <Spinner label="Loading assets…" />}
        {error && <ErrorState error={error} onRetry={() => refetch()} />}
        {data && data.items.length === 0 && (
          <EmptyState
            title="No assets match these filters"
            hint="Clear the filters to see your full fleet."
          />
        )}
        {data && data.items.length > 0 && (
          <AssetTable assets={data.items} onSelect={setSelected} />
        )}
      </Card>

      <AssetDetailDrawer assetId={selected} onClose={() => setSelected(null)} />
    </div>
  );
}
