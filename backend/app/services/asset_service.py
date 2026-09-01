"""Asset queries and enriched serialisation.

The dashboards poll every 5 seconds, so serialisation must not be N+1. Rather
than lazy-loading site/client/employee/rental/alerts per asset (which for 50
assets would be ~250 queries per poll), ``serialize_assets`` bulk-loads every
relation into dicts and joins in Python. Cost is a fixed ~6 queries regardless
of fleet size.
"""

from datetime import timezone

from sqlalchemy import Select, func, or_, select
from sqlalchemy.orm import Session

from app.models import (
    Alert,
    AlertSeverity,
    AlertStatus,
    Asset,
    AssetStatus,
    Client,
    Employee,
    Rental,
    RentalStatus,
    Site,
    utcnow,
)
from app.schemas.domain import AlertBrief, AssetDetail, AssetOut

OPEN_ALERT_STATES = (AlertStatus.OPEN.value, AlertStatus.ACKNOWLEDGED.value)
OPEN_RENTAL_STATES = (RentalStatus.ACTIVE.value, RentalStatus.OVERDUE.value)


def _aware(dt):
    """Normalise a datetime read back from SQLite to timezone-aware UTC.

    SQLite has no native timestamptz: values come back naive even though they
    were stored as aware. Comparing naive against aware raises TypeError, so
    every datetime leaving the DB passes through here.
    """
    if dt is None:
        return None
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt


def hours_until(dt) -> float | None:
    dt = _aware(dt)
    if dt is None:
        return None
    return (dt - utcnow()).total_seconds() / 3600.0


def apply_asset_filters(
    stmt: Select,
    *,
    status: str | None = None,
    product_type: str | None = None,
    site_id: int | None = None,
    q: str | None = None,
) -> Select:
    """Apply the shared filter set used by both fleet and client asset lists."""
    if status:
        stmt = stmt.where(Asset.status == status)
    if product_type:
        stmt = stmt.where(Asset.product_type == product_type)
    if site_id is not None:
        stmt = stmt.where(Asset.current_site_id == site_id)
    if q:
        needle = f"%{q.strip().lower()}%"
        stmt = stmt.where(
            or_(
                func.lower(Asset.asset_code).like(needle),
                func.lower(Asset.product_type).like(needle),
                func.lower(func.coalesce(Asset.model, "")).like(needle),
            )
        )
    return stmt


def _lookup_maps(db: Session, assets: list[Asset]) -> dict:
    """Bulk-load every relation the asset views need. ~6 queries, fleet-size independent."""
    asset_ids = [a.id for a in assets]
    site_ids = {a.current_site_id for a in assets if a.current_site_id}
    client_ids = {a.current_client_id for a in assets if a.current_client_id}
    employee_ids = {a.assigned_employee_id for a in assets if a.assigned_employee_id}
    employee_ids |= {a.current_operator_id for a in assets if a.current_operator_id}

    sites = {}
    if site_ids:
        sites = {s.id: s for s in db.execute(select(Site).where(Site.id.in_(site_ids))).scalars()}

    clients = {}
    if client_ids:
        clients = {c.id: c for c in db.execute(select(Client).where(Client.id.in_(client_ids))).scalars()}

    employees = {}
    if employee_ids:
        employees = {e.id: e for e in db.execute(select(Employee).where(Employee.id.in_(employee_ids))).scalars()}

    rentals: dict[int, Rental] = {}
    alert_counts: dict[int, int] = {}
    worst: dict[int, str] = {}

    if asset_ids:
        for r in db.execute(
            select(Rental).where(Rental.asset_id.in_(asset_ids), Rental.status.in_(OPEN_RENTAL_STATES))
        ).scalars():
            rentals[r.asset_id] = r

        rows = db.execute(
            select(Alert.asset_id, Alert.severity, func.count(Alert.id))
            .where(Alert.asset_id.in_(asset_ids), Alert.status.in_(OPEN_ALERT_STATES))
            .group_by(Alert.asset_id, Alert.severity)
        ).all()
        for asset_id, severity, count in rows:
            alert_counts[asset_id] = alert_counts.get(asset_id, 0) + count
            current = worst.get(asset_id)
            if current is None or AlertSeverity(severity).rank < AlertSeverity(current).rank:
                worst[asset_id] = severity

    return {
        "sites": sites,
        "clients": clients,
        "employees": employees,
        "rentals": rentals,
        "alert_counts": alert_counts,
        "worst": worst,
    }


