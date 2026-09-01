"""Dashboard endpoints -- one aggregate response per role."""

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.deps import (
    TenantContext,
    get_tenant_context,
    require_admin,
    require_client,
    scope_alerts,
    scope_assets,
    scope_recommendations,
)
from app.database import get_db
from app.models import (
    Alert,
    AlertStatus,
    Asset,
    Forecast,
    Recommendation,
    RecommendationStatus,
    utcnow,
)
from app.routes.alerts import SEVERITY_ORDER, serialize_alerts
from app.routes.intelligence import serialize_forecasts, serialize_recommendations
from app.routes.sites import build_site_stats
from app.schemas.dashboard import ClientDashboard, CompanyDashboard
from app.services import dashboard_service
from app.services.asset_service import serialize_assets

router = APIRouter(prefix="/dashboard", tags=["dashboard"])

LIVE = (AlertStatus.OPEN.value, AlertStatus.ACKNOWLEDGED.value)


@router.get("/client", response_model=ClientDashboard)
def client_dashboard(
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(require_client),
) -> ClientDashboard:
    """Everything the client overview screen needs, in one round trip."""
    assets = db.execute(
        scope_assets(select(Asset), ctx).order_by(Asset.asset_code)
    ).scalars().all()

    alerts = db.execute(
        scope_alerts(select(Alert).where(Alert.status.in_(LIVE)), ctx)
        .order_by(SEVERITY_ORDER, Alert.created_at.desc())
        .limit(50)
    ).scalars().all()

    recommendations = db.execute(
        scope_recommendations(
            select(Recommendation).where(Recommendation.status != RecommendationStatus.DISMISSED.value), ctx
        )
        .order_by(Recommendation.created_at.desc())
        .limit(10)
    ).scalars().all()

    return ClientDashboard(
        kpis=dashboard_service.client_kpis(db, ctx),
        assets=serialize_assets(db, list(assets)),
        alerts=serialize_alerts(db, list(alerts)),
        utilization_trend=dashboard_service.utilization_trend(db, ctx),
        by_product_type=dashboard_service.product_type_stats(db, ctx),
        recommendations=serialize_recommendations(db, list(recommendations)),
        generated_at=utcnow().isoformat(),
    )


@router.get("/company", response_model=CompanyDashboard)
def company_dashboard(
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(require_admin),
) -> CompanyDashboard:
    """The control tower: what is happening, what is wrong, what next, what to do."""
    action_queue = db.execute(
        select(Alert)
        .where(Alert.status.in_(LIVE))
        .order_by(SEVERITY_ORDER, Alert.created_at.desc())
        .limit(40)
    ).scalars().all()

    latest_forecast_date = db.execute(select(Forecast.forecast_date).order_by(Forecast.forecast_date.desc()).limit(1)).scalar_one_or_none()
    forecasts = []
    if latest_forecast_date is not None:
        forecasts = db.execute(
            select(Forecast)
            .where(Forecast.forecast_date == latest_forecast_date)
            .order_by(Forecast.expected_shortfall.desc())
        ).scalars().all()

    recommendations = db.execute(
        select(Recommendation)
        .where(Recommendation.status != RecommendationStatus.DISMISSED.value)
        .order_by(Recommendation.created_at.desc())
        .limit(15)
    ).scalars().all()

    return CompanyDashboard(
        kpis=dashboard_service.company_kpis(db, ctx),
        sites=build_site_stats(db, ctx),
        action_queue=serialize_alerts(db, list(action_queue)),
        utilization_trend=dashboard_service.utilization_trend(db, ctx),
        by_product_type=dashboard_service.product_type_stats(db, ctx),
        forecasts=serialize_forecasts(db, list(forecasts)),
        recommendations=serialize_recommendations(db, list(recommendations)),
        generated_at=utcnow().isoformat(),
    )
