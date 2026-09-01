/**
 * TypeScript mirrors of the backend Pydantic schemas.
 *
 * These are hand-maintained rather than generated. If you change a Pydantic
 * model in `backend/app/schemas/`, update the matching interface here --
 * the OpenAPI schema at http://localhost:8000/openapi.json is the reference.
 */

export type UserRole = "COMPANY_ADMIN" | "COMPANY_OPERATOR" | "CLIENT";

export type ProductType =
  | "EXCAVATOR"
  | "BULLDOZER"
  | "CRANE"
  | "GRADER"
  | "WHEEL_LOADER";

export type AssetStatus =
  | "AVAILABLE"
  | "RENTED"
  | "ACTIVE"
  | "IDLE"
  | "OVERDUE"
  | "MAINTENANCE"
  | "UNKNOWN";

export type WarehouseStatus =
  | "IN_WAREHOUSE"
  | "DEPLOYED"
  | "IN_TRANSIT"
  | "MAINTENANCE";

export type HealthState = "GOOD" | "WARNING" | "CRITICAL";

export type AlertSeverity = "CRITICAL" | "HIGH" | "MEDIUM" | "LOW" | "INFO";
export type AlertStatus = "OPEN" | "ACKNOWLEDGED" | "RESOLVED";

export type AlertType =
  | "CONTINUOUS_USAGE"
  | "UNDERUTILIZED"
  | "LOW_FUEL"
  | "TIRE_WARNING"
  | "ENGINE_WARNING"
  | "DUE_SOON"
  | "OVERDUE"
  | "UNAUTHORIZED_OPERATOR"
  | "UNASSIGNED_EQUIPMENT"
  | "ML_ANOMALY"
  | "FORECAST_SHORTFALL";

export type RentalStatus = "ACTIVE" | "RETURNED" | "OVERDUE" | "CANCELLED";

export type RecommendationType =
  | "REQUEST_MORE_ASSETS"
  | "PREPOSITION_ASSET"
  | "RETURN_UNDERUTILIZED"
  | "SCHEDULE_MAINTENANCE"
  | "REASSIGN_OPERATOR";

export type RecommendationStatus = "OPEN" | "REQUESTED" | "ACCEPTED" | "DISMISSED";

// ---------------------------------------------------------------------------

export interface ClientBrief {
  id: number;
  name: string;
  code: string;
}

export interface User {
  id: number;
  email: string;
  full_name: string;
  role: UserRole;
  client_id: number | null;
  client?: ClientBrief | null;
  is_active: boolean;
}

export interface TokenResponse {
  access_token: string;
  token_type: string;
  expires_in: number;
  user: User;
}

export interface Page<T> {
  items: T[];
  total: number;
  limit: number;
  offset: number;
}

export interface Site {
  id: number;
  code: string;
  name: string;
  address: string | null;
  latitude: number;
  longitude: number;
  client_id: number | null;
  is_warehouse: boolean;
  active: boolean;
}

export interface SiteWithStats extends Site {
  deployed_assets: number;
  active_assets: number;
  idle_assets: number;
  anomaly_count: number;
  utilization: number;
}

export interface Employee {
  id: number;
  client_id: number;
  employee_code: string;
  name: string;
  phone: string | null;
  active: boolean;
}

export interface EmployeeWithAssignment extends Employee {
  assigned_asset_id: number | null;
  assigned_asset_code: string | null;
}

export interface AlertBrief {
  id: number;
  type: AlertType;
  severity: AlertSeverity;
  title: string;
  status: AlertStatus;
  created_at: string;
}

export interface Asset {
  id: number;
  asset_code: string;
  product_type: ProductType;
  model: string | null;
  status: AssetStatus;
  warehouse_status: WarehouseStatus;

  current_site_id: number | null;
  site_code: string | null;
  site_name: string | null;

  current_client_id: number | null;
  client_name: string | null;

  /** Who is AUTHORISED to operate. */
  assigned_employee_id: number | null;
  assigned_employee_code: string | null;
  assigned_employee_name: string | null;

  /** Who telemetry REPORTS is operating. A mismatch drives the critical alert. */
  current_operator_id: number | null;
  current_operator_code: string | null;
  current_operator_name: string | null;
  operator_match: boolean;

  fuel_level: number;
  tire_condition: HealthState;
  engine_condition: HealthState;
  is_running: boolean;

  runtime_minutes_today: number;
  idle_minutes_today: number;
  utilization: number;

  latitude: number | null;
  longitude: number | null;
  last_seen_at: string | null;

  rental_id: number | null;
  expected_return_at: string | null;
  hours_until_due: number | null;

  alert_count: number;
  max_severity: AlertSeverity | null;
}

export interface AssetDetail extends Asset {
  serial_number: string | null;
  qr_token: string;
  daily_rate: number;
  runtime_minutes: number;
  idle_minutes: number;
  continuous_runtime_minutes: number;
  engine_temp_c: number;
  lifetime_utilization: number;
  alerts: AlertBrief[];
}

export interface TelemetryPoint {
  timestamp: string;
  runtime_delta_minutes: number;
  idle_delta_minutes: number;
  fuel_level: number;
  tire_health: HealthState;
  engine_health: HealthState;
  engine_temp_c: number;
  is_running: boolean;
  latitude: number | null;
  longitude: number | null;
  current_operator_id: number | null;
}

export interface Alert {
  id: number;
  asset_id: number | null;
  asset_code: string | null;
  client_id: number | null;
  client_name: string | null;
  site_id: number | null;
  site_code: string | null;
  type: AlertType;
  severity: AlertSeverity;
  title: string;
  description: string;
  /** Human-readable explanation. Never a raw model score. */
  reasons: string[];
  recommended_action: string | null;
  source: "RULE" | "ML" | "HYBRID";
  score: number | null;
  status: AlertStatus;
  created_at: string;
  acknowledged_at: string | null;
  resolved_at: string | null;
}