def _base_payload(asset: Asset, maps: dict) -> dict:
    site = maps["sites"].get(asset.current_site_id)
    client = maps["clients"].get(asset.current_client_id)
    employee = maps["employees"].get(asset.assigned_employee_id)
    operator = maps["employees"].get(asset.current_operator_id)
    rental = maps["rentals"].get(asset.id)

    return {
        "id": asset.id,
        "asset_code": asset.asset_code,
        "product_type": asset.product_type,
        "model": asset.model,
        "status": asset.status,
        "warehouse_status": asset.warehouse_status,
        "current_site_id": asset.current_site_id,
        "site_code": site.code if site else None,
        "site_name": site.name if site else None,
        "current_client_id": asset.current_client_id,
        "client_name": client.name if client else None,
        "assigned_employee_id": asset.assigned_employee_id,
        "assigned_employee_code": employee.employee_code if employee else None,
        "assigned_employee_name": employee.name if employee else None,
        "current_operator_id": asset.current_operator_id,
        "current_operator_code": operator.employee_code if operator else None,
        "current_operator_name": operator.name if operator else None,
        "operator_match": asset.operator_match,
        "fuel_level": round(asset.fuel_level, 1),
        "tire_condition": asset.tire_condition,
        "engine_condition": asset.engine_condition,
        "is_running": asset.is_running,
        "runtime_minutes_today": asset.runtime_minutes_today,
        "idle_minutes_today": asset.idle_minutes_today,
        "utilization": round(asset.utilization, 4),
        "latitude": asset.latitude,
        "longitude": asset.longitude,
        "last_seen_at": _aware(asset.last_seen_at),
        "rental_id": rental.id if rental else None,
        "expected_return_at": _aware(rental.expected_return_at) if rental else None,
        "hours_until_due": round(hours_until(rental.expected_return_at), 2) if rental else None,
        "alert_count": maps["alert_counts"].get(asset.id, 0),
        "max_severity": maps["worst"].get(asset.id),
    }


def serialize_assets(db: Session, assets: list[Asset]) -> list[AssetOut]:
    if not assets:
        return []
    maps = _lookup_maps(db, assets)
    return [AssetOut(**_base_payload(a, maps)) for a in assets]


def serialize_asset_detail(db: Session, asset: Asset) -> AssetDetail:
    maps = _lookup_maps(db, [asset])
    payload = _base_payload(asset, maps)

    alerts = (
        db.execute(
            select(Alert)
            .where(Alert.asset_id == asset.id, Alert.status.in_(OPEN_ALERT_STATES))
            .order_by(Alert.created_at.desc())
            .limit(25)
        )
        .scalars()
        .all()
    )

    payload.update(
        {
            "serial_number": asset.serial_number,
            "qr_token": asset.qr_token,
            "daily_rate": asset.daily_rate,
            "runtime_minutes": asset.runtime_minutes,
            "idle_minutes": asset.idle_minutes,
            "continuous_runtime_minutes": asset.continuous_runtime_minutes,
            "engine_temp_c": round(asset.engine_temp_c, 1),
            "lifetime_utilization": round(asset.lifetime_utilization, 4),
            "alerts": [
                AlertBrief(
                    id=a.id,
                    type=a.type,
                    severity=a.severity,
                    title=a.title,
                    status=a.status,
                    created_at=_aware(a.created_at),
                )
                for a in alerts
            ],
        }
    )
    return AssetDetail(**payload)


def resolve_asset_by_code(db: Session, code: str) -> Asset | None:
    """Look up an asset by its printed code OR its QR/RFID token.

    The check-in/out console accepts either, so manual entry and a simulated
    scan hit exactly the same backend path.
    """
    needle = code.strip()
    return db.execute(
        select(Asset).where(or_(Asset.asset_code == needle, Asset.qr_token == needle))
    ).scalar_one_or_none()


def active_rental_for(db: Session, asset_id: int) -> Rental | None:
    return db.execute(
        select(Rental)
        .where(Rental.asset_id == asset_id, Rental.status.in_(OPEN_RENTAL_STATES))
        .order_by(Rental.checkout_at.desc())
    ).scalars().first()


def is_deployed(asset: Asset) -> bool:
    return asset.status in (
        AssetStatus.RENTED.value,
        AssetStatus.ACTIVE.value,
        AssetStatus.IDLE.value,
        AssetStatus.OVERDUE.value,
    )
