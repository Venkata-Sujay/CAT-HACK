/**
 * Routing and route guards.
 *
 * Guards here are a UX convenience, NOT the security boundary. Tenant isolation
 * is enforced in the backend query layer (app/core/deps.py) -- hiding a nav link
 * protects nothing. These guards exist so a user lands somewhere sensible.
 */

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";

import { AppShell } from "./components/AppShell";
import { AuthProvider, homeRouteFor, useAuth } from "./lib/auth";
import { Login } from "./pages/Login";

import { ClientOverview } from "./pages/client/Overview";
import { ClientAssets } from "./pages/client/Assets";
import { ClientEmployees } from "./pages/client/Employees";
import { ClientAlerts } from "./pages/client/Alerts";
import { ClientRecommendations } from "./pages/client/Recommendations";

import { ControlTower } from "./pages/company/ControlTower";
import { MapSites } from "./pages/company/MapSites";
import { Fleet } from "./pages/company/Fleet";
import { Inventory } from "./pages/company/Inventory";
import { RentalsPage } from "./pages/company/Rentals";
import { CheckInOut } from "./pages/company/CheckInOut";
import { ClientsPage } from "./pages/company/Clients";
import { CompanyAlerts } from "./pages/company/Alerts";
import { Forecasting } from "./pages/company/Forecasting";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      // The simulator changes data constantly, so cached data is stale on
      // arrival. Refetching on mount keeps views honest.
      staleTime: 0,
      retry: 1,
      refetchOnWindowFocus: true,
    },
  },
});

function FullPageSpinner() {
  return (
    <div className="h-full flex items-center justify-center bg-base">
      <span className="w-5 h-5 border-2 border-border border-t-accent rounded-full animate-spin" />
    </div>
  );
}

function RequireAuth({ children, role }: { children: ReactNode; role?: "admin" | "client" }) {
  const { user, loading, isAdmin } = useAuth();

  if (loading) return <FullPageSpinner />;
  if (!user) return <Navigate to="/login" replace />;

  // Wrong-role access redirects to that user's own home rather than showing a
  // "forbidden" page -- the destination is always somewhere they can act.
  if (role === "admin" && !isAdmin) return <Navigate to="/client" replace />;
  if (role === "client" && isAdmin) return <Navigate to="/company" replace />;

  return <AppShell>{children}</AppShell>;
}

function RootRedirect() {
  const { user, loading } = useAuth();
  if (loading) return <FullPageSpinner />;
  return <Navigate to={homeRouteFor(user)} replace />;
}

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <AuthProvider>
          <Routes>
            <Route path="/login" element={<Login />} />

            {/* ---- Client ---- */}
            <Route path="/client" element={<RequireAuth role="client"><ClientOverview /></RequireAuth>} />
            <Route path="/client/assets" element={<RequireAuth role="client"><ClientAssets /></RequireAuth>} />
            <Route path="/client/employees" element={<RequireAuth role="client"><ClientEmployees /></RequireAuth>} />
            <Route path="/client/alerts" element={<RequireAuth role="client"><ClientAlerts /></RequireAuth>} />
            <Route path="/client/recommendations" element={<RequireAuth role="client"><ClientRecommendations /></RequireAuth>} />

            {/* ---- Company ---- */}
            <Route path="/company" element={<RequireAuth role="admin"><ControlTower /></RequireAuth>} />
            <Route path="/company/map" element={<RequireAuth role="admin"><MapSites /></RequireAuth>} />
            <Route path="/company/fleet" element={<RequireAuth role="admin"><Fleet /></RequireAuth>} />
            <Route path="/company/inventory" element={<RequireAuth role="admin"><Inventory /></RequireAuth>} />
            <Route path="/company/rentals" element={<RequireAuth role="admin"><RentalsPage /></RequireAuth>} />
            <Route path="/company/checkinout" element={<RequireAuth role="admin"><CheckInOut /></RequireAuth>} />
            <Route path="/company/clients" element={<RequireAuth role="admin"><ClientsPage /></RequireAuth>} />
            <Route path="/company/alerts" element={<RequireAuth role="admin"><CompanyAlerts /></RequireAuth>} />
            <Route path="/company/forecasting" element={<RequireAuth role="admin"><Forecasting /></RequireAuth>} />

            <Route path="/" element={<RootRedirect />} />
            <Route path="*" element={<RootRedirect />} />
          </Routes>
        </AuthProvider>
      </BrowserRouter>
    </QueryClientProvider>
  );
}
