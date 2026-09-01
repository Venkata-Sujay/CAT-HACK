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
  // Two deep links land here: the control-tower map sends ?site=<id>, and the
  // equipment strip sends ?type=<PRODUCT_TYPE>. Both filters initialise from
  // the URL so the destination arrives already narrowed.
  const [searchParams, setSearchParams] = useSearchParams();
  const [status, setStatus] = useState("");
  const [productType, setProductType] = useState(searchParams.get("type") ?? "");
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

  /** Keep the URL in step with the filters so a view stays shareable. */
  const syncUrl = (next: { site?: string; type?: string }) => {
    const params: Record<string, string> = {};
    const site = next.site ?? siteId;
    const type = next.type ?? productType;
    if (site) params.site = site;
    if (type) params.type = type;
    setSearchParams(params);
  };

  const handleSiteChange = (value: string) => {
    setSiteId(value);
    syncUrl({ site: value });
  };

  const handleTypeChange = (value: string) => {
    setProductType(value);
    syncUrl({ type: value });
  };

  return (
    <div className="p-6">
      <PageHeader title="Fleet" subtitle="Every asset across all clients and sites" />

      <AssetFilters
        status={status}
        onStatus={setStatus}
        productType={productType}
        onProductType={handleTypeChange}
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
