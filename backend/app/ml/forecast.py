"""Demand forecast inference.

Predicts rental demand per (site, product_type) for every day across a horizon,
compares each day against the equipment that will actually be on site, and
persists the shortfall.

Three things are worth knowing before editing this file:

1. **The forecast is recursive, not single-shot.** The model's strongest
   features are lags (`prev_day_demand`, `rolling_7d_mean`, `rolling_30d_mean`).
   To predict day D+3 you need day D+2, which you do not have. So each
   prediction is appended to the working series and feeds the next day's
   features. This is the standard way to run a multi-step forecast off a
   lag-feature regressor, and it is why uncertainty grows with horizon --
   errors compound.

2. **Availability is PROJECTED, not frozen.** A site's stock is not constant:
   rentals come off-hire on known dates and those machines go back to the
   depot. Holding availability flat would hide the most useful finding this
   system produces -- "you have 3 today, two come off-hire Thursday, and demand
   rises to 3.3 on Friday". Each day's row carries that day's projected count.

3. **A missing artifact is not a blank screen.** With no model, this falls back
   to the 7-day rolling average -- the same baseline the model is benchmarked
   against in training -- and reports `source: "baseline-rolling-7d"`.
"""

import logging
from collections import defaultdict
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
    RentalStatus,
    Site,
    utcnow,
)

logger = logging.getLogger("rental.ml.forecast")

# 45 days of history so the 30-day rolling feature is fully populated on day 1
# of the horizon rather than being averaged over a short, noisy window.
HISTORY_DAYS = 45
DEFAULT_HORIZON = 14

ON_SITE_STATUSES = (
    AssetStatus.ACTIVE.value,
    AssetStatus.IDLE.value,
    AssetStatus.RENTED.value,
    AssetStatus.OVERDUE.value,
)


def _historical_demand(
    db: Session,
    site_id: int,
    product_type: str,
    days: int = HISTORY_DAYS,
    include_today: bool = False,
) -> list[float]:
    """Daily count of rentals active at this site for this type, oldest first.

    Ends at YESTERDAY by default: feature lags must not be built from a day that
    is still in progress. `include_today=True` is for the timeline chart, where
    omitting today would leave a visible one-day hole between the history line
    and the forecast line.
    """
    today = utcnow().date()
    span = days + 1 if include_today else days
    start = today - timedelta(days=days)

    rows = db.execute(
        select(Rental.checkout_at, Rental.expected_return_at, Rental.actual_return_at)
        .join(Asset, Asset.id == Rental.asset_id)
        .where(Rental.site_id == site_id, Asset.product_type == product_type)
    ).all()

    series = []
    for offset in range(span):
        day = start + timedelta(days=offset)
        count = 0
        for checkout, expected, actual in rows:
            if checkout is None:
                continue
            c = checkout.date() if hasattr(checkout, "date") else checkout
            end = actual or expected
            if end is None:
                continue
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


def _build_features(
    series: list[float],
    site_index: int,
    product_index: int,
    target_day: date,
    utilization: float,
    active: int,
) -> list[float]:
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


def _availability_schedule(
    db: Session, site_id: int, product_type: str, today: date, horizon_days: int
) -> dict[date, int]:
    """Projected on-site count of this equipment type, per day across the horizon.

    Starts from what is physically on site now and steps DOWN on each day a
    rental is scheduled to end, because a returned machine goes back to the
    depot. Rentals already overdue are treated as still on site -- they are.
    """
    on_site = (
        db.execute(
            select(Asset.id).where(
                Asset.current_site_id == site_id,
                Asset.product_type == product_type,
                Asset.status.in_(ON_SITE_STATUSES),
            )
        )
        .scalars()
        .all()
    )

    if not on_site:
        return {today + timedelta(days=d): 0 for d in range(horizon_days + 1)}

    # When does each of those machines come off hire?
    returns: dict[date, int] = defaultdict(int)
    due_rows = db.execute(
        select(Rental.asset_id, Rental.expected_return_at).where(
            Rental.asset_id.in_(on_site),
            Rental.status.in_((RentalStatus.ACTIVE.value, RentalStatus.OVERDUE.value)),
        )
    ).all()
    for _asset_id, expected in due_rows:
        if expected is None:
            continue
        due = expected.date() if hasattr(expected, "date") else expected
        if due > today:
            returns[due] += 1

    schedule: dict[date, int] = {}
    running = len(on_site)
    for offset in range(horizon_days + 1):
        day = today + timedelta(days=offset)
        running -= returns.get(day, 0)
        schedule[day] = max(0, running)
    return schedule


