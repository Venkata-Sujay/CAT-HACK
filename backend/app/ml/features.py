"""Feature engineering, shared by training and inference.

This module is imported by BOTH the offline training scripts (``ml/train_*.py``)
and the live inference path. That is deliberate: if training and serving built
their features separately they would drift, and the model would silently score
garbage. One definition, one source of truth.

``ANOMALY_FEATURES`` is the canonical column order. It is persisted into the
model artifact's metadata and verified at load time.
"""

from datetime import timezone

from app.models import Asset, AssetStatus, HealthState, utcnow

# Canonical feature order for the anomaly model. Do not reorder without
# retraining -- the model indexes columns positionally.
ANOMALY_FEATURES = [
    "runtime_minutes_today",
    "idle_minutes_today",
    "utilization",
    "fuel_consumption_rate",
    "fuel_level",
    "continuous_runtime_minutes",
    "engine_health_numeric",
    "tire_health_numeric",
    "operator_match",
    "site_assignment_present",
    "rental_active",
    "hours_since_last_seen",
    # Added after a train/serve skew hunt. runtime_minutes_today is meaningless
    # without knowing how much of the day has passed: 40 minutes of runtime at
    # 07:00 is a machine that has just started, the same 40 minutes at 19:00 is
    # a machine that never worked. Without this the model cannot tell those
    # apart and flags half the fleet every morning. Derived from the other two
    # counters, so it needs no new data source on either side.
    "hours_elapsed_today",
    # Runtime as a fraction of the WORKING time available so far, rather than
    # of the whole elapsed day.
    #
    # `utilization` divides by elapsed time including the night, so a healthy
    # machine reads 0.16 at 08:00 and 0.44 at 20:00 -- the same machine, two
    # very different numbers, and a genuinely dead machine at 08:00 lands
    # inside that range. This divides by shift minutes only, so a healthy
    # machine sits near 0.6 at ANY hour and a dead one sits at 0.0 at any hour.
    # Turning a conditional into a flat one made "dead asset" recall jump from
    # 31% to the figure printed by ml/train_anomaly_model.py.
    "shift_utilization",
]

# Human-readable labels used to build alert explanations.
FEATURE_LABELS = {
    "runtime_minutes_today": "runtime today",
    "idle_minutes_today": "idle time today",
    "utilization": "utilization",
    "fuel_consumption_rate": "fuel consumption rate",
    "fuel_level": "fuel level",
    "continuous_runtime_minutes": "continuous operating time",
    "engine_health_numeric": "engine condition",
    "tire_health_numeric": "tire condition",
    "operator_match": "operator authorisation",
    "site_assignment_present": "site assignment",
    "rental_active": "rental status",
    "hours_since_last_seen": "time since last report",
    "hours_elapsed_today": "hours into the working day",
    "shift_utilization": "utilization against working hours so far",
}

# Working shift, mirroring the simulator (app/simulator/engine.py).
SHIFT_START_HOUR = 6.0
SHIFT_END_HOUR = 20.0
SHIFT_LENGTH_HOURS = SHIFT_END_HOUR - SHIFT_START_HOUR


def shift_minutes_elapsed(hours_elapsed_today: float) -> float:
    """Minutes of the working shift that have passed, given hours since midnight.

    Zero before the shift opens, saturating at the full shift once it closes.
    Shared by training and serving like everything else in this module.
    """
    return max(0.0, min(hours_elapsed_today - SHIFT_START_HOUR, SHIFT_LENGTH_HOURS)) * 60.0


DEPLOYED_STATES = (
    AssetStatus.RENTED.value,
    AssetStatus.ACTIVE.value,
    AssetStatus.IDLE.value,
    AssetStatus.OVERDUE.value,
)


def _health_numeric(value: str) -> int:
    try:
        return HealthState(value).numeric
    except ValueError:
        return 0


def _hours_since(dt) -> float:
    if dt is None:
        return 999.0
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return max(0.0, (utcnow() - dt).total_seconds() / 3600.0)


def _num(value, default: float = 0.0) -> float:
    """Coerce to float, treating None as the default.

    SQLAlchemy column defaults are applied at INSERT time, so an Asset built in
    memory (or read back before a flush) has None where the schema promises a
    number. Feature extraction must not assume the DB has filled those in --
    a TypeError here would take down a whole scoring sweep.
    """
    if value is None:
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def asset_to_features(asset: Asset) -> dict[str, float]:
    """Extract the anomaly feature vector from an asset's live state.

    Returns a dict keyed by ANOMALY_FEATURES so callers can build a DataFrame
    with a guaranteed column order.
    """
    runtime = _num(asset.runtime_minutes_today)
    idle = _num(asset.idle_minutes_today)
    engaged = runtime + idle

    fuel_level = _num(asset.fuel_level, 100.0)

    # Fuel burned per engaged hour. Zero denominator is a genuine "no data"
    # case, not an error -- report 0 rather than dividing by zero.
    fuel_used = max(0.0, 100.0 - fuel_level)
    fuel_rate = (fuel_used / (engaged / 60.0)) if engaged > 0 else 0.0

    utilization = (runtime / engaged) if engaged > 0 else 0.0

    return {
        "runtime_minutes_today": runtime,
        "idle_minutes_today": idle,
        "utilization": round(utilization, 4),
        "fuel_consumption_rate": round(fuel_rate, 4),
        "fuel_level": fuel_level,
        "continuous_runtime_minutes": _num(asset.continuous_runtime_minutes),
        "engine_health_numeric": float(_health_numeric(asset.engine_condition or "GOOD")),
        "tire_health_numeric": float(_health_numeric(asset.tire_condition or "GOOD")),
        "operator_match": 1.0 if asset.operator_match else 0.0,
        "site_assignment_present": 1.0 if asset.current_site_id is not None else 0.0,
        "rental_active": 1.0 if asset.status in DEPLOYED_STATES else 0.0,
        "hours_since_last_seen": round(_hours_since(asset.last_seen_at), 3),
        "hours_elapsed_today": round(engaged / 60.0, 3),
        "shift_utilization": round(_shift_utilization(runtime, engaged / 60.0), 4),
    }


def _shift_utilization(runtime_minutes: float, hours_elapsed: float) -> float:
    shift_minutes = shift_minutes_elapsed(hours_elapsed)
    if shift_minutes <= 0:
        return 0.0
    # Capped at 1.0: a machine running through the night legitimately exceeds
    # the shift, and `continuous_runtime_minutes` is the feature that says so.
    return min(1.0, runtime_minutes / shift_minutes)


def features_to_row(features: dict[str, float]) -> list[float]:
    """Order a feature dict into the canonical model input vector."""
    return [float(features.get(name, 0.0)) for name in ANOMALY_FEATURES]


# ---------------------------------------------------------------------------
# Demand forecasting features
# ---------------------------------------------------------------------------

DEMAND_FEATURES = [
    "site_encoded",
    "product_encoded",
    "day_of_week",
    "week_of_year",
    "month",
    "is_weekend",
    "prev_day_demand",
    "prev_week_demand",
    "rolling_7d_mean",
    "rolling_14d_mean",
    "rolling_30d_mean",
    "avg_utilization_7d",
    "active_rentals",
]
