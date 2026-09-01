/**
 * Client employee (operator) management.
 *
 * Registering an operator here is what makes the UNAUTHORIZED_OPERATOR alert
 * meaningful: without a registered operator on an asset there is nothing for
 * telemetry's reported operator to disagree with.
 */

import { useState } from "react";
import { PageHeader } from "../../components/AppShell";
import { Card, EmptyState, ErrorState, SectionHeader, Spinner } from "../../components/ui";
import { useCreateEmployee, useEmployees, useUpdateEmployee } from "../../lib/queries";

export function ClientEmployees() {
  const { data, isLoading, error, refetch } = useEmployees();
  const create = useCreateEmployee();
  const update = useUpdateEmployee();

  const [name, setName] = useState("");
  const [phone, setPhone] = useState("");
  const [formError, setFormError] = useState<string | null>(null);

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    setFormError(null);
    create.mutate(
      { name: name.trim(), phone: phone.trim() || undefined },
      {
        onSuccess: () => {
          setName("");
          setPhone("");
        },
        onError: (err) => setFormError(err instanceof Error ? err.message : "Could not add operator"),
      },
    );
  };

  return (
    <div className="p-6">
      <PageHeader
        title="Operators"
        subtitle="Registered operators authorised to run your equipment"
      />

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <Card className="lg:col-span-2" padded={false}>
          <div className="p-4 pb-2">
            <SectionHeader
              title="Registered operators"
              subtitle={data ? `${data.length} on record` : undefined}
            />
          </div>

          {isLoading && <Spinner label="Loading operators…" />}
          {error && <ErrorState error={error} onRetry={() => refetch()} />}
          {data && data.length === 0 && (
            <EmptyState
              title="No operators registered"
              hint="Add an operator to enable unauthorized-operator detection."
            />
          )}

          {data && data.length > 0 && (
            <div className="overflow-x-auto">
              <table className="w-full border-collapse">
                <thead>
                  <tr className="border-b border-border">
                    <th className="th">Code</th>
                    <th className="th">Name</th>
                    <th className="th">Phone</th>
                    <th className="th">Assigned to</th>
                    <th className="th">Status</th>
                    <th className="th"></th>
                  </tr>
                </thead>
                <tbody>
                  {data.map((employee) => (
                    <tr key={employee.id} className="border-b border-border/60 hover:bg-elevated transition-colors">
                      <td className="td font-mono text-xs text-ink">{employee.employee_code}</td>
                      <td className="td text-ink">{employee.name}</td>
                      <td className="td text-muted text-xs">{employee.phone ?? "—"}</td>
                      <td className="td">
                        {employee.assigned_asset_code ? (
                          <span className="font-mono text-xs text-accent">
                            {employee.assigned_asset_code}
                          </span>
                        ) : (
                          <span className="text-faint text-xs">Unassigned</span>
                        )}
                      </td>
                      <td className="td">
                        <span
                          className={`chip ${
                            employee.active
                              ? "bg-ok/15 text-ok border border-ok/25"
                              : "bg-elevated text-faint border border-border"
                          }`}
                        >
                          {employee.active ? "Active" : "Inactive"}
                        </span>
                      </td>
                      <td className="td text-right">
                        <button
                          className="btn-ghost text-xs py-1"
                          disabled={update.isPending}
                          onClick={() =>
                            update.mutate({ id: employee.id, active: !employee.active })
                          }
                        >
                          {employee.active ? "Deactivate" : "Reactivate"}
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Card>

        <Card>
          <SectionHeader title="Add operator" subtitle="A code is generated automatically" />
          <form onSubmit={submit} className="space-y-3">
            <div>
              <label htmlFor="op-name" className="block text-2xs uppercase tracking-wider text-faint mb-1.5">
                Full name
              </label>
              <input
                id="op-name"
                value={name}
                onChange={(e) => setName(e.target.value)}
                className="input"
                placeholder="e.g. Rahul Sharma"
                required
                minLength={2}
              />
            </div>
            <div>
              <label htmlFor="op-phone" className="block text-2xs uppercase tracking-wider text-faint mb-1.5">
                Phone <span className="normal-case tracking-normal">(optional)</span>
              </label>
              <input
                id="op-phone"
                value={phone}
                onChange={(e) => setPhone(e.target.value)}
                className="input"
                placeholder="+91 …"
              />
            </div>

            {formError && (
              <div className="bg-danger/10 border border-danger/25 rounded-md px-3 py-2">
                <p className="text-xs text-danger">{formError}</p>
              </div>
            )}

            <button type="submit" className="btn-primary w-full" disabled={create.isPending || !name.trim()}>
              {create.isPending ? "Adding…" : "Add operator"}
            </button>
          </form>

          <p className="text-2xs text-faint mt-4 leading-relaxed">
            Assign an operator to a machine from that asset's detail panel. If telemetry later
            reports a different operator while the machine is running, a critical alert is raised.
          </p>
        </Card>
      </div>
    </div>
  );
}
