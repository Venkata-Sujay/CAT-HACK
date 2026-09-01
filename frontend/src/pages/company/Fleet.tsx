/** Company fleet view -- every asset across every client. */

import { useState } from "react";
import { useSearchParams } from "react-router-dom";
import { PageHeader } from "../../components/AppShell";
import { AssetDetailDrawer } from "../../components/AssetDetailDrawer";
import { AssetFilters, AssetTable } from "../../components/AssetTable";
import { Card, EmptyState, ErrorState, Spinner } from "../../components/ui";
import { useAssets, useSites } from "../../lib/queries";
import type { ProductType } from "../../lib/types";

export function Fleet() {
  // The control-tower map deep-links here with ?site=<id>, so the site filter
  // initialises from the URL.
  const [searchParams, setSearchParams] = useSearchParams();
  const [status, setStatus] = useState("");
  const [productType, setProductType] = useState("");
  const [siteId, setSiteId] = useState(searchParams.get("site") ?? "");
  const [search, setSearch] = useState("");
  const [selected, setSelected] = useState<number | null>(null);

  const { data, isLoading, error, refetch } = useAssets({
    status: status || undefined,
    product_type: (productType as ProductType) || undefined,
    site_id: siteId ? Number(siteId) : undefined,
    q: search || undefined,
  });
  const { data: sites } = useSites();

  const handleSiteChange = (value: string) => {
    setSiteId(value);
    if (value) setSearchParams({ site: value });
    else setSearchParams({});
  };

  return (
    <div className="p-6">
      <PageHeader title="Fleet" subtitle="Every asset across all clients and sites" />

      <AssetFilters
        status={status}
        onStatus={setStatus}
        productType={productType}
        onProductType={setProductType}
        siteId={siteId}
        onSiteId={handleSiteChange}
        search={search}
        onSearch={setSearch}
        sites={sites}
        resultCount={data?.total}
      />

      <Card padded={false}>
        {isLoading && <Spinner label="Loading fleet…" />}
        {error && <ErrorState error={error} onRetry={() => refetch()} />}
        {data && data.items.length === 0 && (
          <EmptyState title="No assets match these filters" hint="Try clearing the filters." />
        )}
        {data && data.items.length > 0 && (
          <AssetTable assets={data.items} onSelect={setSelected} showClient />
        )}
      </Card>

      <AssetDetailDrawer assetId={selected} onClose={() => setSelected(null)} />
    </div>
  );
}
