"""Alert endpoints -- the action queue."""

from fastapi import APIRouter, Depends, Query
from sqlalchemy import case, select
from sqlalchemy.orm import Session

from app.core.deps import (
    TenantContext,
    get_alert_or_404,
    get_tenant_context,
    scope_alerts,
)
from app.database import get_db
from app.models import Alert, AlertSeverity, AlertStatus, AlertType, Asset, Client, Site
from app.schemas.domain import AlertOut
from app.services import alert_service
from app.services.asset_service import _aware

router = APIRouter(prefix="/alerts", tags=["alerts"])

# Sort CRITICAL first, then HIGH, and so on -- the action queue must lead with
# what matters. Done in SQL so pagination stays correct.
SEVERITY_ORDER = case(
    {
        AlertSeverity.CRITICAL.value: 0,
        AlertSeverity.HIGH.value: 1,
        AlertSeverity.MEDIUM.value: 2,
        AlertSeverity.LOW.value: 3,
        AlertSeverity.INFO.value: 4,
    },
    value=Alert.severity,
    else_=5,
)


def serialize_alerts(db: Session, alerts: list[Alert]) -> list[AlertOut]:
    if not alerts:
        return []
    asset_ids = {a.asset_id for a in alerts if a.asset_id}
    client_ids = {a.client_id for a in alerts if a.client_id}
    site_ids = {a.site_id for a in alerts if a.site_id}

    assets = {}
    if asset_ids:
        assets = {a.id: a for a in db.execute(select(Asset).where(Asset.id.in_(asset_ids))).scalars()}
    clients = {}
    if client_ids:
        clients = {c.id: c for c in db.execute(select(Client).where(Client.id.in_(client_ids))).scalars()}
    sites = {}
    if site_ids:
        sites = {s.id: s for s in db.execute(select(Site).where(Site.id.in_(site_ids))).scalars()}

    return [
        AlertOut(
            id=a.id,
            asset_id=a.asset_id,
            asset_code=assets[a.asset_id].asset_code if a.asset_id in assets else None,
            client_id=a.client_id,
            client_name=clients[a.client_id].name if a.client_id in clients else None,
            site_id=a.site_id,
            site_code=sites[a.site_id].code if a.site_id in sites else None,
            type=a.type,
            severity=a.severity,
            title=a.title,
            description=a.description,
            reasons=a.reasons or [],
            recommended_action=a.recommended_action,
            source=a.source,
            score=a.score,
            status=a.status,
            created_at=_aware(a.created_at),
            acknowledged_at=_aware(a.acknowledged_at),
            resolved_at=_aware(a.resolved_at),
        )
        for a in alerts
    ]


@router.get("", response_model=list[AlertOut])
def list_alerts(
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(get_tenant_context),
    severity: AlertSeverity | None = None,
    type_filter: AlertType | None = Query(default=None, alias="type"),
    status_filter: AlertStatus | None = Query(default=None, alias="status"),
    include_resolved: bool = False,
    limit: int = Query(default=100, ge=1, le=500),
) -> list[AlertOut]:
    stmt = scope_alerts(select(Alert), ctx)

    if status_filter:
        stmt = stmt.where(Alert.status == status_filter.value)
    elif not include_resolved:
        # Default view is the live queue; resolved alerts are history.
        stmt = stmt.where(Alert.status.in_((AlertStatus.OPEN.value, AlertStatus.ACKNOWLEDGED.value)))

    if severity:
        stmt = stmt.where(Alert.severity == severity.value)
    if type_filter:
        stmt = stmt.where(Alert.type == type_filter.value)

    rows = db.execute(stmt.order_by(SEVERITY_ORDER, Alert.created_at.desc()).limit(limit)).scalars().all()
    return serialize_alerts(db, list(rows))


@router.patch("/{alert_id}/acknowledge", response_model=AlertOut)
def acknowledge_alert(
    alert_id: int,
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(get_tenant_context),
) -> AlertOut:
    alert = get_alert_or_404(db, alert_id, ctx)
    alert_service.acknowledge(db, alert, ctx.user_id)
    db.commit()
    db.refresh(alert)
    return serialize_alerts(db, [alert])[0]


@router.patch("/{alert_id}/resolve", response_model=AlertOut)
def resolve_alert(
    alert_id: int,
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(get_tenant_context),
) -> AlertOut:
    alert = get_alert_or_404(db, alert_id, ctx)
    alert_service.resolve(db, alert, ctx.user_id)
    db.commit()
    db.refresh(alert)
    return serialize_alerts(db, [alert])[0]
