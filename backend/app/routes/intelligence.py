"""Forecast and recommendation endpoints."""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.deps import (
    TenantContext,
    get_recommendation_or_404,
    get_tenant_context,
    require_admin,
    require_client,
    scope_recommendations,
)
from app.database import get_db
from app.models import (
    Asset,
    Client,
    Forecast,
    ProductType,
    Recommendation,
    RecommendationStatus,
    Site,
    utcnow,
)
from app.schemas.domain import ForecastOut, RecommendationOut
from app.services.asset_service import _aware

router = APIRouter(tags=["intelligence"])


def serialize_forecasts(db: Session, forecasts: list[Forecast]) -> list[ForecastOut]:
    if not forecasts:
        return []
    site_ids = {f.site_id for f in forecasts}
    sites = {s.id: s for s in db.execute(select(Site).where(Site.id.in_(site_ids))).scalars()}
    return [
        ForecastOut(
            id=f.id,
            site_id=f.site_id,
            site_code=sites[f.site_id].code if f.site_id in sites else None,
            site_name=sites[f.site_id].name if f.site_id in sites else None,
            product_type=f.product_type,
            forecast_date=f.forecast_date,
            horizon_days=f.horizon_days,
            predicted_demand=round(f.predicted_demand, 2),
            currently_available=f.currently_available,
            expected_shortfall=round(f.expected_shortfall, 2),
            model_version=f.model_version,
        )
        for f in forecasts
    ]


def serialize_recommendations(db: Session, recs: list[Recommendation]) -> list[RecommendationOut]:
    if not recs:
        return []
    site_ids = {r.site_id for r in recs if r.site_id}
    client_ids = {r.client_id for r in recs if r.client_id}
    asset_ids = {r.asset_id for r in recs if r.asset_id}

    sites = {s.id: s for s in db.execute(select(Site).where(Site.id.in_(site_ids))).scalars()} if site_ids else {}
    clients = {c.id: c for c in db.execute(select(Client).where(Client.id.in_(client_ids))).scalars()} if client_ids else {}
    assets = {a.id: a for a in db.execute(select(Asset).where(Asset.id.in_(asset_ids))).scalars()} if asset_ids else {}

    return [
        RecommendationOut(
            id=r.id,
            client_id=r.client_id,
            client_name=clients[r.client_id].name if r.client_id in clients else None,
            site_id=r.site_id,
            site_code=sites[r.site_id].code if r.site_id in sites else None,
            asset_id=r.asset_id,
            asset_code=assets[r.asset_id].asset_code if r.asset_id in assets else None,
            type=r.type,
            title=r.title,
            description=r.description,
            rationale=r.rationale or [],
            product_type=r.product_type,
            quantity=r.quantity,
            status=r.status,
            created_at=_aware(r.created_at),
        )
        for r in recs
    ]


# ---------------------------------------------------------------------------
# Forecast
# ---------------------------------------------------------------------------


@router.get("/forecast", response_model=list[ForecastOut])
def get_forecast(
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(get_tenant_context),
    site_id: int | None = None,
    product_type: ProductType | None = None,
    horizon: int = Query(default=7, ge=1, le=30),
) -> list[ForecastOut]:
    """Demand forecast by site and product type.

    Clients see forecasts only for sites where they currently have equipment --
    the company's demand picture at other sites is not theirs to see.
    """
    stmt = select(Forecast).where(Forecast.horizon_days <= horizon)

    if not ctx.is_admin:
        visible = select(Asset.current_site_id).where(
            Asset.current_client_id == ctx.client_id, Asset.current_site_id.is_not(None)
        )
        site_ids = {row for row in db.execute(visible).scalars() if row is not None}
        if not site_ids:
            return []
        stmt = stmt.where(Forecast.site_id.in_(site_ids))

    if site_id is not None:
        stmt = stmt.where(Forecast.site_id == site_id)
    if product_type is not None:
        stmt = stmt.where(Forecast.product_type == product_type.value)

    rows = db.execute(
        stmt.order_by(Forecast.forecast_date, Forecast.expected_shortfall.desc())
    ).scalars().all()
    return serialize_forecasts(db, list(rows))


@router.post("/forecast/regenerate", response_model=dict)
def regenerate_forecast(
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(require_admin),
) -> dict:
    """Re-run the demand model and the recommendation rules that depend on it."""
    from app.ml.forecast import generate_forecasts
    from app.services.recommendation_service import regenerate_all

    forecast_result = generate_forecasts(db)
    reco_result = regenerate_all(db)
    return {"forecast": forecast_result, "recommendations": reco_result}


# ---------------------------------------------------------------------------
# Recommendations
# ---------------------------------------------------------------------------


@router.get("/recommendations", response_model=list[RecommendationOut])
def list_recommendations(
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(get_tenant_context),
    include_dismissed: bool = False,
    limit: int = Query(default=50, ge=1, le=200),
) -> list[RecommendationOut]:
    stmt = scope_recommendations(select(Recommendation), ctx)
    if not include_dismissed:
        stmt = stmt.where(Recommendation.status != RecommendationStatus.DISMISSED.value)
    rows = db.execute(stmt.order_by(Recommendation.created_at.desc()).limit(limit)).scalars().all()
    return serialize_recommendations(db, list(rows))


@router.post("/recommendations/{rec_id}/request", response_model=RecommendationOut)
def request_recommendation(
    rec_id: int,
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(require_client),
) -> RecommendationOut:
    """Client acts on a recommendation: 'Request More Assets'.

    The MVP records the request so the company sees demand signal. No payment
    or fulfilment flow -- out of scope for the hackathon.
    """
    rec = get_recommendation_or_404(db, rec_id, ctx)

    if rec.status == RecommendationStatus.REQUESTED.value:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This request has already been submitted.",
        )

    rec.status = RecommendationStatus.REQUESTED.value
    rec.requested_at = utcnow()
    rec.requested_by_user_id = ctx.user_id
    db.commit()
    db.refresh(rec)
    return serialize_recommendations(db, [rec])[0]


@router.patch("/recommendations/{rec_id}/dismiss", response_model=RecommendationOut)
def dismiss_recommendation(
    rec_id: int,
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(get_tenant_context),
) -> RecommendationOut:
    rec = get_recommendation_or_404(db, rec_id, ctx)
    rec.status = RecommendationStatus.DISMISSED.value
    db.commit()
    db.refresh(rec)
    return serialize_recommendations(db, [rec])[0]
