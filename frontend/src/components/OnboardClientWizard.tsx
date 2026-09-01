/**
 * New-client onboarding wizard.
 *
 * Bringing a customer on is one business event, so it is one form and one API
 * call, not four screens that each half-commit. Three steps only because the
 * information genuinely arrives in three chunks:
 *
 *   1. WHO   -- company details and the portal login they will use
 *   2. WHERE -- the site their equipment goes to, placed on the map
 *   3. WHAT  -- how many of each machine, capped by real depot stock
 *
 * The depot cap is the part worth pointing at. The stepper cannot request more
 * than exists; the backend refuses it again on submit. A rental system that
 * lets you promise equipment you do not have is the problem, not the product.
 */

import { useEffect, useMemo, useState } from "react";
import { equipmentImage } from "../lib/equipment";
import { productTypeLabel } from "../lib/format";
import { useDepotAvailability, useOnboardClient } from "../lib/queries";
import type {
  ClientOnboardingResponse,
  DepotAvailability,
  ProductType,
} from "../lib/types";

const STEPS = ["Company", "Site", "Equipment"] as const;

/** Depot centre. A new site defaults near the operating region, not (0,0). */
const DEFAULT_LAT = 17.45;
const DEFAULT_LNG = 78.4;

interface Draft {
  name: string;
  contactEmail: string;
  contactPhone: string;
  loginEmail: string;
  loginPassword: string;
  loginFullName: string;
  siteName: string;
  siteAddress: string;
  latitude: string;
  longitude: string;
  rentalDays: string;
  quantities: Record<string, number>;
}

const EMPTY: Draft = {
  name: "",
  contactEmail: "",
  contactPhone: "",
  loginEmail: "",
  loginPassword: "",
  loginFullName: "",
  siteName: "",
  siteAddress: "",
  latitude: String(DEFAULT_LAT),
  longitude: String(DEFAULT_LNG),
  rentalDays: "30",
  quantities: {},
};

