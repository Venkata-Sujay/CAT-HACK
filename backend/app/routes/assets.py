"""Asset endpoints.

Every read here is tenant-scoped. Note the pattern used throughout:

    stmt = scope_assets(select(Asset), ctx)     # list  -> filtered
    asset = get_asset_or_404(db, id, ctx)       # detail -> 404 on cross-tenant

A ``client_id`` query parameter is deliberately NOT accepted on any of these
routes. Scope comes from the token; see app/core/deps.py.
"""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.deps import (
    TenantContext,
    get_asset_or_404,
    get_employee_or_404,
    get_tenant_context,
    require_admin,
    scope_assets,
    scope_events,
    scope_telemetry,
)
from app.database import get_db
from app.models import (
    Asset,
    AssetEvent,
    AssetStatus,
    Client,
    Employee,
    ProductType,
    TelemetryLog,
    User,
    WarehouseStatus,
    utcnow,
)
from app.schemas.common import MessageResponse, Page
from app.schemas.domain import (
    AssetCreate,
    AssetDetail,
    AssetEventOut,
    AssetOut,
    AssignEmployeeRequest,
    TelemetryPoint,
)
from app.services import asset_service, rental_service
from app.services.asset_service import apply_asset_filters, serialize_asset_detail, serialize_assets

router = APIRouter(prefix="/assets", tags=["assets"])


