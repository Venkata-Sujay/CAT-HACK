"""Recommendation engine -- deliberately rule-based, not a third ML model.

A learned recommender trained on synthetic data would be unexplainable and
untrustworthy. These rules compose three signals the system already computes
well -- forecast demand, current inventory, and observed utilisation -- and can
state exactly why they fired. That is more useful to an operator than a score.

Rules
-----
COMPANY
  PREPOSITION_ASSET     forecast shortfall at a site + spare stock elsewhere
  RETURN_UNDERUTILIZED  rented machine with sustained near-zero utilisation
CLIENT
  REQUEST_MORE_ASSETS   fleet utilisation above threshold for a product type
"""

import logging

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import settings
from app.models import (
    Asset,
    AssetStatus,
    Client,
    Forecast,
    ProductType,
    Recommendation,
    RecommendationStatus,
    RecommendationType,
    Site,
    WarehouseStatus,
    utcnow,
)

logger = logging.getLogger("rental.reco")


def _upsert(
    db: Session,
    *,
    dedupe_key: str,
    client_id: int | None,
    site_id: int | None,
    asset_id: int | None,
    rec_type: RecommendationType,
    title: str,
    description: str,
    rationale: list[str],
    product_type: str | None,
    quantity: int,
) -> Recommendation:
    """Create or refresh a recommendation.

    Same deduplication reasoning as alerts: this runs on a schedule and must not
    accumulate duplicates. A recommendation the user already acted on
    (REQUESTED/DISMISSED) is left alone.
    """
    existing = db.execute(select(Recommendation).where(Recommendation.dedupe_key == dedupe_key)).scalar_one_or_none()

    if existing is not None:
        if existing.status == RecommendationStatus.OPEN.value:
            existing.title = title
            existing.description = description
            existing.rationale = rationale
            existing.quantity = quantity
        return existing

    rec = Recommendation(
        client_id=client_id,
        site_id=site_id,
        asset_id=asset_id,
        type=rec_type.value,
        title=title,
        description=description,
        rationale=rationale,
        product_type=product_type,
        quantity=quantity,
        status=RecommendationStatus.OPEN.value,
        dedupe_key=dedupe_key,
        created_at=utcnow(),
    )
    db.add(rec)
    return rec


def generate_company_recommendations(db: Session) -> int:
    """Pre-positioning suggestions driven by forecast shortfalls."""
    created = 0

    # The forecast now spans every day of the horizon, so a (site, type) pair can
    # show a shortfall on several days. Take the EARLIEST one: "you run short on
    # Thursday" is actionable, "you might run short in two weeks" is not, and the
    # near-horizon prediction is also the more reliable of the two because
    # recursive forecasting compounds error with distance.
    rows = db.execute(
        select(Forecast)
        .where(Forecast.expected_shortfall > 0.5)
        .order_by(Forecast.forecast_date)
    ).scalars().all()
    if not rows:
        return 0

    first_shortfall: dict[tuple[int, str], Forecast] = {}
    for row in rows:
        key = (row.site_id, row.product_type)
        if key not in first_shortfall:
            first_shortfall[key] = row

    shortfalls = sorted(
        first_shortfall.values(),
        key=lambda f: (f.forecast_date, -f.expected_shortfall),
    )

    for forecast in shortfalls:
        site = db.get(Site, forecast.site_id)
        if site is None:
            continue

        # Spare stock of this type sitting in the warehouse.
        spare = db.execute(
            select(func.count(Asset.id)).where(
                Asset.product_type == forecast.product_type,
                Asset.status == AssetStatus.AVAILABLE.value,
                Asset.warehouse_status == WarehouseStatus.IN_WAREHOUSE.value,
            )
        ).scalar_one() or 0

        needed = int(round(forecast.expected_shortfall))
        if needed <= 0:
            continue

        movable = min(spare, needed)
        readable_type = forecast.product_type.replace("_", " ").title()
        days_out = max(0, forecast.horizon_days)

        if movable > 0:
            title = f"Pre-position {movable} {readable_type}(s) to {site.code}"
            description = (
                f"{site.name} runs short of {readable_type}s in {days_out} day(s), on "
                f"{forecast.forecast_date:%a %d %b}. Demand is forecast at "
                f"{forecast.predicted_demand:.1f} against {forecast.currently_available} "
                f"projected on site -- a shortfall of {forecast.expected_shortfall:.1f}. "
                f"{spare} unit(s) of this type are idle in the warehouse and could be moved "
                "ahead of demand."
            )
            rationale = [
                f"Shortfall first appears: {forecast.forecast_date:%a %d %b} ({days_out} days out)",
                f"Forecast demand: {forecast.predicted_demand:.1f}",
                f"Projected available at site that day: {forecast.currently_available}",
                f"Expected shortfall: {forecast.expected_shortfall:.1f}",
                f"Warehouse stock available now: {spare}",
            ]
        else:
            title = f"{readable_type} shortage expected at {site.code}"
            description = (
                f"{site.name} runs short of {readable_type}s in {days_out} day(s), on "
                f"{forecast.forecast_date:%a %d %b} -- demand "
                f"{forecast.predicted_demand:.1f} against {forecast.currently_available} "
                f"projected on site, a shortfall of {forecast.expected_shortfall:.1f}. "
                "There is no spare stock of this type in the warehouse. "
                "Consider recalling an under-utilised unit from another site."
            )
            rationale = [
                f"Shortfall first appears: {forecast.forecast_date:%a %d %b} ({days_out} days out)",
                f"Forecast demand: {forecast.predicted_demand:.1f}",
                f"Expected shortfall: {forecast.expected_shortfall:.1f}",
                "No warehouse stock of this type available",
            ]

        _upsert(
            db,
            dedupe_key=f"company:preposition:{forecast.site_id}:{forecast.product_type}",
            client_id=None,
            site_id=forecast.site_id,
            asset_id=None,
            rec_type=RecommendationType.PREPOSITION_ASSET,
            title=title,
            description=description,
            rationale=rationale,
            product_type=forecast.product_type,
            quantity=max(movable, needed),
        )
        created += 1

    return created


