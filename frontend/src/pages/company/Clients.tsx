/** Client (tenant) roster with per-client rollups. */

import { PageHeader } from "../../components/AppShell";
import { Card, EmptyState, ErrorState, Spinner, UtilizationBar } from "../../components/ui";
import { percent } from "../../lib/format";
import { useClients } from "../../lib/queries";

export function ClientsPage() {
  const { data, isLoading, error, refetch } = useClients();

  return (
    <div className="p-6">
      <PageHeader title="Clients" subtitle="Tenants renting equipment, with live rollups" />

      {isLoading && <Card><Spinner label="Loading clients…" /></Card>}
      {error && <Card><ErrorState error={error} onRetry={() => refetch()} /></Card>}
      {data && data.length === 0 && <Card><EmptyState title="No clients on record" /></Card>}

      {data && data.length > 0 && (
        <>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-5">
            {data.map((client) => (
              <Card key={client.id}>
                <div className="flex items-start justify-between gap-3 mb-3">
                  <div className="min-w-0">
                    <h3 className="text-sm font-semibold text-ink truncate">{client.name}</h3>
                    <p className="text-2xs text-faint font-mono mt-0.5">{client.code}</p>
                  </div>
                  {client.critical_alerts > 0 && (
                    <span className="chip bg-danger/15 text-danger border border-danger/30 shrink-0">
                      {client.critical_alerts} critical
                    </span>
                  )}
                </div>

                <div className="grid grid-cols-3 gap-3 mb-3">
                  <div>
                    <div className="text-2xs text-faint mb-0.5">Assets</div>
                    <div className="text-lg font-semibold text-ink tnum leading-none">
                      {client.rented_assets}
                    </div>
                  </div>
                  <div>
                    <div className="text-2xs text-faint mb-0.5">Operators</div>
                    <div className="text-lg font-semibold text-ink tnum leading-none">
                      {client.employees}
                    </div>
                  </div>
                  <div>
                    <div className="text-2xs text-faint mb-0.5">Open alerts</div>
                    <div
                      className={`text-lg font-semibold tnum leading-none ${
                        client.open_alerts > 0 ? "text-warn" : "text-ink"
                      }`}
                    >
                      {client.open_alerts}
                    </div>
                  </div>
                </div>

                <div className="mb-2">
                  <div className="text-2xs text-faint mb-1">
                    Fleet utilization · {percent(client.avg_utilization)}
                  </div>
                  <UtilizationBar value={client.avg_utilization} />
                </div>

                {client.contact_email && (
                  <p className="text-2xs text-faint mt-3 pt-3 border-t border-border truncate">
                    {client.contact_email}
                  </p>
                )}
              </Card>
            ))}
          </div>

          <Card padded={false}>
            <div className="overflow-x-auto">
              <table className="w-full border-collapse">
                <thead>
                  <tr className="border-b border-border">
                    <th className="th">Client</th>
                    <th className="th">Code</th>
                    <th className="th text-right">Assets on rental</th>
                    <th className="th text-right">Operators</th>
                    <th className="th text-right">Open alerts</th>
                    <th className="th text-right">Critical</th>
                    <th className="th">Utilization</th>
                    <th className="th">Contact</th>
                  </tr>
                </thead>
                <tbody>
                  {data.map((client) => (
                    <tr key={client.id} className="border-b border-border/60 hover:bg-elevated transition-colors">
                      <td className="td text-ink font-medium">{client.name}</td>
                      <td className="td font-mono text-xs text-muted">{client.code}</td>
                      <td className="td text-right text-ink tnum">{client.rented_assets}</td>
                      <td className="td text-right text-muted tnum">{client.employees}</td>
                      <td className="td text-right tnum">
                        <span className={client.open_alerts > 0 ? "text-warn" : "text-faint"}>
                          {client.open_alerts}
                        </span>
                      </td>
                      <td className="td text-right tnum">
                        <span className={client.critical_alerts > 0 ? "text-danger" : "text-faint"}>
                          {client.critical_alerts}
                        </span>
                      </td>
                      <td className="td w-32">
                        <UtilizationBar value={client.avg_utilization} />
                      </td>
                      <td className="td text-muted text-xs">{client.contact_email ?? "—"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Card>
        </>
      )}
    </div>
  );
}