def generate_forecasts(
    db: Session,
    horizon_days: int = DEFAULT_HORIZON,
    commit: bool = True,
) -> dict:
    """Forecast demand for every (site, product_type) across the horizon."""
    sites = (
        db.execute(select(Site).where(Site.active.is_(True), Site.is_warehouse.is_(False)))
        .scalars()
        .all()
    )
    if not sites:
        return {"generated": 0, "reason": "no active sites"}

    bundle = model_registry.demand_bundle
    model = bundle.get("model") if bundle else None
    model_version = (
        (bundle.get("metadata", {}) or {}).get("model_version", "baseline-rolling-7d")
        if bundle
        else "baseline-rolling-7d"
    )
    used_model = model is not None

    today = utcnow().date()
    horizon_end = today + timedelta(days=horizon_days)

    # Regeneration is idempotent: drop every forecast at or after today rather
    # than only one target date, otherwise a shorter horizon leaves orphan rows
    # from a previous longer run sitting in the chart.
    for row in db.execute(select(Forecast).where(Forecast.forecast_date >= today)).scalars().all():
        db.delete(row)
    db.flush()

    site_codes = {s.code: i for i, s in enumerate(sorted(sites, key=lambda s: s.code))}
    product_index = {pt.value: i for i, pt in enumerate(ProductType)}

    generated = 0

    for site in sites:
        for product in ProductType:
            history = _historical_demand(db, site.id, product.value)
            availability = _availability_schedule(
                db, site.id, product.value, today, horizon_days
            )

            util_row = db.execute(
                select(
                    func.sum(Asset.runtime_minutes_today),
                    func.sum(Asset.idle_minutes_today),
                ).where(
                    Asset.current_site_id == site.id,
                    Asset.product_type == product.value,
                )
            ).one()
            denom = (util_row[0] or 0) + (util_row[1] or 0)
            utilization = (util_row[0] or 0) / denom if denom else 0.0

            # Nothing to say about a site that has never used this equipment
            # and holds none of it.
            if sum(history) == 0 and availability[today] == 0:
                continue

            # Recursive multi-step: each prediction becomes the next day's lag.
            working = list(history)
            for offset in range(1, horizon_days + 1):
                target_day = today + timedelta(days=offset)
                available = availability.get(target_day, availability[today])

                if used_model:
                    row = _build_features(
                        working,
                        site_codes.get(site.code, 0),
                        product_index[product.value],
                        target_day,
                        utilization,
                        available,
                    )
                    try:
                        predicted = float(model.predict([row])[0])
                    except Exception:  # noqa: BLE001 - degrade, never fail the sweep
                        logger.exception(
                            "Demand prediction failed for %s/%s", site.code, product.value
                        )
                        predicted = _baseline(working)
                else:
                    predicted = _baseline(working)

                predicted = max(0.0, predicted)
                working.append(predicted)

                db.add(
                    Forecast(
                        site_id=site.id,
                        product_type=product.value,
                        forecast_date=target_day,
                        horizon_days=offset,
                        predicted_demand=round(predicted, 2),
                        currently_available=available,
                        expected_shortfall=round(max(0.0, predicted - available), 2),
                        model_version=model_version,
                        generated_at=utcnow(),
                    )
                )
                generated += 1

    if commit:
        db.commit()

    return {
        "generated": generated,
        "horizon_days": horizon_days,
        "first_date": (today + timedelta(days=1)).isoformat(),
        "last_date": horizon_end.isoformat(),
        "source": "model" if used_model else "baseline-rolling-7d",
        "model_version": model_version,
        "method": "recursive multi-step" if used_model else "rolling-mean baseline",
    }


def demand_timeline(
    db: Session,
    site_id: int,
    product_type: str,
    history_days: int = 21,
) -> dict:
    """History + forecast for one (site, product), shaped for a single chart.

    The two series overlap on exactly one point -- today -- so the line joins
    cleanly instead of showing a visual break between what happened and what is
    predicted.
    """
    today = utcnow().date()
    history = _historical_demand(
        db, site_id, product_type, days=history_days, include_today=True
    )
    start = today - timedelta(days=history_days)

    points: list[dict] = []
    for offset, value in enumerate(history):
        day = start + timedelta(days=offset)
        points.append(
            {
                "date": day.isoformat(),
                "actual": value,
                "predicted": None,
                "available": None,
                "is_forecast": False,
            }
        )

    rows = (
        db.execute(
            select(Forecast)
            .where(
                Forecast.site_id == site_id,
                Forecast.product_type == product_type,
                Forecast.forecast_date >= today,
            )
            .order_by(Forecast.forecast_date)
        )
        .scalars()
        .all()
    )

    # Join the seam: the last historical point also carries the first predicted
    # value so the chart draws one continuous line instead of two broken ones.
    if points and rows:
        points[-1]["predicted"] = points[-1]["actual"]
        points[-1]["available"] = rows[0].currently_available

    for row in rows:
        points.append(
            {
                "date": row.forecast_date.isoformat(),
                "actual": None,
                "predicted": round(row.predicted_demand, 2),
                "available": row.currently_available,
                "is_forecast": True,
            }
        )

    return {
        "site_id": site_id,
        "product_type": product_type,
        "today": today.isoformat(),
        "model_version": rows[0].model_version if rows else None,
        "points": points,
    }