@router.get("", response_model=Page[AssetOut])
def list_assets(
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(get_tenant_context),
    status_filter: str | None = Query(default=None, alias="status"),
    product_type: ProductType | None = None,
    site_id: int | None = None,
    q: str | None = None,
    limit: int = Query(default=200, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> Page[AssetOut]:
    stmt = scope_assets(select(Asset), ctx)
    stmt = apply_asset_filters(
        stmt,
        status=status_filter,
        product_type=product_type.value if product_type else None,
        site_id=site_id,
        q=q,
    )

    total = db.execute(select(func.count()).select_from(stmt.subquery())).scalar_one()
    rows = db.execute(stmt.order_by(Asset.asset_code).limit(limit).offset(offset)).scalars().all()

    return Page[AssetOut](items=serialize_assets(db, list(rows)), total=total, limit=limit, offset=offset)


@router.get("/{asset_id}", response_model=AssetDetail)
def get_asset(
    asset_id: int,
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(get_tenant_context),
) -> AssetDetail:
    asset = get_asset_or_404(db, asset_id, ctx)
    return serialize_asset_detail(db, asset)


@router.get("/{asset_id}/telemetry", response_model=list[TelemetryPoint])
def get_asset_telemetry(
    asset_id: int,
    hours: int = Query(default=24, ge=1, le=720),
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(get_tenant_context),
) -> list[TelemetryPoint]:
    # Scoped lookup first: a cross-tenant asset 404s before any telemetry is read.
    get_asset_or_404(db, asset_id, ctx)

    from datetime import timedelta

    since = utcnow() - timedelta(hours=hours)
    stmt = scope_telemetry(
        select(TelemetryLog).where(TelemetryLog.asset_id == asset_id, TelemetryLog.timestamp >= since),
        ctx,
    )
    rows = db.execute(stmt.order_by(TelemetryLog.timestamp)).scalars().all()
    return [TelemetryPoint.model_validate(r) for r in rows]


@router.get("/{asset_id}/events", response_model=list[AssetEventOut])
def get_asset_events(
    asset_id: int,
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(get_tenant_context),
) -> list[AssetEventOut]:
    get_asset_or_404(db, asset_id, ctx)

    stmt = select(AssetEvent).where(AssetEvent.asset_id == asset_id)
    # Company roles see the full history; a client sees only events from their
    # own tenancy, so a previous renter's activity is not disclosed.
    stmt = scope_events(stmt, ctx)
    rows = db.execute(stmt.order_by(AssetEvent.timestamp.desc()).limit(limit)).scalars().all()

    actor_ids = {r.actor_user_id for r in rows if r.actor_user_id}
    actors = {}
    if actor_ids:
        actors = {u.id: u for u in db.execute(select(User).where(User.id.in_(actor_ids))).scalars()}

    return [
        AssetEventOut(
            id=r.id,
            asset_id=r.asset_id,
            event_type=r.event_type,
            old_value=r.old_value,
            new_value=r.new_value,
            description=r.description,
            timestamp=asset_service._aware(r.timestamp),
            actor_name=actors[r.actor_user_id].full_name if r.actor_user_id in actors else None,
        )
        for r in rows
    ]


@router.post("/{asset_id}/assign-employee", response_model=AssetDetail)
def assign_employee(
    asset_id: int,
    payload: AssignEmployeeRequest,
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(get_tenant_context),
) -> AssetDetail:
    """Assign an operator.

    BOTH the asset and the employee go through tenant-scoped lookups, and
    ``assign_employee`` re-checks they belong to the same client. Checking only
    one side would leave a cross-tenant write open.
    """
    asset = get_asset_or_404(db, asset_id, ctx)
    employee = get_employee_or_404(db, payload.employee_id, ctx)

    rental_service.assign_employee(db, asset=asset, employee=employee, ctx=ctx)
    db.commit()
    db.refresh(asset)
    return serialize_asset_detail(db, asset)


@router.delete("/{asset_id}/assign-employee", response_model=AssetDetail)
def unassign_employee(
    asset_id: int,
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(get_tenant_context),
) -> AssetDetail:
    asset = get_asset_or_404(db, asset_id, ctx)
    rental_service.unassign_employee(db, asset=asset, ctx=ctx)
    db.commit()
    db.refresh(asset)
    return serialize_asset_detail(db, asset)


@router.post("", response_model=AssetDetail, status_code=status.HTTP_201_CREATED)
def create_asset(
    payload: AssetCreate,
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(require_admin),
) -> AssetDetail:
    """Add a machine to the fleet. Company admins only."""
    import secrets

    code = payload.asset_code
    if not code:
        # Continue the EQX#### sequence rather than restarting numbering.
        last = db.execute(select(func.max(Asset.asset_code)).where(Asset.asset_code.like("EQX%"))).scalar_one_or_none()
        next_num = (int(last[3:]) + 1) if last and last[3:].isdigit() else 1001
        code = f"EQX{next_num}"

    if db.execute(select(Asset).where(Asset.asset_code == code)).scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"Asset code {code} already exists")

    asset = Asset(
        asset_code=code,
        product_type=payload.product_type.value,
        model=payload.model,
        serial_number=payload.serial_number,
        status=AssetStatus.AVAILABLE.value,
        warehouse_status=WarehouseStatus.IN_WAREHOUSE.value,
        qr_token=f"QR-{code}-{secrets.token_hex(4).upper()}",
        daily_rate=payload.daily_rate,
        fuel_level=100.0,
        last_seen_at=utcnow(),
    )
    db.add(asset)
    db.flush()

    from app.models import EventType

    db.add(
        AssetEvent(
            asset_id=asset.id,
            actor_user_id=ctx.user_id,
            event_type=EventType.ASSET_CREATED.value,
            new_value=code,
            description=f"{payload.product_type.value} added to fleet",
            timestamp=utcnow(),
        )
    )
    db.commit()
    db.refresh(asset)
    return serialize_asset_detail(db, asset)


@router.patch("/{asset_id}/maintenance", response_model=AssetDetail)
def set_maintenance(
    asset_id: int,
    active: bool = Query(..., description="true starts maintenance, false completes it"),
    notes: str | None = None,
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(require_admin),
) -> AssetDetail:
    """Start or complete maintenance.

    Completing maintenance is the only path that restores component health to
    GOOD -- health degrades monotonically otherwise.
    """
    asset = get_asset_or_404(db, asset_id, ctx)
    rental_service.set_maintenance(db, asset=asset, active=active, actor_user_id=ctx.user_id, notes=notes)
    db.commit()
    db.refresh(asset)
    return serialize_asset_detail(db, asset)
