"""Dashboard aggregate contracts.

Both dashboards are served by a single endpoint each. This is deliberate: the
control tower needs eight KPIs, a site list, an action queue and three charts,
and issuing seven parallel requests would make the 5s polling loop hammer the
API. One aggregate response keeps polling cheap and the screen consistent
(everything reflects the same instant).
"""

from pydantic import BaseModel

from app.schemas.domain import (
    AlertOut,
    AssetOut,
    ForecastOut,
    RecommendationOut,
    SiteWithStats,
)


class UtilizationPoint(BaseModel):
    """One bucket of the utilisation trend chart."""

    label: str          # e.g. "Mon 08:00" or "2026-08-28"
    utilization: float  # 0.0-1.0
    runtime_hours: float
    idle_hours: float


class ProductTypeStat(BaseModel):
    """Inventory rollup for one equipment type."""

    product_type: str
    total: int
    deployed: int
    warehouse: int
    maintenance: int
    active: int
    idle: int
    utilization: float


class ClientKPIs(BaseModel):
    active_assets: int
    idle_assets: int
    due_soon: int
    overdue: int
    critical_alerts: int
    avg_utilization: float
    total_assets: int


class ClientDashboard(BaseModel):
    kpis: ClientKPIs
    assets: list[AssetOut]
    alerts: list[AlertOut]
    utilization_trend: list[UtilizationPoint]
    by_product_type: list[ProductTypeStat]
    recommendations: list[RecommendationOut]
    generated_at: str


class CompanyKPIs(BaseModel):
    total_fleet: int
    rented: int
    available: int
    in_warehouse: int
    active: int
    idle: int
    overdue: int
    maintenance: int
    critical_alerts: int
    avg_utilization: float


class CompanyDashboard(BaseModel):
    kpis: CompanyKPIs
    sites: list[SiteWithStats]
    action_queue: list[AlertOut]
    utilization_trend: list[UtilizationPoint]
    by_product_type: list[ProductTypeStat]
    forecasts: list[ForecastOut]
    recommendations: list[RecommendationOut]
    generated_at: str


class SimulatorStatus(BaseModel):
    running: bool
    tick_count: int
    simulated_clock: str | None = None
    tick_seconds: int
    simulated_minutes_per_tick: int
    seed: int
    last_tick_at: str | None = None
    assets_updated_last_tick: int = 0


class HealthResponse(BaseModel):
    status: str
    database: bool
    anomaly_model_loaded: bool
    demand_model_loaded: bool
    simulator_running: bool
    message: str | None = None
