/**
 * TanStack Query hooks.
 *
 * "Realtime" is polling: `refetchInterval` on the live views. This is a
 * deliberate choice over WebSockets -- it reconnects for free, survives a
 * backend restart mid-demo, and has no socket lifecycle to get wrong. At a 5s
 * interval the latency is invisible to a viewer.
 */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, qs } from "./api";
import type {
  Alert,
  AlertSeverity,
  AssetDetail,
  AssetEvent,
  AssetLookupResponse,
  ClientDashboard,
  ClientRow,
  CompanyDashboard,
  Employee,
  EmployeeWithAssignment,
  Forecast,
  HealthResponse,
  Page,
  ProductType,
  Recommendation,
  Rental,
  SimulatorStatus,
  Site,
  SiteWithStats,
  TelemetryPoint,
  Asset,
} from "./types";

/** Poll cadence for live views. */
export const LIVE_POLL_MS = 5000;
/** Slower cadence for things that barely move (forecasts, client lists). */
export const SLOW_POLL_MS = 30000;

// ---------------------------------------------------------------------------
// Dashboards
// ---------------------------------------------------------------------------

export function useCompanyDashboard() {
  return useQuery({
    queryKey: ["dashboard", "company"],
    queryFn: () => api.get<CompanyDashboard>("/dashboard/company"),
    refetchInterval: LIVE_POLL_MS,
  });
}

export function useClientDashboard() {
  return useQuery({
    queryKey: ["dashboard", "client"],
    queryFn: () => api.get<ClientDashboard>("/dashboard/client"),
    refetchInterval: LIVE_POLL_MS,
  });
}

// ---------------------------------------------------------------------------
// Assets
// ---------------------------------------------------------------------------

export interface AssetFilters {
  status?: string;
  product_type?: ProductType | "";
  site_id?: number | "";
  q?: string;
}

export function useAssets(filters: AssetFilters = {}) {
  return useQuery({
    queryKey: ["assets", filters],
    queryFn: () => api.get<Page<Asset>>(`/assets${qs({ ...filters, limit: 500 })}`),
    refetchInterval: LIVE_POLL_MS,
  });
}

export function useAsset(assetId: number | null) {
  return useQuery({
    queryKey: ["asset", assetId],
    queryFn: () => api.get<AssetDetail>(`/assets/${assetId}`),
    enabled: assetId !== null,
    refetchInterval: LIVE_POLL_MS,
  });
}

export function useAssetTelemetry(assetId: number | null, hours = 24) {
  return useQuery({
    queryKey: ["telemetry", assetId, hours],
    queryFn: () => api.get<TelemetryPoint[]>(`/assets/${assetId}/telemetry?hours=${hours}`),
    enabled: assetId !== null,
    refetchInterval: LIVE_POLL_MS,
  });
}

export function useAssetEvents(assetId: number | null) {
  return useQuery({
    queryKey: ["events", assetId],
    queryFn: () => api.get<AssetEvent[]>(`/assets/${assetId}/events`),
    enabled: assetId !== null,
  });
}

export function useAssignEmployee() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ assetId, employeeId }: { assetId: number; employeeId: number }) =>
      api.post<AssetDetail>(`/assets/${assetId}/assign-employee`, { employee_id: employeeId }),
    onSuccess: () => invalidateLiveData(qc),
  });
}

export function useUnassignEmployee() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (assetId: number) => api.del<AssetDetail>(`/assets/${assetId}/assign-employee`),
    onSuccess: () => invalidateLiveData(qc),
  });
}

export function useCreateAsset() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: { product_type: ProductType; model?: string; daily_rate?: number }) =>
      api.post<AssetDetail>("/assets", body),
    onSuccess: () => invalidateLiveData(qc),
  });
}

export function useSetMaintenance() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ assetId, active }: { assetId: number; active: boolean }) =>
      api.patch<AssetDetail>(`/assets/${assetId}/maintenance?active=${active}`),
    onSuccess: () => invalidateLiveData(qc),
  });
}

// ---------------------------------------------------------------------------
// Sites / clients / employees
// ---------------------------------------------------------------------------

export function useSites() {
  return useQuery({
    queryKey: ["sites"],
    queryFn: () => api.get<SiteWithStats[]>("/sites"),
    refetchInterval: LIVE_POLL_MS,
  });
}

export function useCreateSite() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: {
      code: string;
      name: string;
      address?: string;
      latitude: number;
      longitude: number;
    }) => api.post<Site>("/sites", body),
    onSuccess: () => invalidateLiveData(qc),
  });
}

export function useClients() {
  return useQuery({
    queryKey: ["clients"],
    queryFn: () => api.get<ClientRow[]>("/clients"),
    refetchInterval: SLOW_POLL_MS,
  });
}

export function useEmployees(clientId?: number) {
  return useQuery({
    queryKey: ["employees", clientId ?? "mine"],
    queryFn: () => api.get<EmployeeWithAssignment[]>(`/employees${qs({ client_id: clientId })}`),
  });
}

