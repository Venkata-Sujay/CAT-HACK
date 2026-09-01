/** Company alerts -- the full action queue across every client. */

import { useState } from "react";
import { PageHeader } from "../../components/AppShell";
import { AlertsView } from "../../components/AlertsView";
import { AssetDetailDrawer } from "../../components/AssetDetailDrawer";

export function CompanyAlerts() {
  const [selected, setSelected] = useState<number | null>(null);

  return (
    <div className="p-6">
      <PageHeader
        title="Action queue"
        subtitle="Every open finding across the fleet, highest severity first"
      />
      <AlertsView onOpenAsset={setSelected} />
      <AssetDetailDrawer assetId={selected} onClose={() => setSelected(null)} />
    </div>
  );
}