export function OnboardClientWizard({ onClose }: { onClose: () => void }) {
  const [step, setStep] = useState(0);
  const [draft, setDraft] = useState<Draft>(EMPTY);
  const [result, setResult] = useState<ClientOnboardingResponse | null>(null);

  const { data: depot } = useDepotAvailability();
  const onboard = useOnboardClient();

  const set = <K extends keyof Draft>(key: K, value: Draft[K]) =>
    setDraft((prev) => ({ ...prev, [key]: value }));

  // Close on Escape, like every other overlay in the app.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  const totalUnits = useMemo(
    () => Object.values(draft.quantities).reduce((sum, n) => sum + n, 0),
    [draft.quantities],
  );

  const stepValid = [
    draft.name.trim().length >= 2 &&
      draft.loginFullName.trim().length >= 2 &&
      draft.loginEmail.includes("@") &&
      draft.loginPassword.length >= 8,
    draft.siteName.trim().length >= 2,
    totalUnits > 0,
  ];

  const submit = () => {
    onboard.mutate(
      {
        name: draft.name.trim(),
        contact_email: draft.contactEmail.trim() || undefined,
        contact_phone: draft.contactPhone.trim() || undefined,
        login_email: draft.loginEmail.trim(),
        login_password: draft.loginPassword,
        login_full_name: draft.loginFullName.trim(),
        sites: [
          {
            name: draft.siteName.trim(),
            address: draft.siteAddress.trim() || undefined,
            latitude: Number(draft.latitude) || DEFAULT_LAT,
            longitude: Number(draft.longitude) || DEFAULT_LNG,
          },
        ],
        equipment: Object.entries(draft.quantities)
          .filter(([, qty]) => qty > 0)
          .map(([product_type, quantity]) => ({
            product_type: product_type as ProductType,
            quantity,
          })),
        rental_days: Number(draft.rentalDays) || 30,
      },
      { onSuccess: setResult },
    );
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 animate-fade-in">
      <div className="absolute inset-0 bg-black/70 backdrop-blur-sm" onClick={onClose} />

      <div className="relative w-full max-w-[720px] max-h-[90vh] card rail overflow-hidden flex flex-col shadow-raised">
        {result ? (
          <SuccessPanel result={result} onClose={onClose} />
        ) : (
          <>
            {/* ---- header + stepper ---- */}
            <div className="p-5 pl-6 border-b border-border shrink-0">
              <div className="flex items-start justify-between gap-4">
                <div>
                  <h2 className="text-base font-semibold text-ink">Register a new client</h2>
                  <p className="text-xs text-muted mt-0.5">
                    Creates the account, its portal login, its site, and checks the equipment out —
                    in one step.
                  </p>
                </div>
                <button onClick={onClose} className="btn-ghost px-2 -mt-1" aria-label="Close">
                  ✕
                </button>
              </div>

              <div className="flex items-center gap-1.5 mt-4">
                {STEPS.map((name, index) => (
                  <div key={name} className="flex items-center gap-1.5 flex-1">
                    <button
                      onClick={() => index < step && setStep(index)}
                      disabled={index > step}
                      className={`flex items-center gap-2 text-2xs font-semibold uppercase tracking-wider
                                  transition-colors ${
                                    index === step
                                      ? "text-accent"
                                      : index < step
                                        ? "text-muted hover:text-ink cursor-pointer"
                                        : "text-faint cursor-default"
                                  }`}
                    >
                      <span
                        className={`w-5 h-5 rounded-md flex items-center justify-center text-[10px] ${
                          index === step
                            ? "bg-accent text-base"
                            : index < step
                              ? "bg-ok/20 text-ok"
                              : "bg-elevated text-faint"
                        }`}
                      >
                        {index < step ? "✓" : index + 1}
                      </span>
                      {name}
                    </button>
                    {index < STEPS.length - 1 && (
                      <div
                        className={`flex-1 h-px ${index < step ? "bg-ok/40" : "bg-border"}`}
                      />
                    )}
                  </div>
                ))}
              </div>
            </div>

            {/* ---- body ---- */}
            <div className="p-6 overflow-y-auto flex-1">
              {step === 0 && <CompanyStep draft={draft} set={set} />}
              {step === 1 && <SiteStep draft={draft} set={set} />}
              {step === 2 && (
                <EquipmentStep draft={draft} setDraft={setDraft} depot={depot ?? []} />
              )}

              {onboard.isError && (
                <div className="mt-4 bg-danger/10 border border-danger/25 rounded-lg px-3 py-2.5">
                  <p className="text-xs text-danger">
                    {onboard.error instanceof Error
                      ? onboard.error.message
                      : "Could not register this client"}
                  </p>
                </div>
              )}
            </div>

            {/* ---- footer ---- */}
            <div className="p-4 px-6 border-t border-border flex items-center justify-between gap-3 shrink-0">
              <button
                onClick={() => (step === 0 ? onClose() : setStep(step - 1))}
                className="btn-ghost text-xs"
              >
                {step === 0 ? "Cancel" : "← Back"}
              </button>

              <div className="flex items-center gap-3">
                {step === 2 && totalUnits > 0 && (
                  <span className="text-2xs text-muted tnum">
                    {totalUnits} machine{totalUnits === 1 ? "" : "s"} · {draft.rentalDays} days
                  </span>
                )}
                {step < STEPS.length - 1 ? (
                  <button
                    onClick={() => setStep(step + 1)}
                    disabled={!stepValid[step]}
                    className="btn-primary text-xs"
                  >
                    Continue →
                  </button>
                ) : (
                  <button
                    onClick={submit}
                    disabled={!stepValid[2] || onboard.isPending}
                    className="btn-primary text-xs"
                  >
                    {onboard.isPending ? "Registering…" : "Register client"}
                  </button>
                )}
              </div>
            </div>
          </>
        )}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------

function Field({
  label,
  hint,
  children,
}: {
  label: string;
  hint?: string;
  children: React.ReactNode;
}) {
  return (
    <div>
      <label className="label text-[10px] block mb-1.5">{label}</label>
      {children}
      {hint && <p className="text-2xs text-faint mt-1">{hint}</p>}
    </div>
  );
}

function CompanyStep({
  draft,
  set,
}: {
  draft: Draft;
  set: <K extends keyof Draft>(key: K, value: Draft[K]) => void;
}) {
  return (
    <div className="space-y-4">
      <Field label="Company name">
        <input
          className="input"
          value={draft.name}
          autoFocus
          onChange={(e) => set("name", e.target.value)}
          placeholder="Meridian Infrastructure Pvt Ltd"
        />
      </Field>

      <div className="grid grid-cols-2 gap-3">
        <Field label="Contact email">
          <input
            className="input"
            value={draft.contactEmail}
            onChange={(e) => set("contactEmail", e.target.value)}
            placeholder="ops@meridian.example"
          />
        </Field>
        <Field label="Contact phone">
          <input
            className="input"
            value={draft.contactPhone}
            onChange={(e) => set("contactPhone", e.target.value)}
            placeholder="+91 40 5566 7788"
          />
        </Field>
      </div>

      <div className="pt-4 mt-1 border-t border-border">
        <h3 className="text-sm font-medium text-ink mb-1">Portal login</h3>
        <p className="text-xs text-muted mb-4">
          The credentials this client signs in with. They will see only their own machines,
          operators and alerts — enforced by the API, not by hiding menu items.
        </p>

        <div className="space-y-4">
          <Field label="Account holder">
            <input
              className="input"
              value={draft.loginFullName}
              onChange={(e) => set("loginFullName", e.target.value)}
              placeholder="Priya Rao"
            />
          </Field>
          <div className="grid grid-cols-2 gap-3">
            <Field label="Login email">
              <input
                className="input"
                value={draft.loginEmail}
                onChange={(e) => set("loginEmail", e.target.value)}
                placeholder="ops@meridian.example"
              />
            </Field>
            <Field label="Password" hint="At least 8 characters. Stored hashed, never shown again.">
              <input
                className="input"
                type="password"
                value={draft.loginPassword}
                onChange={(e) => set("loginPassword", e.target.value)}
                placeholder="••••••••"
              />
            </Field>
          </div>
        </div>
      </div>
    </div>
  );
}

function SiteStep({
  draft,
  set,
}: {
  draft: Draft;
  set: <K extends keyof Draft>(key: K, value: Draft[K]) => void;
}) {
  return (
    <div className="space-y-4">
      <p className="text-xs text-muted">
        Where the equipment is going. The site is created against this client and appears on the
        fleet map immediately, with its own code in the SITE-00N sequence.
      </p>

      <Field label="Site name">
        <input
          className="input"
          value={draft.siteName}
          autoFocus
          onChange={(e) => set("siteName", e.target.value)}
          placeholder="Meridian Ring Road Phase 2"
        />
      </Field>

      <Field label="Address">
        <input
          className="input"
          value={draft.siteAddress}
          onChange={(e) => set("siteAddress", e.target.value)}
          placeholder="ORR Exit 14, Hyderabad"
        />
      </Field>

      <div className="grid grid-cols-3 gap-3">
        <Field label="Latitude">
          <input
            className="input tnum"
            value={draft.latitude}
            onChange={(e) => set("latitude", e.target.value)}
          />
        </Field>
        <Field label="Longitude">
          <input
            className="input tnum"
            value={draft.longitude}
            onChange={(e) => set("longitude", e.target.value)}
          />
        </Field>
        <Field label="Rental length" hint="days">
          <input
            className="input tnum"
            type="number"
            min={1}
            max={365}
            value={draft.rentalDays}
            onChange={(e) => set("rentalDays", e.target.value)}
          />
        </Field>
      </div>
    </div>
  );
}

function EquipmentStep({
  draft,
  setDraft,
  depot,
}: {
  draft: Draft;
  setDraft: React.Dispatch<React.SetStateAction<Draft>>;
  depot: DepotAvailability[];
}) {
  const setQty = (type: string, next: number, max: number) =>
    setDraft((prev) => ({
      ...prev,
      quantities: { ...prev.quantities, [type]: Math.max(0, Math.min(max, next)) },
    }));

  return (
    <div>
      <p className="text-xs text-muted mb-4">
        Only what is actually in the depot can be allocated. The counter stops at the stock on
        hand, and the server checks it again on submit.
      </p>

      <div className="space-y-2">
        {depot.map((line) => {
          const qty = draft.quantities[line.product_type] ?? 0;
          const none = line.available === 0;
          return (
            <div
              key={line.product_type}
              className={`flex items-center gap-3 rounded-lg border p-2 pr-3 transition-colors ${
                qty > 0 ? "border-accent/50 bg-accent/5" : "border-border bg-base"
              } ${none ? "opacity-45" : ""}`}
            >
              <img
                src={equipmentImage(line.product_type, "thumb")}
                alt=""
                className="w-16 h-11 rounded object-cover shrink-0"
              />
              <div className="min-w-0 flex-1">
                <div className="text-sm text-ink font-medium">
                  {productTypeLabel(line.product_type)}
                </div>
                <div className="text-2xs text-faint tnum">
                  {none ? (
                    <span className="text-warn">none in depot</span>
                  ) : (
                    <>
                      {line.available} of {line.total} available
                    </>
                  )}
                </div>
              </div>

              <div className="flex items-center gap-1.5 shrink-0">
                <button
                  onClick={() => setQty(line.product_type, qty - 1, line.available)}
                  disabled={qty === 0}
                  className="w-7 h-7 rounded-md border border-border text-muted hover:text-ink
                             hover:border-borderlight disabled:opacity-30 transition-colors"
                  aria-label={`Fewer ${line.product_type}`}
                >
                  −
                </button>
                <span className="w-7 text-center text-sm text-ink tnum font-semibold">{qty}</span>
                <button
                  onClick={() => setQty(line.product_type, qty + 1, line.available)}
                  disabled={qty >= line.available}
                  className="w-7 h-7 rounded-md border border-border text-muted hover:text-ink
                             hover:border-borderlight disabled:opacity-30 transition-colors"
                  aria-label={`More ${line.product_type}`}
                >
                  +
                </button>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

function SuccessPanel({
  result,
  onClose,
}: {
  result: ClientOnboardingResponse;
  onClose: () => void;
}) {
  return (
    <>
      <div className="p-6 pl-7 border-b border-border">
        <div className="flex items-center gap-2.5 mb-2">
          <span className="w-6 h-6 rounded-md bg-ok/20 text-ok flex items-center justify-center text-xs">
            ✓
          </span>
          <h2 className="text-base font-semibold text-ink">{result.client_name} is live</h2>
        </div>
        <p className="text-xs text-muted">
          Tenant <span className="font-mono text-ink">{result.client_code}</span> created with a
          working portal login. Sign out and sign back in as{" "}
          <span className="font-mono text-ink">{result.login_email}</span> to see the client side of
          this same data.
        </p>
      </div>

      <div className="p-6 pl-7 overflow-y-auto flex-1 space-y-5">
        {result.sites.length > 0 && (
          <section>
            <h3 className="label text-[10px] mb-2">Sites created</h3>
            {result.sites.map((site) => (
              <div
                key={site.id}
                className="flex items-center justify-between gap-3 bg-base border border-border rounded-lg px-3 py-2"
              >
                <div>
                  <div className="text-sm text-ink">{site.name}</div>
                  <div className="text-2xs text-faint tnum">
                    {site.latitude.toFixed(4)}, {site.longitude.toFixed(4)}
                  </div>
                </div>
                <span className="font-mono text-xs text-accent">{site.code}</span>
              </div>
            ))}
          </section>
        )}

        {result.allocated.length > 0 && (
          <section>
            <h3 className="label text-[10px] mb-2">
              Equipment checked out · {result.allocated.length}
            </h3>
            <div className="space-y-1.5">
              {result.allocated.map((asset) => (
                <div
                  key={asset.asset_id}
                  className="flex items-center gap-3 bg-base border border-border rounded-lg p-1.5 pr-3"
                >
                  <img
                    src={equipmentImage(asset.product_type, "thumb")}
                    alt=""
                    className="w-12 h-8 rounded object-cover shrink-0"
                  />
                  <span className="font-mono text-xs text-ink">{asset.asset_code}</span>
                  <span className="text-xs text-muted flex-1 truncate">
                    {productTypeLabel(asset.product_type)}
                    {asset.model ? ` · ${asset.model}` : ""}
                  </span>
                  <span className="text-2xs text-faint font-mono">{asset.site_code}</span>
                </div>
              ))}
            </div>
          </section>
        )}

        <section>
          <h3 className="label text-[10px] mb-2">Depot after allocation</h3>
          <div className="grid grid-cols-5 gap-2">
            {result.inventory_after.map((line) => (
              <div
                key={line.product_type}
                className="bg-base border border-border rounded-lg px-2 py-2 text-center"
              >
                <div className="text-lg font-semibold text-ink tnum leading-none">
                  {line.available}
                </div>
                <div className="text-[9px] text-faint mt-1 leading-tight">
                  {productTypeLabel(line.product_type)}
                </div>
              </div>
            ))}
          </div>
        </section>
      </div>

      <div className="p-4 px-6 border-t border-border flex justify-end shrink-0">
        <button onClick={onClose} className="btn-primary text-xs">
          Done
        </button>
      </div>
    </>
  );
}