export interface Rental {
  id: number;
  asset_id: number;
  asset_code: string | null;
  product_type: ProductType | null;
  client_id: number;
  client_name: string | null;
  site_id: number | null;
  site_code: string | null;
  checkout_at: string;
  expected_return_at: string;
  actual_return_at: string | null;
  status: RentalStatus;
  rental_rate: number;
  hours_until_due: number | null;
  checkin_condition_notes: string | null;
}

export interface AssetLookupResponse {
  asset: Asset;
  active_rental: Rental | null;
  available_employees: Employee[];
}

export interface AssetEvent {
  id: number;
  asset_id: number;
  event_type: string;
  old_value: string | null;
  new_value: string | null;
  description: string | null;
  timestamp: string;
  actor_name: string | null;
}

export interface Forecast {
  id: number;
  site_id: number;
  site_code: string | null;
  site_name: string | null;
  product_type: ProductType;
  forecast_date: string;
  horizon_days: number;
  predicted_demand: number;
  currently_available: number;
  expected_shortfall: number;
  model_version: string | null;
}

/**
 * One point on the demand timeline. History rows carry `actual`, forecast rows
 * carry `predicted`, and exactly one row -- today -- carries both, so the chart
 * draws a single continuous line across the boundary.
 */
export interface ForecastTimelinePoint {
  date: string;
  actual: number | null;
  predicted: number | null;
  available: number | null;
  is_forecast: boolean;
}

export interface ForecastTimeline {
  site_id: number;
  product_type: ProductType;
  today: string;
  model_version: string | null;
  points: ForecastTimelinePoint[];
}

// ---------------------------------------------------------------------------
// Client onboarding
// ---------------------------------------------------------------------------

export interface DepotAvailability {
  product_type: ProductType;
  available: number;
  total: number;
}

export interface OnboardingSiteInput {
  name: string;
  address?: string;
  latitude: number;
  longitude: number;
}

export interface OnboardingEquipmentInput {
  product_type: ProductType;
  quantity: number;
}

export interface ClientOnboardingRequest {
  name: string;
  code?: string;
  contact_email?: string;
  contact_phone?: string;
  login_email: string;
  login_password: string;
  login_full_name: string;
  sites: OnboardingSiteInput[];
  equipment: OnboardingEquipmentInput[];
  rental_days: number;
}

export interface AllocatedAsset {
  asset_id: number;
  asset_code: string;
  product_type: ProductType;
  model: string | null;
  site_code: string | null;
  rental_id: number;
}

export interface ClientOnboardingResponse {
  client_id: number;
  client_name: string;
  client_code: string;
  login_email: string;
  user_id: number;
  sites: { id: number; code: string; name: string; latitude: number; longitude: number }[];
  allocated: AllocatedAsset[];
  inventory_after: DepotAvailability[];
  expected_return_at: string;
}

export interface Recommendation {
  id: number;
  client_id: number | null;
  client_name: string | null;
  site_id: number | null;
  site_code: string | null;
  asset_id: number | null;
  asset_code: string | null;
  type: RecommendationType;
  title: string;
  description: string;
  rationale: string[];
  product_type: ProductType | null;
  quantity: number;
  status: RecommendationStatus;
  created_at: string;
}

export interface ClientRow {
  id: number;
  name: string;
  code: string;
  contact_email: string | null;
  contact_phone: string | null;
  active: boolean;
  rented_assets: number;
  employees: number;
  open_alerts: number;
  critical_alerts: number;
  avg_utilization: number;
}

// ---------------------------------------------------------------------------
// Dashboards
// ---------------------------------------------------------------------------

export interface UtilizationPoint {
  label: string;
  utilization: number;
  runtime_hours: number;
  idle_hours: number;
}

export interface ProductTypeStat {
  product_type: ProductType;
  total: number;
  deployed: number;
  warehouse: number;
  maintenance: number;
  active: number;
  idle: number;
  utilization: number;
}

export interface ClientKPIs {
  active_assets: number;
  idle_assets: number;
  due_soon: number;
  overdue: number;
  critical_alerts: number;
  avg_utilization: number;
  total_assets: number;
}

export interface ClientDashboard {
  kpis: ClientKPIs;
  assets: Asset[];
  alerts: Alert[];
  utilization_trend: UtilizationPoint[];
  by_product_type: ProductTypeStat[];
  recommendations: Recommendation[];
  generated_at: string;
}

export interface CompanyKPIs {
  total_fleet: number;
  rented: number;
  available: number;
  in_warehouse: number;
  active: number;
  idle: number;
  overdue: number;
  maintenance: number;
  critical_alerts: number;
  avg_utilization: number;
}

export interface CompanyDashboard {
  kpis: CompanyKPIs;
  sites: SiteWithStats[];
  action_queue: Alert[];
  utilization_trend: UtilizationPoint[];
  by_product_type: ProductTypeStat[];
  forecasts: Forecast[];
  recommendations: Recommendation[];
  generated_at: string;
}

export interface SimulatorStatus {
  running: boolean;
  tick_count: number;
  simulated_clock: string | null;
  tick_seconds: number;
  simulated_minutes_per_tick: number;
  seed: number;
  last_tick_at: string | null;
  assets_updated_last_tick: number;
}

export interface HealthResponse {
  status: string;
  database: boolean;
  anomaly_model_loaded: boolean;
  demand_model_loaded: boolean;
  simulator_running: boolean;
  message: string | null;
}
