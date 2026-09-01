"""Dashboard aggregates.

One aggregate response per dashboard rather than a request per widget: the UI
polls every 5 seconds, and seven parallel requests per poll would hammer the API
for no benefit. A single response also guarantees every tile on screen reflects
the same instant.
"""

from datetime import timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import settings
from app.core.deps import TenantContext, scope_alerts, scope_assets
from app.models import (
    Alert,
    AlertSeverity,
    AlertStatus,
    Asset,
    AssetStatus,
    ProductType,
    TelemetryLog,
    WarehouseStatus,
    utcnow,
)
from app.schemas.dashboard import (
    ClientKPIs,
    CompanyKPIs,
    ProductTypeStat,
    UtilizationPoint,
)

LIVE_ALERTS = (AlertStatus.OPEN.value, AlertStatus.ACKNOWLEDGED.value)


def _status_counts(db: Session, ctx: TenantContext) -> dict[str, int]:
    stmt = scope_assets(select(Asset.status, func.count(Asset.id)).group_by(Asset.status), ctx)
    return {status: count for status, count in db.execute(stmt).all()}


def _fleet_utilization(db: Session, ctx: TenantContext) -> float:
    stmt = scope_assets(
        select(func.sum(Asset.runtime_minutes_today), func.sum(Asset.idle_minutes_today)), ctx
    )
    runtime, idle = db.execute(stmt).one()
    denom = (runtime or 0) + (idle or 0)
    return round((runtime or 0) / denom, 4) if denom else 0.0


def _critical_alert_count(db: Session, ctx: TenantContext) -> int:
    stmt = scope_alerts(
        select(func.count(Alert.id)).where(
            Alert.status.in_(LIVE_ALERTS),
            Alert.severity.in_((AlertSeverity.CRITICAL.value, AlertSeverity.HIGH.value)),
        ),
        ctx,
    )
    return db.execute(stmt).scalar_one() or 0


def client_kpis(db: Session, ctx: TenantContext) -> ClientKPIs:
    counts = _status_counts(db, ctx)
    total = sum(counts.values())

    # Due-soon needs the rental deadline, so it comes off the rentals table.
    from app.models import Rental, RentalStatus

    horizon = utcnow() + timedelta(hours=settings.DUE_SOON_HOURS)
    due_stmt = select(func.count(Rental.id)).where(
        Rental.status == RentalStatus.ACTIVE.value,
        Rental.expected_return_at <= horizon,
        Rental.expected_return_at > utcnow(),
    )
    if not ctx.is_admin:
        due_stmt = due_stmt.where(Rental.client_id == ctx.client_id)
    due_soon = db.execute(due_stmt).scalar_one() or 0

    return ClientKPIs(
        active_assets=counts.get(AssetStatus.ACTIVE.value, 0),
        idle_assets=counts.get(AssetStatus.IDLE.value, 0) + counts.get(AssetStatus.RENTED.value, 0),
        due_soon=due_soon,
        overdue=counts.get(AssetStatus.OVERDUE.value, 0),
        critical_alerts=_critical_alert_count(db, ctx),
        avg_utilization=_fleet_utilization(db, ctx),
        total_assets=total,
    )


def company_kpis(db: Session, ctx: TenantContext) -> CompanyKPIs:
    counts = _status_counts(db, ctx)
    total = sum(counts.values())

    warehouse = db.execute(
        scope_assets(
            select(func.count(Asset.id)).where(Asset.warehouse_status == WarehouseStatus.IN_WAREHOUSE.value), ctx
        )
    ).scalar_one() or 0

    rented = (
        counts.get(AssetStatus.RENTED.value, 0)
        + counts.get(AssetStatus.ACTIVE.value, 0)
        + counts.get(AssetStatus.IDLE.value, 0)
        + counts.get(AssetStatus.OVERDUE.value, 0)
    )

    return CompanyKPIs(
        total_fleet=total,
        rented=rented,
        available=counts.get(AssetStatus.AVAILABLE.value, 0),
        in_warehouse=warehouse,
        active=counts.get(AssetStatus.ACTIVE.value, 0),
        idle=counts.get(AssetStatus.IDLE.value, 0) + counts.get(AssetStatus.RENTED.value, 0),
        overdue=counts.get(AssetStatus.OVERDUE.value, 0),
        maintenance=counts.get(AssetStatus.MAINTENANCE.value, 0),
        critical_alerts=_critical_alert_count(db, ctx),
        avg_utilization=_fleet_utilization(db, ctx),
    )


