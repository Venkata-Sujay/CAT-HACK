"""Demand forecast inference.

Predicts rental demand per (site, product_type) for a future horizon, compares
it against what is actually available, and persists the shortfall.

If the model artifact is missing the system does NOT go blind: it falls back to
a 7-day rolling average -- the same baseline the model is benchmarked against
during training. A degraded forecast is far more useful in a demo than an empty
screen, and the response says which path produced the number.
"""

import logging
from datetime import date, timedelta

import numpy as np
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.ml.registry import model_registry
from app.models import (
    Asset,
    AssetStatus,
    Forecast,
    ProductType,
    Rental,
    Site,
    WarehouseStatus,
    utcnow,
)

logger = logging.getLogger("rental.ml.forecast")


def _historical_demand(db: Session, site_id: int, product_type: str, days: int = 30) -> list[float]:
    """Daily count of rentals active at this site for this type, most recent last."""
    today = utcnow().date()
    start = today - timedelta(days=days)

    rows = db.execute(
        select(Rental.checkout_at, Rental.expected_return_at, Rental.actual_return_at)
        .join(Asset, Asset.id == Rental.asset_id)
        .where(Rental.site_id == site_id, Asset.product_type == product_type)
    ).all()

    series = []
    for offset in range(days):
        day = start + timedelta(days=offset)
        count = 0
        for checkout, expected, actual in rows:
            if checkout is None:
                continue
            c = checkout.date() if hasattr(checkout, "date") else checkout
            end = actual or expected
            e = end.date() if hasattr(end, "date") else end
            if c <= day <= e:
                count += 1
        series.append(float(count))
    return series


def _baseline(series: list[float], window: int = 7) -> float:
    """7-day rolling mean -- the benchmark the ML model must beat."""
    if not series:
        return 0.0
    tail = series[-window:]
    return float(np.mean(tail)) if tail else 0.0


def _build_features(series: list[float], site_index: int, product_index: int, target_day: date, utilization: float, active: int) -> list[float]:
    """Assemble one demand feature row. Order must match ml.features.DEMAND_FEATURES."""
    prev_day = series[-1] if series else 0.0
    prev_week = series[-7] if len(series) >= 7 else prev_day

    def roll(n: int) -> float:
        tail = series[-n:] if series else []
        return float(np.mean(tail)) if tail else 0.0

    iso = target_day.isocalendar()
    return [
        float(site_index),
        float(product_index),
        float(target_day.weekday()),
        float(iso.week),
        float(target_day.month),
        1.0 if target_day.weekday() >= 5 else 0.0,
        prev_day,
        prev_week,
        roll(7),
        roll(14),
        roll(30),
        utilization,
        float(active),
    ]


def generate_forecasts(db: Session, horizon_days: int = 7, commit: bool = True) -> dict:
    """Forecast demand for every (site, product_type) and persist the results."""
    sites = db.execute(select(Site).where(Site.active.is_(True), Site.is_warehouse.is_(False))).scalars().all()
    if not sites:
        return {"generated": 0, "reason": "no active sites"}

    bundle = model_registry.demand_bundle
    model = bundle.get("model") if bundle else None
    encoders = bundle.get("encoders", {}) if bundle else {}
    model_version = (bundle.get("metadata", {}) or {}).get("model_version", "baseline-rolling-7d") if bundle else "baseline-rolling-7d"
    used_model = model is not None

    target_day = utcnow().date() + timedelta(days=horizon_days)

    # Clear previous forecasts for this target so regeneration is idempotent.
    existing = db.execute(select(Forecast).where(Forecast.forecast_date == target_day)).scalars().all()
    for row in existing:
        db.delete(row)
    db.flush()

    site_codes = {s.code: i for i, s in enumerate(sorted(sites, key=lambda s: s.code))}
    product_index = {pt.value: i for i, pt in enumerate(ProductType)}

    generated = 0
    for site in sites:
        for product in ProductType:
            series = _historical_demand(db, site.id, product.value)

            # What is actually on hand at this site right now.
            available_here = db.execute(
                select(func.count(Asset.id)).where(
                    Asset.current_site_id == site.id,
                    Asset.product_type == product.value,
                    Asset.status.in_(
                        (AssetStatus.ACTIVE.value, AssetStatus.IDLE.value, AssetStatus.RENTED.value)
                    ),
                )
            ).scalar_one() or 0

            util_row = db.execute(
                select(func.sum(Asset.runtime_minutes_today), func.sum(Asset.idle_minutes_today)).where(
                    Asset.current_site_id == site.id, Asset.product_type == product.value
                )
            ).one()
            denom = (util_row[0] or 0) + (util_row[1] or 0)
            utilization = (util_row[0] or 0) / denom if denom else 0.0

            if used_model:
                row = _build_features(
                    series,
                    site_codes.get(site.code, 0),
                    product_index[product.value],
                    target_day,
                    utilization,
                    available_here,
                )
                try:
                    predicted = float(model.predict([row])[0])
                except Exception:  # noqa: BLE001 - fall back rather than fail the sweep
                    logger.exception("Demand prediction failed for %s/%s", site.code, product.value)
                    predicted = _baseline(series)
            else:
                predicted = _baseline(series)

            predicted = max(0.0, predicted)

            # Nothing to say about a site that has never used this equipment.
            if predicted < 0.05 and available_here == 0 and sum(series) == 0:
                continue

            shortfall = max(0.0, predicted - available_here)

            db.add(
                Forecast(
                    site_id=site.id,
                    product_type=product.value,
                    forecast_date=target_day,
                    horizon_days=horizon_days,
                    predicted_demand=round(predicted, 2),
                    currently_available=available_here,
                    expected_shortfall=round(shortfall, 2),
                    model_version=model_version,
                    generated_at=utcnow(),
                )
            )
            generated += 1

    if commit:
        db.commit()

    return {
        "generated": generated,
        "forecast_date": target_day.isoformat(),
        "horizon_days": horizon_days,
        "source": "model" if used_model else "baseline-rolling-7d",
        "model_version": model_version,
    }
