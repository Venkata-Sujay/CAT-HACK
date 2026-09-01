/**
 * Check-in / check-out console.
 *
 * A mandatory problem-statement requirement. Flow: scan or type an asset code,
 * the backend resolves it and tells us whether it is currently on rental, and
 * the panel switches between check-out and check-in accordingly.
 *
 * QR/RFID is SIMULATED. `GET /rentals/lookup/{code}` accepts either a printed
 * asset code or a QR token, so a "scan" and a manual entry take exactly the
 * same backend path -- no divergence between the two input methods. Wiring a
 * real camera scanner is a nice-to-have that would not change this flow.
 */

import { useState } from "react";
import { PageHeader } from "../../components/AppShell";
import {
  AssetCode,
  Card,
  EmptyState,
  FuelBar,
  HealthDot,
  SectionHeader,
  StatusChip,
} from "../../components/ui";
import { formatDateTime, formatDue, minutesToHours, productTypeLabel } from "../../lib/format";
import {
  useAssetLookup,
  useCheckin,
  useCheckout,
  useClients,
  useEmployees,
  useSites,
} from "../../lib/queries";
import type { AssetLookupResponse, HealthState } from "../../lib/types";

export function CheckInOut() {
  const [code, setCode] = useState("");
  const [result, setResult] = useState<AssetLookupResponse | null>(null);
  const [banner, setBanner] = useState<{ kind: "ok" | "error"; text: string } | null>(null);

  const lookup = useAssetLookup();

  const runLookup = (value: string) => {
    const query = value.trim();
    if (!query) return;
    setBanner(null);
    lookup.mutate(query, {
      onSuccess: (data) => setResult(data),
      onError: (err) => {
        setResult(null);
        setBanner({ kind: "error", text: err instanceof Error ? err.message : "Lookup failed" });
      },
    });
  };

  const reset = () => {
    setResult(null);
    setCode("");
  };

  return (
    <div className="p-6">
      <PageHeader
        title="Check-In / Check-Out"
        subtitle="Scan or enter an asset code to start. QR/RFID is simulated — both inputs resolve through the same endpoint."
      />

      {banner && (
        <div
          className={`mb-4 rounded-md border px-3 py-2.5 ${
            banner.kind === "ok"
              ? "bg-ok/10 border-ok/25 text-ok"
              : "bg-danger/10 border-danger/25 text-danger"
          }`}
        >
          <p className="text-sm">{banner.text}</p>
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-5 gap-4">
        {/* ---- Scanner ---- */}
        <Card className="lg:col-span-2">
          <SectionHeader title="Identify asset" subtitle="Asset code or QR token" />

          <form
            onSubmit={(e) => {
              e.preventDefault();
              runLookup(code);
            }}
            className="space-y-3"
          >
            <div className="relative">
              <input
                value={code}
                onChange={(e) => setCode(e.target.value)}
                placeholder="EQX1007 or QR-EQX1007-…"
                className="input font-mono pr-9"
                autoFocus
              />
              <svg
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="1.75"
                strokeLinecap="round"
                className="w-4 h-4 text-faint absolute right-3 top-1/2 -translate-y-1/2"
              >
                <path d="M3 8V5a2 2 0 012-2h3M16 3h3a2 2 0 012 2v3M21 16v3a2 2 0 01-2 2h-3M8 21H5a2 2 0 01-2-2v-3M3 12h18" />
              </svg>
            </div>

            <div className="flex gap-2">
              <button type="submit" className="btn-primary flex-1" disabled={lookup.isPending || !code.trim()}>
                {lookup.isPending ? "Looking up…" : "Look up"}
              </button>
              {result && (
                <button type="button" className="btn-secondary" onClick={reset}>
                  Clear
                </button>
              )}
            </div>
          </form>

          <div className="mt-4 pt-4 border-t border-border">
            <div className="text-2xs uppercase tracking-wider text-faint mb-2">
              Simulated scan — demo shortcuts
            </div>
            <div className="flex flex-wrap gap-1.5">
              {["EQX1007", "EQX1012", "EQX1021", "EQX1045"].map((demoCode) => (
                <button
                  key={demoCode}
                  onClick={() => {
                    setCode(demoCode);
                    runLookup(demoCode);
                  }}
                  className="px-2 py-1 rounded border border-border bg-base hover:border-accent/40
                             hover:bg-elevated transition-colors font-mono text-xs text-muted"
                >
                  {demoCode}
                </button>
              ))}
            </div>
            <p className="text-2xs text-faint mt-2.5 leading-relaxed">
              Each button stands in for a physical QR scan. A real scanner would post the same code
              to the same endpoint.
            </p>
          </div>
        </Card>

        {/* ---- Action panel ---- */}
        <div className="lg:col-span-3">
          {!result ? (
            <Card>
              <EmptyState
                title="No asset selected"
                hint="Scan or enter an asset code to check equipment in or out."
              />
            </Card>
          ) : result.active_rental ? (
            <CheckinPanel
              result={result}
              onDone={(message) => {
                setBanner({ kind: "ok", text: message });
                reset();
              }}
              onError={(message) => setBanner({ kind: "error", text: message })}
            />
          ) : (
            <CheckoutPanel
              result={result}
              onDone={(message) => {
                setBanner({ kind: "ok", text: message });
                reset();
              }}
              onError={(message) => setBanner({ kind: "error", text: message })}
            />
          )}
        </div>
      </div>
    </div>
  );
}

/** Compact asset summary shown above both panels. */
function AssetSummary({ result }: { result: AssetLookupResponse }) {
  const { asset } = result;
  return (
    <div className="bg-base border border-border rounded-md p-3 mb-4">
      <div className="flex items-center justify-between gap-3 mb-2.5">
        <div className="flex items-center gap-2.5">
          <AssetCode code={asset.asset_code} className="text-base" />
          <StatusChip status={asset.status} />
        </div>
        <span className="text-xs text-muted">{productTypeLabel(asset.product_type)}</span>
      </div>
      <div className="grid grid-cols-4 gap-3 text-xs">
        <div>
          <div className="text-2xs text-faint mb-0.5">Fuel</div>
          <FuelBar level={asset.fuel_level} />
        </div>
        <div>
          <div className="text-2xs text-faint mb-0.5">Condition</div>
          <div className="flex gap-2.5">
            <HealthDot state={asset.tire_condition} label="Tire" />
            <HealthDot state={asset.engine_condition} label="Eng" />
          </div>
        </div>
        <div>
          <div className="text-2xs text-faint mb-0.5">Runtime today</div>
          <div className="text-ink tnum">{minutesToHours(asset.runtime_minutes_today)}</div>
        </div>
        <div>
          <div className="text-2xs text-faint mb-0.5">Site</div>
          <div className="text-ink">{asset.site_code ?? "—"}</div>
        </div>
      </div>
    </div>
  );
}

function CheckoutPanel({
  result,
  onDone,
  onError,
}: {
  result: AssetLookupResponse;
  onDone: (message: string) => void;
  onError: (message: string) => void;
}) {
  const { asset } = result;
  const checkout = useCheckout();
  const { data: clients } = useClients();
  const { data: sites } = useSites();

  const [clientId, setClientId] = useState("");
  const [siteId, setSiteId] = useState("");
  const [employeeId, setEmployeeId] = useState("");
  // Default to two weeks out -- the most common rental length in the seed data.
  const [dueDate, setDueDate] = useState(() => {
    const date = new Date();
    date.setDate(date.getDate() + 14);
    return date.toISOString().slice(0, 10);
  });

  // Operator list depends on the client chosen, so it is fetched reactively.
  const { data: employees } = useEmployees(clientId ? Number(clientId) : undefined);

  const canSubmit = Boolean(clientId && dueDate);
  const workSites = (sites ?? []).filter((site) => !site.is_warehouse);

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    checkout.mutate(
      {
        asset_id: asset.id,
        client_id: Number(clientId),
        site_id: siteId ? Number(siteId) : null,
        employee_id: employeeId ? Number(employeeId) : null,
        // Send end-of-day so a same-day return date is still in the future.
        expected_return_at: new Date(`${dueDate}T17:00:00`).toISOString(),
      },
      {
        onSuccess: () => onDone(`${asset.asset_code} checked out successfully.`),
        onError: (err) => onError(err instanceof Error ? err.message : "Check-out failed"),
      },
    );
  };

  if (asset.status === "MAINTENANCE") {
    return (
      <Card>
        <SectionHeader title="Check out" />
        <AssetSummary result={result} />
        <div className="bg-warn/10 border border-warn/25 rounded-md px-3 py-2.5">
          <p className="text-sm text-warn">
            {asset.asset_code} is in maintenance and cannot be rented out. Complete maintenance from
            the asset panel first.
          </p>
        </div>
      </Card>
    );
  }

  return (
    <Card>
      <SectionHeader title="Check out" subtitle="Assign this machine to a client and site" />
      <AssetSummary result={result} />

      <form onSubmit={submit} className="grid grid-cols-2 gap-3">
        <div>
          <label className="block text-2xs uppercase tracking-wider text-faint mb-1.5">
            Client <span className="text-danger">*</span>
          </label>
          <select
            value={clientId}
            onChange={(e) => {
              setClientId(e.target.value);
              setEmployeeId("");
            }}
            className="input"
            required
          >
            <option value="">Select client…</option>
            {(clients ?? []).map((client) => (
              <option key={client.id} value={client.id}>
                {client.name}
              </option>
            ))}
          </select>
        </div>

        <div>
          <label className="block text-2xs uppercase tracking-wider text-faint mb-1.5">Site</label>
          <select value={siteId} onChange={(e) => setSiteId(e.target.value)} className="input">
            <option value="">No site assigned</option>
            {workSites.map((site) => (
              <option key={site.id} value={site.id}>
                {site.code} — {site.name}
              </option>
            ))}
          </select>
        </div>

        <div>
          <label className="block text-2xs uppercase tracking-wider text-faint mb-1.5">
            Operator
          </label>
          <select
            value={employeeId}
            onChange={(e) => setEmployeeId(e.target.value)}
            className="input"
            disabled={!clientId}
          >
            <option value="">{clientId ? "No operator assigned" : "Select a client first"}</option>
            {(employees ?? [])
              .filter((employee) => employee.active)
              .map((employee) => (
                <option key={employee.id} value={employee.id}>
                  {employee.employee_code} — {employee.name}
                </option>
              ))}
          </select>
        </div>

        <div>
          <label className="block text-2xs uppercase tracking-wider text-faint mb-1.5">
            Expected return <span className="text-danger">*</span>
          </label>
          <input
            type="date"
            value={dueDate}
            onChange={(e) => setDueDate(e.target.value)}
            className="input"
            required
          />
        </div>

        <div className="col-span-2 flex items-center gap-3 pt-1">
          <button type="submit" className="btn-primary" disabled={!canSubmit || checkout.isPending}>
            {checkout.isPending ? "Checking out…" : "Confirm check-out"}
          </button>
          {(!siteId || !employeeId) && (
            <p className="text-2xs text-warn">
              Without a site and operator this machine will raise an "unaccounted for" alert.
            </p>
          )}
        </div>
      </form>
    </Card>
  );
}

function CheckinPanel({
  result,
  onDone,
  onError,
}: {
  result: AssetLookupResponse;
  onDone: (message: string) => void;
  onError: (message: string) => void;
}) {
  const { asset, active_rental: rental } = result;
  const checkin = useCheckin();

  const [notes, setNotes] = useState("");
  const [tire, setTire] = useState<HealthState>(asset.tire_condition);
  const [engine, setEngine] = useState<HealthState>(asset.engine_condition);
  const [toMaintenance, setToMaintenance] = useState(false);

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    checkin.mutate(
      {
        asset_id: asset.id,
        condition_notes: notes.trim() || undefined,
        tire_condition: tire,
        engine_condition: engine,
        send_to_maintenance: toMaintenance,
      },
      {
        onSuccess: () => onDone(`${asset.asset_code} checked in and returned to the warehouse.`),
        onError: (err) => onError(err instanceof Error ? err.message : "Check-in failed"),
      },
    );
  };

  const healthOptions: HealthState[] = ["GOOD", "WARNING", "CRITICAL"];
  const overdue = rental!.hours_until_due !== null && rental!.hours_until_due < 0;

  return (
    <Card>
      <SectionHeader title="Check in" subtitle="Close the rental and record returned condition" />
      <AssetSummary result={result} />

      <div className="bg-base border border-border rounded-md p-3 mb-4">
        <div className="grid grid-cols-3 gap-3 text-xs">
          <div>
            <div className="text-2xs text-faint mb-0.5">Client</div>
            <div className="text-ink">{rental!.client_name}</div>
          </div>
          <div>
            <div className="text-2xs text-faint mb-0.5">Checked out</div>
            <div className="text-ink">{formatDateTime(rental!.checkout_at)}</div>
          </div>
          <div>
            <div className="text-2xs text-faint mb-0.5">Due</div>
            <div className={overdue ? "text-danger font-medium" : "text-ink"}>
              {formatDue(rental!.hours_until_due)}
            </div>
          </div>
        </div>
      </div>

      <form onSubmit={submit} className="space-y-3">
        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="block text-2xs uppercase tracking-wider text-faint mb-1.5">
              Tire condition on return
            </label>
            <select value={tire} onChange={(e) => setTire(e.target.value as HealthState)} className="input">
              {healthOptions.map((option) => (
                <option key={option} value={option}>
                  {option}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className="block text-2xs uppercase tracking-wider text-faint mb-1.5">
              Engine condition on return
            </label>
            <select value={engine} onChange={(e) => setEngine(e.target.value as HealthState)} className="input">
              {healthOptions.map((option) => (
                <option key={option} value={option}>
                  {option}
                </option>
              ))}
            </select>
          </div>
        </div>

        <div>
          <label className="block text-2xs uppercase tracking-wider text-faint mb-1.5">
            Condition notes
          </label>
          <textarea
            value={notes}
            onChange={(e) => setNotes(e.target.value)}
            rows={2}
            className="input resize-none"
            placeholder="Any damage, wear or issues observed on return…"
          />
        </div>

        <label className="flex items-center gap-2 text-xs text-muted cursor-pointer">
          <input
            type="checkbox"
            checked={toMaintenance}
            onChange={(e) => setToMaintenance(e.target.checked)}
            className="accent-accent"
          />
          Send directly to maintenance instead of the available pool
        </label>

        <p className="text-2xs text-faint leading-relaxed">
          A machine returned in CRITICAL condition is routed to maintenance automatically. The
          inspector's assessment here is the only way component health returns to GOOD — telemetry
          can only degrade it.
        </p>

        <button type="submit" className="btn-primary" disabled={checkin.isPending}>
          {checkin.isPending ? "Checking in…" : "Confirm check-in"}
        </button>
      </form>
    </Card>
  );
}