def product_type_stats(db: Session, ctx: TenantContext) -> list[ProductTypeStat]:
    """Inventory rollup by equipment type -- powers the inventory screen."""
    rows = db.execute(
        scope_assets(
            select(
                Asset.product_type,
                Asset.status,
                Asset.warehouse_status,
                func.count(Asset.id),
            ).group_by(Asset.product_type, Asset.status, Asset.warehouse_status),
            ctx,
        )
    ).all()

    util_rows = db.execute(
        scope_assets(
            select(
                Asset.product_type,
                func.sum(Asset.runtime_minutes_today),
                func.sum(Asset.idle_minutes_today),
            ).group_by(Asset.product_type),
            ctx,
        )
    ).all()
    utilization = {}
    for product_type, runtime, idle in util_rows:
        denom = (runtime or 0) + (idle or 0)
        utilization[product_type] = round((runtime or 0) / denom, 4) if denom else 0.0

    buckets: dict[str, dict[str, int]] = {}
    for product_type, status, warehouse_status, count in rows:
        b = buckets.setdefault(
            product_type,
            {"total": 0, "deployed": 0, "warehouse": 0, "maintenance": 0, "active": 0, "idle": 0},
        )
        b["total"] += count
        if status == AssetStatus.ACTIVE.value:
            b["active"] += count
        if status in (AssetStatus.IDLE.value, AssetStatus.RENTED.value):
            b["idle"] += count
        if status == AssetStatus.MAINTENANCE.value:
            b["maintenance"] += count
        elif warehouse_status == WarehouseStatus.IN_WAREHOUSE.value:
            b["warehouse"] += count
        elif warehouse_status == WarehouseStatus.DEPLOYED.value:
            b["deployed"] += count

    # Include every product type, even ones with zero assets, so the inventory
    # table does not silently change shape as machines get rented out.
    result = []
    for pt in ProductType:
        b = buckets.get(pt.value, {"total": 0, "deployed": 0, "warehouse": 0, "maintenance": 0, "active": 0, "idle": 0})
        result.append(
            ProductTypeStat(
                product_type=pt.value,
                total=b["total"],
                deployed=b["deployed"],
                warehouse=b["warehouse"],
                maintenance=b["maintenance"],
                active=b["active"],
                idle=b["idle"],
                utilization=utilization.get(pt.value, 0.0),
            )
        )
    return result


def utilization_trend(db: Session, ctx: TenantContext, hours: int = 24, buckets: int = 12) -> list[UtilizationPoint]:
    """Utilisation over time, bucketed from the telemetry series.

    Aggregating in Python rather than SQL keeps this portable: date_trunc and
    strftime differ between PostgreSQL and SQLite, and the row count here is
    small enough that it does not matter.
    """
    since = utcnow() - timedelta(hours=hours)

    stmt = select(TelemetryLog.timestamp, TelemetryLog.runtime_delta_minutes, TelemetryLog.idle_delta_minutes).where(
        TelemetryLog.timestamp >= since
    )
    if not ctx.is_admin:
        stmt = stmt.where(TelemetryLog.client_id == ctx.client_id)

    rows = db.execute(stmt).all()
    if not rows:
        return []

    bucket_span = timedelta(hours=hours) / buckets
    totals: list[list[float]] = [[0.0, 0.0] for _ in range(buckets)]

    for ts, runtime, idle in rows:
        if ts is None:
            continue
        if ts.tzinfo is None:
            from datetime import timezone

            ts = ts.replace(tzinfo=timezone.utc)
        offset = (ts - since).total_seconds()
        index = int(offset // bucket_span.total_seconds())
        index = max(0, min(buckets - 1, index))
        totals[index][0] += runtime or 0
        totals[index][1] += idle or 0

    points = []
    for i, (runtime, idle) in enumerate(totals):
        denom = runtime + idle
        bucket_time = since + bucket_span * i
        points.append(
            UtilizationPoint(
                label=bucket_time.strftime("%d %b %H:%M"),
                utilization=round(runtime / denom, 4) if denom else 0.0,
                runtime_hours=round(runtime / 60, 2),
                idle_hours=round(idle / 60, 2),
            )
        )
    return points
