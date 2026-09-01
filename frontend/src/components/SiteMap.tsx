/**
 * Leaflet site map.
 *
 * OpenStreetMap tiles specifically because they need no API key -- a key wall
 * or quota error would take the map out of the demo. The default tiles are
 * bright, so they are CSS-filtered to dark in index.css rather than swapped for
 * a dark tile provider that would need an account.
 */

import { useEffect, useMemo } from "react";
import { MapContainer, Marker, Popup, TileLayer, useMap } from "react-leaflet";
import L from "leaflet";
import "leaflet/dist/leaflet.css";
import type { SiteWithStats } from "../lib/types";
import { percent } from "../lib/format";

/**
 * Build a marker as an inline SVG divIcon.
 *
 * Leaflet's default marker images break under bundlers (the PNG URLs resolve
 * relative to the CSS, not the bundle). A divIcon avoids that entirely and lets
 * the marker carry live data: deployed count in the badge, colour by severity.
 */
function siteIcon(site: SiteWithStats): L.DivIcon {
  const hasAnomalies = site.anomaly_count > 0;
  const color = site.is_warehouse ? "#6B7688" : hasAnomalies ? "#F0555A" : "#FFCD11";
  const ring = hasAnomalies ? "#F0555A" : "#FFCD11";

  return L.divIcon({
    className: "",
    html: `
      <div style="position:relative;display:flex;align-items:center;justify-content:center;">
        ${
          hasAnomalies
            ? `<span style="position:absolute;width:44px;height:44px;border-radius:50%;
                 background:${ring};opacity:0.18;animation:pulse-dot 2s ease-in-out infinite;"></span>`
            : ""
        }
        <div style="
          width:30px;height:30px;border-radius:50%;
          background:${color};border:2px solid #0A0B0D;
          display:flex;align-items:center;justify-content:center;
          font:600 11px/1 Inter,sans-serif;color:#0A0B0D;
          box-shadow:0 2px 8px rgba(0,0,0,0.5);position:relative;">
          ${site.deployed_assets}
        </div>
        ${
          hasAnomalies
            ? `<div style="position:absolute;top:-3px;right:-3px;width:14px;height:14px;
                 border-radius:50%;background:#F0555A;border:2px solid #0A0B0D;
                 font:700 8px/10px Inter,sans-serif;color:#fff;text-align:center;">
                 ${site.anomaly_count}
               </div>`
            : ""
        }
      </div>`,
    iconSize: [30, 30],
    iconAnchor: [15, 15],
  });
}

/** Fit the viewport to the markers whenever the set of sites changes. */
function FitBounds({ sites }: { sites: SiteWithStats[] }) {
  const map = useMap();
  useEffect(() => {
    if (sites.length === 0) return;
    const bounds = L.latLngBounds(sites.map((s) => [s.latitude, s.longitude] as [number, number]));
    map.fitBounds(bounds, { padding: [50, 50], maxZoom: 12 });
  }, [map, sites]);
  return null;
}

export function SiteMap({
  sites,
  onSelectSite,
  height = "100%",
  /** Embedded maps must not eat the page scroll. Full-page maps should. */
  scrollWheelZoom = false,
}: {
  sites: SiteWithStats[];
  onSelectSite?: (siteId: number) => void;
  height?: string | number;
  scrollWheelZoom?: boolean;
}) {
  // Fall back to the depot region if there is nothing to fit to yet.
  const center = useMemo<[number, number]>(() => {
    if (sites.length === 0) return [17.47, 78.44];
    const lat = sites.reduce((sum, s) => sum + s.latitude, 0) / sites.length;
    const lng = sites.reduce((sum, s) => sum + s.longitude, 0) / sites.length;
    return [lat, lng];
  }, [sites]);

  return (
    <div style={{ height }} className="relative rounded-lg overflow-hidden border border-border">
      {!scrollWheelZoom && (
        <div
          className="absolute bottom-2 left-2 z-[400] pointer-events-none rounded-md
                     bg-surface/85 border border-border px-2 py-1 text-2xs text-faint backdrop-blur"
        >
          Use + / − to zoom
        </div>
      )}
      <MapContainer
        center={center}
        zoom={10}
        style={{ height: "100%", width: "100%" }}
        zoomControl
        scrollWheelZoom={scrollWheelZoom}
      >
        <TileLayer
          url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
          attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
        />
        <FitBounds sites={sites} />

        {sites.map((site) => (
          <Marker key={site.id} position={[site.latitude, site.longitude]} icon={siteIcon(site)}>
            <Popup>
              <div className="min-w-[190px]">
                <div className="flex items-center gap-2 mb-1.5">
                  <span className="font-mono text-xs font-semibold text-ink">{site.code}</span>
                  {site.is_warehouse && (
                    <span className="chip bg-elevated text-muted border border-border">Depot</span>
                  )}
                </div>
                <div className="text-xs text-muted mb-2.5">{site.name}</div>

                <div className="grid grid-cols-2 gap-x-3 gap-y-1 text-xs">
                  <span className="text-faint">Deployed</span>
                  <span className="text-ink tnum text-right">{site.deployed_assets}</span>
                  <span className="text-faint">Active</span>
                  <span className="text-ok tnum text-right">{site.active_assets}</span>
                  <span className="text-faint">Idle</span>
                  <span className="text-neutral tnum text-right">{site.idle_assets}</span>
                  <span className="text-faint">Utilization</span>
                  <span className="text-ink tnum text-right">{percent(site.utilization)}</span>
                  {site.anomaly_count > 0 && (
                    <>
                      <span className="text-danger">Anomalies</span>
                      <span className="text-danger tnum text-right font-semibold">
                        {site.anomaly_count}
                      </span>
                    </>
                  )}
                </div>

                {onSelectSite && (
                  <button
                    onClick={() => onSelectSite(site.id)}
                    className="btn-secondary text-xs py-1 w-full mt-2.5"
                  >
                    View assets
                  </button>
                )}
              </div>
            </Popup>
          </Marker>
        ))}
      </MapContainer>
    </div>
  );
}