export function useCreateEmployee() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: { name: string; phone?: string; client_id?: number }) =>
      api.post<Employee>("/employees", body),
    onSuccess: () => invalidateLiveData(qc),
  });
}

export function useUpdateEmployee() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, ...body }: { id: number; name?: string; phone?: string; active?: boolean }) =>
      api.patch<Employee>(`/employees/${id}`, body),
    onSuccess: () => invalidateLiveData(qc),
  });
}

// ---------------------------------------------------------------------------
// Rentals / check-in-out
// ---------------------------------------------------------------------------

export function useRentals(status?: string) {
  return useQuery({
    queryKey: ["rentals", status ?? "all"],
    queryFn: () => api.get<Rental[]>(`/rentals${qs({ status })}`),
    refetchInterval: LIVE_POLL_MS,
  });
}

export function useAssetLookup() {
  return useMutation({
    mutationFn: (code: string) =>
      api.get<AssetLookupResponse>(`/rentals/lookup/${encodeURIComponent(code)}`),
  });
}

export function useCheckout() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: {
      asset_id?: number;
      asset_code?: string;
      client_id: number;
      site_id?: number | null;
      employee_id?: number | null;
      expected_return_at: string;
    }) => api.post<Rental>("/rentals/checkout", body),
    onSuccess: () => invalidateLiveData(qc),
  });
}

export function useCheckin() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: {
      asset_id?: number;
      asset_code?: string;
      condition_notes?: string;
      tire_condition?: string;
      engine_condition?: string;
      send_to_maintenance?: boolean;
    }) => api.post<Rental>("/rentals/checkin", body),
    onSuccess: () => invalidateLiveData(qc),
  });
}

// ---------------------------------------------------------------------------
// Alerts
// ---------------------------------------------------------------------------

export function useAlerts(filters: { severity?: AlertSeverity | ""; type?: string; status?: string } = {}) {
  return useQuery({
    queryKey: ["alerts", filters],
    queryFn: () => api.get<Alert[]>(`/alerts${qs(filters)}`),
    refetchInterval: LIVE_POLL_MS,
  });
}

export function useAcknowledgeAlert() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (alertId: number) => api.patch<Alert>(`/alerts/${alertId}/acknowledge`),
    onSuccess: () => invalidateLiveData(qc),
  });
}

export function useResolveAlert() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (alertId: number) => api.patch<Alert>(`/alerts/${alertId}/resolve`),
    onSuccess: () => invalidateLiveData(qc),
  });
}

// ---------------------------------------------------------------------------
// Intelligence
// ---------------------------------------------------------------------------

export function useForecast(params: { site_id?: number | ""; product_type?: ProductType | "" } = {}) {
  return useQuery({
    queryKey: ["forecast", params],
    queryFn: () => api.get<Forecast[]>(`/forecast${qs(params)}`),
    refetchInterval: SLOW_POLL_MS,
  });
}

export function useRegenerateForecast() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => api.post<Record<string, unknown>>("/forecast/regenerate"),
    onSuccess: () => invalidateLiveData(qc),
  });
}

export function useRecommendations() {
  return useQuery({
    queryKey: ["recommendations"],
    queryFn: () => api.get<Recommendation[]>("/recommendations"),
    refetchInterval: SLOW_POLL_MS,
  });
}

export function useRequestRecommendation() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => api.post<Recommendation>(`/recommendations/${id}/request`),
    onSuccess: () => invalidateLiveData(qc),
  });
}

export function useDismissRecommendation() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => api.patch<Recommendation>(`/recommendations/${id}/dismiss`),
    onSuccess: () => invalidateLiveData(qc),
  });
}

// ---------------------------------------------------------------------------
// System
// ---------------------------------------------------------------------------

export function useSimulatorStatus(enabled = true) {
  return useQuery({
    queryKey: ["simulator"],
    queryFn: () => api.get<SimulatorStatus>("/simulator/status"),
    refetchInterval: LIVE_POLL_MS,
    enabled,
  });
}

export function useSimulatorControl() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (action: "start" | "stop" | "tick") =>
      api.post<Record<string, unknown>>(`/simulator/${action}`),
    onSuccess: () => invalidateLiveData(qc),
  });
}

export function useHealth() {
  return useQuery({
    queryKey: ["health"],
    queryFn: () => api.get<HealthResponse>("/health"),
    refetchInterval: SLOW_POLL_MS,
  });
}

// ---------------------------------------------------------------------------

/**
 * Invalidate everything that a write could have changed.
 *
 * Broad on purpose: a checkout touches assets, rentals, alerts, sites and both
 * dashboards. Enumerating exact keys per mutation would be a bug farm, and with
 * a 50-asset dataset the refetch cost is trivial.
 */
function invalidateLiveData(qc: ReturnType<typeof useQueryClient>) {
  for (const key of [
    "dashboard",
    "assets",
    "asset",
    "alerts",
    "rentals",
    "sites",
    "employees",
    "clients",
    "recommendations",
    "forecast",
    "events",
  ]) {
    qc.invalidateQueries({ queryKey: [key] });
  }
}
