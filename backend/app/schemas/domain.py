"""Domain request/response contracts: sites, employees, assets, rentals,
telemetry, alerts, forecasts and recommendations.

Kept in one module because these types reference each other heavily (an asset
embeds its site, employee and alert summary) and splitting them would produce a
web of circular imports for no readability gain.
"""

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import (
    AlertSeverity,
    AlertStatus,
    AlertType,
    HealthState,
    ProductType,
    RecommendationType,
    RentalStatus,
)

# ---------------------------------------------------------------------------
# Sites
# ---------------------------------------------------------------------------


class SiteCreate(BaseModel):
    code: str = Field(min_length=2, max_length=32)
    name: str = Field(min_length=2, max_length=160)
    address: str | None = None
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    client_id: int | None = None
    is_warehouse: bool = False


class SiteOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    code: str
    name: str
    address: str | None = None
    latitude: float
    longitude: float
    client_id: int | None = None
    is_warehouse: bool
    active: bool


class SiteWithStats(SiteOut):
    """Site enriched with live counts -- what the map markers render."""

    deployed_assets: int = 0
    active_assets: int = 0
    idle_assets: int = 0
    anomaly_count: int = 0
    utilization: float = 0.0


# ---------------------------------------------------------------------------
# Employees
# ---------------------------------------------------------------------------


class EmployeeCreate(BaseModel):
    name: str = Field(min_length=2, max_length=160)
    employee_code: str | None = Field(default=None, max_length=32)
    phone: str | None = Field(default=None, max_length=40)
    # Admin-only. Ignored entirely when the caller is a client -- their own
    # client_id from the token is used instead.
    client_id: int | None = None


class EmployeeUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=160)
    phone: str | None = Field(default=None, max_length=40)
    active: bool | None = None


class EmployeeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    client_id: int
    employee_code: str
    name: str
    phone: str | None = None
    active: bool


class EmployeeWithAssignment(EmployeeOut):
    assigned_asset_id: int | None = None
    assigned_asset_code: str | None = None


class AssignEmployeeRequest(BaseModel):
    employee_id: int


# ---------------------------------------------------------------------------
# Assets
# ---------------------------------------------------------------------------


class AssetCreate(BaseModel):
    asset_code: str | None = Field(default=None, max_length=32)
    product_type: ProductType
    model: str | None = None
    serial_number: str | None = None
    daily_rate: float = Field(default=0.0, ge=0)


