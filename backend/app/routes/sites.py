"""Site endpoints -- includes the live stats the map markers render."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.deps import (
    TenantContext,
    get_tenant_context,
    require_admin,
    scope_assets,
)
from app.database import get_db
from app.models import Alert, AlertSeverity, AlertStatus, Asset, AssetStatus, Site
from app.schemas.domain import AssetOut, SiteCreate, SiteOut, SiteWithStats
from app.services.asset_service import serialize_assets

router = APIRouter(prefix="/sites", tags=["sites"])

SEVERE = (AlertSeverity.CRITICAL.value, AlertSeverity.HIGH.value)
LIVE_ALERTS = (AlertStatus.OPEN.value, AlertStatus.ACKNOWLEDGED.value)


def build_site_stats(db: Session, ctx: TenantContext) -> list[SiteWithStats]:
    """Sites with deployed/active/idle/anomaly counts.

    Clients see only sites where they currently have equipment; showing them the
    company's full site list would leak where other tenants operate.
    """
    site_stmt = select(Site).where(Site.active.is_(True))

    if not ctx.is_admin:
        visible = select(Asset.current_site_id).where(
            Asset.current_client_id == ctx.client_id, Asset.current_site_id.is_not(None)
        )
        site_ids = {row for row in db.execute(visible).scalars() if row is not None}
        if not site_ids:
            return []
        site_stmt = site_stmt.where(Site.id.in_(site_ids))

    sites = db.execute(site_stmt.order_by(Site.code)).scalars().all()
    if not sites:
        return []

    site_ids = [s.id for s in sites]

    # Asset counts per site, tenant-scoped.
    counts_stmt = scope_assets(
        select(Asset.current_site_id, Asset.status, func.count(Asset.id))
        .where(Asset.current_site_id.in_(site_ids))
        .group_by(Asset.current_site_id, Asset.status),
        ctx,
    )
    deployed: dict[int, int] = {}
    active: dict[int, int] = {}
    idle: dict[int, int] = {}
    for site_id, asset_status, count in db.execute(counts_stmt).all():
        deployed[site_id] = deployed.get(site_id, 0) + count
        if asset_status == AssetStatus.ACTIVE.value:
            active[site_id] = active.get(site_id, 0) + count
        elif asset_status in (AssetStatus.IDLE.value, AssetStatus.RENTED.value):
            idle[site_id] = idle.get(site_id, 0) + count

    # Utilisation per site from the live counters.
    util_stmt = scope_assets(
        select(
            Asset.current_site_id,
            func.sum(Asset.runtime_minutes_today),
            func.sum(Asset.idle_minutes_today),
        )
        .where(Asset.current_site_id.in_(site_ids))
        .group_by(Asset.current_site_id),
        ctx,
    )
    utilization: dict[int, float] = {}
    for site_id, runtime, idle_mins in db.execute(util_stmt).all():
        denom = (runtime or 0) + (idle_mins or 0)
        utilization[site_id] = (runtime or 0) / denom if denom else 0.0

    # Severe live alerts per site.
    alert_stmt = select(Alert.site_id, func.count(Alert.id)).where(
        Alert.site_id.in_(site_ids),
        Alert.status.in_(LIVE_ALERTS),
        Alert.severity.in_(SEVERE),
    )
    if not ctx.is_admin:
        alert_stmt = alert_stmt.where(Alert.client_id == ctx.client_id)
    anomalies = dict(db.execute(alert_stmt.group_by(Alert.site_id)).all())

    return [
        SiteWithStats(
            id=s.id,
            code=s.code,
            name=s.name,
            address=s.address,
            latitude=s.latitude,
            longitude=s.longitude,
            client_id=s.client_id,
            is_warehouse=s.is_warehouse,
            active=s.active,
            deployed_assets=deployed.get(s.id, 0),
            active_assets=active.get(s.id, 0),
            idle_assets=idle.get(s.id, 0),
            anomaly_count=anomalies.get(s.id, 0),
            utilization=round(utilization.get(s.id, 0.0), 4),
        )
        for s in sites
    ]


@router.get("", response_model=list[SiteWithStats])
def list_sites(
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(get_tenant_context),
) -> list[SiteWithStats]:
    return build_site_stats(db, ctx)


@router.post("", response_model=SiteOut, status_code=status.HTTP_201_CREATED)
def create_site(
    payload: SiteCreate,
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(require_admin),
) -> SiteOut:
    """Add a site. Company admins only (403 for clients -- the route is not a secret)."""
    if db.execute(select(Site).where(Site.code == payload.code)).scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"Site code {payload.code} already exists")

    site = Site(
        code=payload.code.strip().upper(),
        name=payload.name.strip(),
        address=payload.address,
        latitude=payload.latitude,
        longitude=payload.longitude,
        client_id=payload.client_id,
        is_warehouse=payload.is_warehouse,
        active=True,
    )
    db.add(site)
    db.commit()
    db.refresh(site)
    return SiteOut.model_validate(site)


@router.get("/{site_id}/assets", response_model=list[AssetOut])
def site_assets(
    site_id: int,
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(get_tenant_context),
) -> list[AssetOut]:
    """Assets deployed at a site, tenant-scoped.

    No 404 for an out-of-scope site: the scoped query simply returns nothing,
    which discloses neither the site's existence nor its contents.
    """
    stmt = scope_assets(select(Asset).where(Asset.current_site_id == site_id), ctx)
    rows = db.execute(stmt.order_by(Asset.asset_code)).scalars().all()
    return serialize_assets(db, list(rows))
