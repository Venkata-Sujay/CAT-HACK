/**
 * Login.
 *
 * Two jobs, in this order:
 *   1. Say what this product IS, in one sentence, over a photograph of the
 *      thing it manages. A judge or a new user meeting the system here should
 *      not have to sign in before understanding it.
 *   2. Get out of the way. Demo credentials are one click -- typing them on
 *      stage wastes time and invites typos.
 */

import { useState } from "react";
import { Navigate, useNavigate } from "react-router-dom";
import { CatBadge } from "../components/Brand";
import { HERO_IMAGE } from "../lib/equipment";
import { homeRouteFor, useAuth } from "../lib/auth";

const DEMO_ACCOUNTS = [
  {
    email: "admin@rental.local",
    label: "Company Admin",
    sub: "Whole fleet, every client",
    tone: "accent" as const,
  },
  { email: "client1@demo.local", label: "Acme Construction", sub: "Client", tone: "muted" as const },
  { email: "client2@demo.local", label: "Northstar Mining", sub: "Client", tone: "muted" as const },
  {
    email: "client3@demo.local",
    label: "Vertex Infrastructure",
    sub: "Client",
    tone: "muted" as const,
  },
];

const DEMO_PASSWORD = "demo1234";

const CAPABILITIES = [
  "Live location and telemetry for every machine",
  "QR check-in / check-out with a full audit trail",
  "Misuse and under-utilization detected automatically",
  "Demand forecast to pre-position stock before it is needed",
];

export function Login() {
  const { user, loading, login } = useAuth();
  const navigate = useNavigate();

  const [email, setEmail] = useState("admin@rental.local");
  const [password, setPassword] = useState(DEMO_PASSWORD);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  if (loading) {
    return (
      <div className="h-full flex items-center justify-center bg-base">
        <span className="w-5 h-5 border-2 border-border border-t-accent rounded-full animate-spin" />
      </div>
    );
  }
  if (user) return <Navigate to={homeRouteFor(user)} replace />;

  const signIn = async (accountEmail: string, accountPassword: string) => {
    setError(null);
    setSubmitting(true);
    try {
      const loggedIn = await login(accountEmail.trim(), accountPassword);
      navigate(homeRouteFor(loggedIn), { replace: true });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Sign-in failed");
    } finally {
      setSubmitting(false);
    }
  };

  const quickLogin = (accountEmail: string) => {
    setEmail(accountEmail);
    setPassword(DEMO_PASSWORD);
    void signIn(accountEmail, DEMO_PASSWORD);
  };

  return (
    <div className="h-full flex bg-base">
      {/* ---- Brand panel ---- */}
      <div className="hidden lg:flex relative flex-1 min-w-0">
        <img
          src={HERO_IMAGE}
          alt="Excavator working on a quarry face"
          className="absolute inset-0 w-full h-full object-cover object-[68%_center]"
        />
        {/* Enough darkening for the copy to sit on, not so much that the
            machine disappears -- the photograph is doing half the explaining. */}
        <div className="absolute inset-0 bg-gradient-to-r from-base via-base/72 to-base/10" />
        <div className="absolute inset-0 bg-gradient-to-t from-base/85 via-transparent to-base/45" />

        <div className="relative flex flex-col justify-between p-10 xl:p-14 max-w-[560px]">
          <CatBadge height={26} />

          <div>
            <div className="w-20 h-1.5 bg-hazard mb-6 rounded-sm" />
            <h1 className="text-[34px] xl:text-[40px] font-semibold text-ink leading-[1.08] tracking-tight">
              Every machine.
              <br />
              Every site.
              <br />
              <span className="text-accent">In real time.</span>
            </h1>
            <p className="text-sm text-muted leading-relaxed mt-5 max-w-md">
              Rental fleets are still run on spreadsheets — equipment goes missing, sits idle, and
              comes back late. This turns the telemetry those machines already produce into
              decisions somebody can act on today.
            </p>

            <ul className="mt-7 space-y-2.5">
              {CAPABILITIES.map((line) => (
                <li key={line} className="flex items-start gap-2.5 text-sm text-muted">
                  <span className="mt-[7px] w-1.5 h-1.5 rounded-full bg-accent shrink-0" />
                  {line}
                </li>
              ))}
            </ul>
          </div>

          <div className="flex items-center gap-2 text-2xs font-semibold tracking-[0.18em] uppercase">
            {["Telemetry", "Platform", "Intelligence", "Action"].map((stage, index) => (
              <div key={stage} className="flex items-center gap-2">
                <span className={index === 3 ? "text-accent" : "text-faint"}>{stage}</span>
                {index < 3 && <span className="text-border">→</span>}
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* ---- Form ---- */}
      <div className="w-full lg:w-[440px] shrink-0 flex items-center justify-center p-6 border-l border-border bg-surface">
        <div className="w-full max-w-[352px]">
          <div className="lg:hidden mb-6">
            <CatBadge height={22} />
          </div>

          <h2 className="text-lg font-semibold text-ink">Sign in</h2>
          <p className="text-xs text-muted mt-1 mb-6">
            Fleet control tower, or a client account.
          </p>

          <form
            onSubmit={(e) => {
              e.preventDefault();
              void signIn(email, password);
            }}
            className="space-y-3.5"
          >
            <div>
              <label htmlFor="email" className="label text-[10px] block mb-1.5">
                Email
              </label>
              <input
                id="email"
                type="text"
                autoComplete="username"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                className="input"
                required
              />
            </div>

            <div>
              <label htmlFor="password" className="label text-[10px] block mb-1.5">
                Password
              </label>
              <input
                id="password"
                type="password"
                autoComplete="current-password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                className="input"
                required
              />
            </div>

            {error && (
              <div className="bg-danger/10 border border-danger/25 rounded-lg px-3 py-2">
                <p className="text-xs text-danger">{error}</p>
              </div>
            )}

            <button type="submit" disabled={submitting} className="btn-primary w-full">
              {submitting ? "Signing in…" : "Sign in"}
            </button>
          </form>

          <div className="mt-6 pt-5 border-t border-border">
            <div className="label text-[10px] mb-2.5">
              Demo accounts · password {DEMO_PASSWORD}
            </div>
            <div className="space-y-1.5">
              {DEMO_ACCOUNTS.map((account) => (
                <button
                  key={account.email}
                  onClick={() => quickLogin(account.email)}
                  disabled={submitting}
                  className={`w-full flex items-center justify-between gap-3 px-3 py-2 rounded-lg
                             bg-base border transition-colors text-left disabled:opacity-50 ${
                               account.tone === "accent"
                                 ? "border-accent/40 hover:border-accent/70 hover:bg-accent/5"
                                 : "border-border hover:border-borderlight hover:bg-elevated"
                             }`}
                >
                  <div className="min-w-0">
                    <div className="text-xs font-medium text-ink truncate">{account.label}</div>
                    <div className="text-2xs text-faint truncate">{account.email}</div>
                  </div>
                  <span
                    className={`text-2xs shrink-0 ${
                      account.tone === "accent" ? "text-accent" : "text-faint"
                    }`}
                  >
                    {account.sub}
                  </span>
                </button>
              ))}
            </div>
            <p className="text-2xs text-faint mt-3 leading-relaxed">
              Development-only credentials for the seeded demo dataset.
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}
