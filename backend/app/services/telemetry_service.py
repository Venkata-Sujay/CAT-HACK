"""Telemetry application -- the single write path for asset live state.

Both the simulator and the HTTP ingest endpoint call ``apply_telemetry``. Having
one path means the denormalised state on ``Asset`` and the ``telemetry_logs``
time series can never disagree.

Two invariants enforced here:

1. **Health is monotonic.** ``tire_health``/``engine_health`` may only degrade.
   An inbound GOOD for an asset already at WARNING is ignored. Recovery happens
   exclusively through maintenance or check-in inspection. Without this the
   simulator would flicker conditions and every health alert would be noise.

2. **Continuous runtime resets on stop.** ``continuous_runtime_minutes`` tracks
   uninterrupted operation for the CONTINUOUS_USAGE rule and must reset the
   moment a machine goes idle, not at the day boundary.
"""

import logging

from sqlalchemy.orm import Session

from app.models import Asset, AssetStatus, HealthState, TelemetryLog, utcnow

logger = logging.getLogger("rental.telemetry")


def _monotonic_health(current: str, incoming: str) -> str:
    """Return the worse of the two states. Health never improves via telemetry."""
    try:
        current_rank = HealthState(current).numeric
        incoming_rank = HealthState(incoming).numeric
    except ValueError:
        return current
    return incoming if incoming_rank > current_rank else current


def apply_telemetry(
    db: Session,
    *,
    asset: Asset,
    is_running: bool,
    runtime_delta: int,
    idle_delta: int,
    fuel_level: float,
    tire_health: str,
    engine_health: str,
    engine_temp_c: float = 45.0,
    latitude: float | None = None,
    longitude: float | None = None,
    operator_id: int | None = None,
    run_rules: bool = True,
    flush: bool = True,
) -> TelemetryLog:
    """Apply one telemetry tick: update live state, append to the series, run rules."""
    now = utcnow()

    # --- counters ---
    asset.runtime_minutes += runtime_delta
    asset.idle_minutes += idle_delta
    asset.runtime_minutes_today += runtime_delta
    asset.idle_minutes_today += idle_delta

    if is_running:
        asset.continuous_runtime_minutes += runtime_delta
    else:
        asset.continuous_runtime_minutes = 0

    # --- live state ---
    asset.is_running = is_running
    asset.fuel_level = max(0.0, min(100.0, fuel_level))
    asset.tire_condition = _monotonic_health(asset.tire_condition, tire_health)
    asset.engine_condition = _monotonic_health(asset.engine_condition, engine_health)
    asset.engine_temp_c = engine_temp_c
    asset.current_operator_id = operator_id
    asset.last_seen_at = now

    if latitude is not None:
        asset.latitude = latitude
    if longitude is not None:
        asset.longitude = longitude

    # --- derived status ---
    # Only rented machines flip between ACTIVE and IDLE. An OVERDUE asset stays
    # OVERDUE regardless of whether it happens to be running -- the deadline
    # breach is the more important fact, and the rule engine owns that state.
    if asset.status in (AssetStatus.RENTED.value, AssetStatus.ACTIVE.value, AssetStatus.IDLE.value):
        asset.status = AssetStatus.ACTIVE.value if is_running else AssetStatus.IDLE.value

    log = TelemetryLog(
        asset_id=asset.id,
        client_id=asset.current_client_id,
        timestamp=now,
        runtime_delta_minutes=runtime_delta,
        idle_delta_minutes=idle_delta,
        fuel_level=asset.fuel_level,
        tire_health=asset.tire_condition,
        engine_health=asset.engine_condition,
        engine_temp_c=engine_temp_c,
        latitude=asset.latitude,
        longitude=asset.longitude,
        site_id=asset.current_site_id,
        current_operator_id=operator_id,
        is_running=is_running,
    )
    db.add(log)

    if flush:
        db.flush()

    if run_rules:
        # Imported here rather than at module scope: rules_engine imports from
        # asset_service, which would otherwise form an import cycle at startup.
        from app.services.rules_engine import evaluate_asset

        evaluate_asset(db, asset)

    return log


def reset_daily_counters(db: Session, assets: list[Asset]) -> int:
    """Roll the per-day counters at a simulated midnight.

    Lifetime totals are untouched; only the ``*_today`` values reset, so
    utilisation means "today" rather than "since the asset was built".
    """
    for asset in assets:
        asset.runtime_minutes_today = 0
        asset.idle_minutes_today = 0
    db.flush()
    return len(assets)