class AlertBrief(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    type: str
    severity: str
    title: str
    status: str
    created_at: datetime


class AssetOut(BaseModel):
    """Row-level asset view. Powers both the client table and company fleet."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    asset_code: str
    product_type: str
    model: str | None = None
    status: str
    warehouse_status: str

    current_site_id: int | None = None
    site_code: str | None = None
    site_name: str | None = None

    current_client_id: int | None = None
    client_name: str | None = None

    # Who is AUTHORISED to operate this machine
    assigned_employee_id: int | None = None
    assigned_employee_code: str | None = None
    assigned_employee_name: str | None = None

    # Who telemetry REPORTS is operating it. A mismatch drives the
    # UNAUTHORIZED_OPERATOR alert, so the UI shows both.
    current_operator_id: int | None = None
    current_operator_code: str | None = None
    current_operator_name: str | None = None
    operator_match: bool = True

    fuel_level: float
    tire_condition: str
    engine_condition: str
    is_running: bool

    runtime_minutes_today: int
    idle_minutes_today: int
    utilization: float

    latitude: float | None = None
    longitude: float | None = None
    last_seen_at: datetime | None = None

    # Rental context
    rental_id: int | None = None
    expected_return_at: datetime | None = None
    hours_until_due: float | None = None

    # Alert rollup
    alert_count: int = 0
    max_severity: str | None = None


class AssetDetail(AssetOut):
    """Drawer view -- adds lifetime counters and embedded alerts."""

    serial_number: str | None = None
    qr_token: str
    daily_rate: float
    runtime_minutes: int
    idle_minutes: int
    continuous_runtime_minutes: int
    engine_temp_c: float
    lifetime_utilization: float
    alerts: list[AlertBrief] = []


# ---------------------------------------------------------------------------
# Telemetry
# ---------------------------------------------------------------------------


class TelemetryPoint(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    timestamp: datetime
    runtime_delta_minutes: int
    idle_delta_minutes: int
    fuel_level: float
    tire_health: str
    engine_health: str
    engine_temp_c: float
    is_running: bool
    latitude: float | None = None
    longitude: float | None = None
    current_operator_id: int | None = None


class TelemetryIngest(BaseModel):
    """External telemetry ingestion contract.

    The simulator writes through the service layer directly, but this endpoint
    exists so real hardware (or a load test) could post the same shape.
    """

    asset_code: str
    is_running: bool
    runtime_delta_minutes: int = Field(default=0, ge=0)
    idle_delta_minutes: int = Field(default=0, ge=0)
    fuel_level: float = Field(ge=0, le=100)
    tire_health: HealthState = HealthState.GOOD
    engine_health: HealthState = HealthState.GOOD
    engine_temp_c: float = 45.0
    latitude: float | None = None
    longitude: float | None = None
    current_operator_code: str | None = None


# ---------------------------------------------------------------------------
# Rentals / check-in / check-out
# ---------------------------------------------------------------------------


class CheckoutRequest(BaseModel):
    """Either asset_id or asset_code/qr_token identifies the machine."""

    asset_id: int | None = None
    asset_code: str | None = None
    client_id: int
    site_id: int | None = None
    employee_id: int | None = None
    expected_return_at: datetime
    rental_rate: float | None = None


class CheckinRequest(BaseModel):
    asset_id: int | None = None
    asset_code: str | None = None
    condition_notes: str | None = None
    tire_condition: HealthState | None = None
    engine_condition: HealthState | None = None
    send_to_maintenance: bool = False


class RentalOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    asset_id: int
    asset_code: str | None = None
    product_type: str | None = None
    client_id: int
    client_name: str | None = None
    site_id: int | None = None
    site_code: str | None = None
    checkout_at: datetime
    expected_return_at: datetime
    actual_return_at: datetime | None = None
    status: str
    rental_rate: float
    hours_until_due: float | None = None
    checkin_condition_notes: str | None = None


class AssetLookupResponse(BaseModel):
    """Resolves an asset_code or qr_token for the check-in/out console."""

    asset: AssetOut
    active_rental: RentalOut | None = None
    available_employees: list[EmployeeOut] = []


# ---------------------------------------------------------------------------
# Alerts
# ---------------------------------------------------------------------------


class AlertOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    asset_id: int | None = None
    asset_code: str | None = None
    client_id: int | None = None
    client_name: str | None = None
    site_id: int | None = None
    site_code: str | None = None
    type: str
    severity: str
    title: str
    description: str
    reasons: list[str] = []
    recommended_action: str | None = None
    source: str
    score: float | None = None
    status: str
    created_at: datetime
    acknowledged_at: datetime | None = None
    resolved_at: datetime | None = None


# ---------------------------------------------------------------------------
# Intelligence
# ---------------------------------------------------------------------------


class ForecastOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    site_id: int
    site_code: str | None = None
    site_name: str | None = None
    product_type: str
    forecast_date: date
    horizon_days: int
    predicted_demand: float
    currently_available: int
    expected_shortfall: float
    model_version: str | None = None


class RecommendationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    client_id: int | None = None
    client_name: str | None = None
    site_id: int | None = None
    site_code: str | None = None
    asset_id: int | None = None
    asset_code: str | None = None
    type: str
    title: str
    description: str
    rationale: list[str] = []
    product_type: str | None = None
    quantity: int
    status: str
    created_at: datetime


# ---------------------------------------------------------------------------
# Events
# ---------------------------------------------------------------------------


class AssetEventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    asset_id: int
    event_type: str
    old_value: str | None = None
    new_value: str | None = None
    description: str | None = None
    timestamp: datetime
    actor_name: str | None = None


# ---------------------------------------------------------------------------
# Filters (shared query params)
# ---------------------------------------------------------------------------


class AssetFilters(BaseModel):
    status: str | None = None
    product_type: ProductType | None = None
    site_id: int | None = None
    severity: AlertSeverity | None = None
    q: str | None = None


class AlertFilters(BaseModel):
    severity: AlertSeverity | None = None
    type: AlertType | None = None
    status: AlertStatus | None = None


class RentalFilters(BaseModel):
    status: RentalStatus | None = None


class RecommendationFilters(BaseModel):
    type: RecommendationType | None = None
