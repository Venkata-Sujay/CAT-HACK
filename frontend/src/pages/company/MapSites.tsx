/** Full-screen site map with a site list and an add-site form. */

import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { PageHeader } from "../../components/AppShell";
import { SiteMap } from "../../components/SiteMap";
import { Card, ErrorState, SectionHeader, Spinner, UtilizationBar } from "../../components/ui";
import { percent } from "../../lib/format";
import { useCreateSite, useSites } from "../../lib/queries";

export function MapSites() {
  const { data: sites, isLoading, error, refetch } = useSites();
  const [showForm, setShowForm] = useState(false);
  const navigate = useNavigate();

  if (isLoading) return <div className="p-6"><Spinner label="Loading sites…" /></div>;
  if (error) return <div className="p-6"><ErrorState error={error} onRetry={() => refetch()} /></div>;

  return (
    <div className="p-6">
      <PageHeader
        title="Map & Sites"
        subtitle={`${sites?.length ?? 0} locations. Markers show deployed asset counts; red badges mark open anomalies.`}
        actions={
          <button className="btn-primary text-xs py-1.5" onClick={() => setShowForm((v) => !v)}>
            {showForm ? "Cancel" : "Add site"}
          </button>
        }
      />

      {showForm && (
        <div className="mb-4">
          <AddSiteForm onDone={() => setShowForm(false)} />
        </div>
      )}

      <div className="grid grid-cols-1 xl:grid-cols-3 gap-4">
        <div className="xl:col-span-2">
          {/* Wheel zoom is ON here and OFF on the embedded control-tower map:
              this page is the map, so the wheel belongs to it. */}
          <SiteMap
            sites={sites ?? []}
            height={560}
            scrollWheelZoom
            onSelectSite={(siteId) => navigate(`/company/fleet?site=${siteId}`)}
          />
        </div>

        <Card padded={false} className="max-h-[560px] overflow-y-auto">
          <div className="p-4 pb-2 sticky top-0 bg-surface z-10 border-b border-border">
            <SectionHeader title="Sites" subtitle="Click through to the assets deployed there" />
          </div>
          <div className="p-3 space-y-2">
            {(sites ?? []).map((site) => (
              <button
                key={site.id}
                onClick={() => navigate(`/company/fleet?site=${site.id}`)}
                className="w-full text-left bg-base border border-border rounded-md p-3
                           hover:border-accent/40 hover:bg-elevated transition-colors"
              >
                <div className="flex items-center justify-between gap-2 mb-1.5">
                  <div className="flex items-center gap-2">
                    <span className="font-mono text-xs font-semibold text-ink">{site.code}</span>
                    {site.is_warehouse && (
                      <span className="chip bg-elevated text-muted border border-border">Depot</span>
                    )}
                  </div>
                  {site.anomaly_count > 0 && (
                    <span className="chip bg-danger/15 text-danger border border-danger/30">
                      {site.anomaly_count} alert{site.anomaly_count > 1 ? "s" : ""}
                    </span>
                  )}
                </div>

                <div className="text-xs text-muted mb-2 truncate">{site.name}</div>

                <div className="flex items-center gap-4 text-2xs mb-2">
                  <span className="text-faint">
                    Deployed <span className="text-ink tnum">{site.deployed_assets}</span>
                  </span>
                  <span className="text-faint">
                    Active <span className="text-ok tnum">{site.active_assets}</span>
                  </span>
                  <span className="text-faint">
                    Idle <span className="text-neutral tnum">{site.idle_assets}</span>
                  </span>
                </div>

                <UtilizationBar value={site.utilization} />
                <div className="text-2xs text-faint mt-1">{percent(site.utilization)} utilization</div>
              </button>
            ))}
          </div>
        </Card>
      </div>
    </div>
  );
}

function AddSiteForm({ onDone }: { onDone: () => void }) {
  const create = useCreateSite();
  const [code, setCode] = useState("");
  const [name, setName] = useState("");
  const [address, setAddress] = useState("");
  // Default to the depot region so a new marker lands somewhere visible.
  const [latitude, setLatitude] = useState("17.4700");
  const [longitude, setLongitude] = useState("78.4400");
  const [error, setError] = useState<string | null>(null);

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    create.mutate(
      {
        code: code.trim().toUpperCase(),
        name: name.trim(),
        address: address.trim() || undefined,
        latitude: Number(latitude),
        longitude: Number(longitude),
      },
      {
        onSuccess: onDone,
        onError: (err) => setError(err instanceof Error ? err.message : "Could not create site"),
      },
    );
  };

  return (
    <Card>
      <SectionHeader title="Add site" subtitle="Coordinates place the marker on the map" />
      <form onSubmit={submit} className="flex flex-wrap items-end gap-3">
        <div className="w-32">
          <label className="block text-2xs uppercase tracking-wider text-faint mb-1.5">Code</label>
          <input
            value={code}
            onChange={(e) => setCode(e.target.value)}
            className="input font-mono"
            placeholder="SITE-004"
            required
            minLength={2}
          />
        </div>
        <div className="w-56">
          <label className="block text-2xs uppercase tracking-wider text-faint mb-1.5">Name</label>
          <input
            value={name}
            onChange={(e) => setName(e.target.value)}
            className="input"
            placeholder="e.g. Eastern Ring Road"
            required
            minLength={2}
          />
        </div>
        <div className="w-56">
          <label className="block text-2xs uppercase tracking-wider text-faint mb-1.5">Address</label>
          <input value={address} onChange={(e) => setAddress(e.target.value)} className="input" />
        </div>
        <div className="w-28">
          <label className="block text-2xs uppercase tracking-wider text-faint mb-1.5">Latitude</label>
          <input
            type="number"
            step="0.0001"
            min={-90}
            max={90}
            value={latitude}
            onChange={(e) => setLatitude(e.target.value)}
            className="input tnum"
            required
          />
        </div>
        <div className="w-28">
          <label className="block text-2xs uppercase tracking-wider text-faint mb-1.5">Longitude</label>
          <input
            type="number"
            step="0.0001"
            min={-180}
            max={180}
            value={longitude}
            onChange={(e) => setLongitude(e.target.value)}
            className="input tnum"
            required
          />
        </div>
        <button type="submit" className="btn-primary" disabled={create.isPending}>
          {create.isPending ? "Creating…" : "Create site"}
        </button>
      </form>
      {error && <p className="text-xs text-danger mt-3">{error}</p>}
    </Card>
  );
}
