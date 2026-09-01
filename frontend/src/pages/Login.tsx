/** Login. Demo credentials are one click away -- typing them on stage wastes time. */

import { useState } from "react";
import { Navigate, useNavigate } from "react-router-dom";
import { homeRouteFor, useAuth } from "../lib/auth";

const DEMO_ACCOUNTS = [
  { email: "admin@rental.local", label: "Company Admin", sub: "Fleet control tower" },
  { email: "client1@demo.local", label: "Acme Construction", sub: "Client account" },
  { email: "client2@demo.local", label: "Northstar Mining", sub: "Client account" },
  { email: "client3@demo.local", label: "Vertex Infrastructure", sub: "Client account" },
];

const DEMO_PASSWORD = "demo1234";

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

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      const loggedIn = await login(email.trim(), password);
      navigate(homeRouteFor(loggedIn), { replace: true });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Sign-in failed");
    } finally {
      setSubmitting(false);
    }
  };

  const quickLogin = async (accountEmail: string) => {
    setEmail(accountEmail);
    setPassword(DEMO_PASSWORD);
    setError(null);
    setSubmitting(true);
    try {
      const loggedIn = await login(accountEmail, DEMO_PASSWORD);
      navigate(homeRouteFor(loggedIn), { replace: true });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Sign-in failed");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="h-full flex items-center justify-center bg-base p-6">
      <div className="w-full max-w-[880px] grid md:grid-cols-2 gap-6">
        {/* ---- Brand panel ---- */}
        <div className="hidden md:flex flex-col justify-center pr-4">
          <div className="flex items-center gap-3 mb-6">
            <div className="w-10 h-10 rounded-lg bg-accent flex items-center justify-center">
              <svg viewBox="0 0 24 24" fill="none" className="w-6 h-6">
                <path
                  d="M4 17h3l2-9 3 12 3-9 2 6h3"
                  stroke="#0B0E13"
                  strokeWidth="2.2"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                />
              </svg>
            </div>
            <div>
              <h1 className="text-xl font-semibold text-ink leading-tight">Smart Rental</h1>
              <p className="text-sm text-muted leading-tight">Tracking System</p>
            </div>
          </div>

          <p className="text-sm text-muted leading-relaxed mb-6">
            Turn rental telemetry into operational decisions. Track equipment in real time, detect
            misuse and under-utilization, and forecast what each site will need next.
          </p>

          <div className="flex items-center gap-2 text-2xs font-medium tracking-wide">
            {["TELEMETRY", "PLATFORM", "INTELLIGENCE", "ACTION"].map((stage, index) => (
              <div key={stage} className="flex items-center gap-2">
                <span className={index === 3 ? "text-accent" : "text-faint"}>{stage}</span>
                {index < 3 && <span className="text-border">→</span>}
              </div>
            ))}
          </div>
        </div>

        {/* ---- Form ---- */}
        <div className="card p-6">
          <h2 className="text-base font-semibold text-ink mb-1">Sign in</h2>
          <p className="text-xs text-muted mb-5">Access the fleet control tower or a client account.</p>

          <form onSubmit={submit} className="space-y-3.5">
            <div>
              <label htmlFor="email" className="block text-2xs uppercase tracking-wider text-faint mb-1.5">
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
              <label htmlFor="password" className="block text-2xs uppercase tracking-wider text-faint mb-1.5">
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
              <div className="bg-danger/10 border border-danger/25 rounded-md px-3 py-2">
                <p className="text-xs text-danger">{error}</p>
              </div>
            )}

            <button type="submit" disabled={submitting} className="btn-primary w-full">
              {submitting ? "Signing in…" : "Sign in"}
            </button>
          </form>

          <div className="mt-5 pt-4 border-t border-border">
            <div className="text-2xs uppercase tracking-wider text-faint mb-2.5">
              Demo accounts · password {DEMO_PASSWORD}
            </div>
            <div className="space-y-1.5">
              {DEMO_ACCOUNTS.map((account) => (
                <button
                  key={account.email}
                  onClick={() => quickLogin(account.email)}
                  disabled={submitting}
                  className="w-full flex items-center justify-between gap-3 px-2.5 py-2 rounded-md
                             bg-base border border-border hover:border-accent/40 hover:bg-elevated
                             transition-colors text-left disabled:opacity-50"
                >
                  <div className="min-w-0">
                    <div className="text-xs font-medium text-ink truncate">{account.label}</div>
                    <div className="text-2xs text-faint truncate">{account.email}</div>
                  </div>
                  <span className="text-2xs text-faint shrink-0">{account.sub}</span>
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
