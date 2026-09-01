/** Client alerts, grouped by severity. */

import { useState } from "react";
import { PageHeader } from "../../components/AppShell";
import { AlertsView } from "../../components/AlertsView";
import { AssetDetailDrawer } from "../../components/AssetDetailDrawer";

export function ClientAlerts() {
  const [selected, setSelected] = useState<number | null>(null);

  return (
    <div className="p-6">
      <PageHeader title="Alerts" subtitle="Issues detected on your equipment" />
      <AlertsView onOpenAsset={setSelected} />
      <AssetDetailDrawer assetId={selected} onClose={() => setSelected(null)} />
    </div>
  );
}