def generate_client_recommendations(db: Session) -> int:
    """Per-client 'you may need more equipment' suggestions.

    Fires when a client's fleet of a given product type is running above the
    configured utilisation threshold -- the signal that they are at capacity.
    """
    created = 0
    clients = db.execute(select(Client).where(Client.active.is_(True))).scalars().all()

    for client in clients:
        rows = db.execute(
            select(
                Asset.product_type,
                func.count(Asset.id),
                func.sum(Asset.runtime_minutes_today),
                func.sum(Asset.idle_minutes_today),
            )
            .where(Asset.current_client_id == client.id)
            .group_by(Asset.product_type)
        ).all()

        for product_type, count, runtime, idle in rows:
            denom = (runtime or 0) + (idle or 0)
            if denom == 0 or count == 0:
                continue
            utilization = (runtime or 0) / denom
            if utilization < settings.CLIENT_HIGH_UTILIZATION_THRESHOLD:
                continue

            readable_type = product_type.replace("_", " ").title()
            # Enough extra capacity to bring utilisation back under the threshold,
            # rounded up, floored at 1.
            suggested = max(1, int(round(count * (utilization - settings.CLIENT_HIGH_UTILIZATION_THRESHOLD) / 0.15)))

            _upsert(
                db,
                dedupe_key=f"client:{client.id}:more:{product_type}",
                client_id=client.id,
                site_id=None,
                asset_id=None,
                rec_type=RecommendationType.REQUEST_MORE_ASSETS,
                title=f"Consider requesting {suggested} more {readable_type}(s)",
                description=(
                    f"Your {readable_type} fleet has averaged {utilization * 100:.0f}% utilization "
                    f"across {count} machine(s), above the {settings.CLIENT_HIGH_UTILIZATION_THRESHOLD * 100:.0f}% "
                    "capacity threshold. Sustained utilization at this level usually means work is being "
                    "queued behind equipment availability."
                ),
                rationale=[
                    f"Current utilization: {utilization * 100:.0f}%",
                    f"Capacity threshold: {settings.CLIENT_HIGH_UTILIZATION_THRESHOLD * 100:.0f}%",
                    f"Machines of this type in your fleet: {count}",
                ],
                product_type=product_type,
                quantity=suggested,
            )
            created += 1

    return created


def generate_underutilization_recommendations(db: Session) -> int:
    """Flag rented machines that are not earning their keep."""
    created = 0

    assets = db.execute(
        select(Asset).where(
            Asset.current_client_id.is_not(None),
            Asset.status.in_((AssetStatus.IDLE.value, AssetStatus.RENTED.value)),
        )
    ).scalars().all()

    for asset in assets:
        engaged = asset.runtime_minutes_today + asset.idle_minutes_today
        if engaged < settings.UNDERUTILIZED_WINDOW_MINUTES:
            continue
        if asset.utilization > 0.10:
            continue

        readable_type = asset.product_type.replace("_", " ").title()
        _upsert(
            db,
            dedupe_key=f"company:underutilized:{asset.id}",
            client_id=asset.current_client_id,
            site_id=asset.current_site_id,
            asset_id=asset.id,
            rec_type=RecommendationType.RETURN_UNDERUTILIZED,
            title=f"{asset.asset_code} is under-utilised -- consider reassignment or return",
            description=(
                f"{asset.asset_code} ({readable_type}) has recorded "
                f"{asset.runtime_minutes_today / 60:.1f}h runtime against "
                f"{asset.idle_minutes_today / 60:.1f}h idle today ({asset.utilization * 100:.0f}% utilization) "
                "while under active rental. The client is paying for capacity they are not using."
            ),
            rationale=[
                f"Runtime today: {asset.runtime_minutes_today / 60:.1f}h",
                f"Idle today: {asset.idle_minutes_today / 60:.1f}h",
                f"Utilization: {asset.utilization * 100:.0f}%",
            ],
            product_type=asset.product_type,
            quantity=1,
        )
        created += 1

    return created


def regenerate_all(db: Session, commit: bool = True) -> dict:
    """Run every recommendation rule. Called after forecasting and by the seed."""
    company = generate_company_recommendations(db)
    client = generate_client_recommendations(db)
    under = generate_underutilization_recommendations(db)
    if commit:
        db.commit()
    return {
        "preposition": company,
        "client_requests": client,
        "underutilized": under,
        "total": company + client + under,
    }
