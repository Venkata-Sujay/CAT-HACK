"""Anomaly inference with explanations.

The model is an IsolationForest, but its raw score is useless to an operator.
"Isolation Forest score = -0.78" tells nobody what to do. So every anomalous
prediction is passed through an explanation step:

  1. Compare each feature against the TRAINING distribution's median and IQR
     (both persisted in the artifact at training time).
  2. Compute a robust z-score:  |value - median| / IQR
  3. Take the top contributors and render them as natural language.

Robust statistics (median/IQR) rather than mean/std because telemetry features
are heavily skewed -- a handful of machines running 20-hour days would drag a
mean far enough to make ordinary assets look anomalous.

The result is an alert that says "Runtime is 87% below this asset's normal
range", which an operator can act on, with the score kept as supporting detail.
"""

import logging

from sqlalchemy.orm import Session

from app.config import settings
from app.ml.features import ANOMALY_FEATURES, FEATURE_LABELS, asset_to_features, features_to_row
from app.ml.registry import model_registry
from app.models import (
    AlertSeverity,
    AlertSource,
    AlertType,
    Asset,
    AssetStatus,
)
from app.services.alert_service import auto_resolve, raise_alert

logger = logging.getLogger("rental.ml.anomaly")

# Features where a HIGH value is the problem; everything else reads as "low".
HIGH_IS_BAD = {
    "idle_minutes_today",
    "continuous_runtime_minutes",
    "engine_health_numeric",
    "tire_health_numeric",
    "hours_since_last_seen",
    "fuel_consumption_rate",
}


def _describe_deviation(name: str, value: float, median: float, iqr: float) -> str | None:
    """Render one feature deviation as a human sentence."""
    label = FEATURE_LABELS.get(name, name.replace("_", " "))

    # Binary flags read as states, not magnitudes.
    if name == "operator_match":
        return "Machine is being operated by someone other than the assigned operator" if value < 0.5 else None
    if name == "site_assignment_present":
        return "No site is assigned to this machine" if value < 0.5 else None
    if name in ("engine_health_numeric", "tire_health_numeric"):
        if value >= 2:
            return f"{label.capitalize()} is CRITICAL"
        if value >= 1:
            return f"{label.capitalize()} has degraded to WARNING"
        return None

    if iqr <= 0:
        return None

    delta = value - median
    if median > 0:
        pct = abs(delta) / median * 100
        direction = "above" if delta > 0 else "below"
        return f"{label.capitalize()} is {pct:.0f}% {direction} the normal range for this fleet"

    if delta > 0:
        return f"{label.capitalize()} is unusually high ({value:.0f} vs typical {median:.0f})"
    return f"{label.capitalize()} is unusually low ({value:.0f} vs typical {median:.0f})"


def explain(features: dict[str, float], stats: dict, top_n: int = 3) -> list[str]:
    """Top-N feature deviations, rendered as natural language."""
    medians = stats.get("median", {})
    iqrs = stats.get("iqr", {})

    scored: list[tuple[float, str]] = []
    for name in ANOMALY_FEATURES:
        value = features.get(name, 0.0)
        median = medians.get(name, 0.0)
        iqr = iqrs.get(name, 0.0)

        if name in ("operator_match", "site_assignment_present"):
            # Binary problems are always maximally interesting when tripped.
            deviation = 10.0 if value < 0.5 else 0.0
        elif name in ("engine_health_numeric", "tire_health_numeric"):
            deviation = value * 4.0
        elif iqr > 0:
            deviation = abs(value - median) / iqr
        else:
            deviation = 0.0

        if deviation > 1.0:
            sentence = _describe_deviation(name, value, median, iqr)
            if sentence:
                scored.append((deviation, sentence))

    scored.sort(key=lambda pair: pair[0], reverse=True)
    return [sentence for _, sentence in scored[:top_n]]


def classify(features: dict[str, float], reasons: list[str]) -> tuple[AlertType, str]:
    """Give the anomaly a meaningful label instead of a generic 'anomaly'.

    Returns (alert_type, human_subtype). The subtype drives the alert title so
    a user sees "Underutilization pattern detected", not "ML anomaly #4".
    """
    utilization = features.get("utilization", 0.0)
    idle = features.get("idle_minutes_today", 0.0)
    runtime = features.get("runtime_minutes_today", 0.0)

    if runtime + idle > 120 and utilization < 0.15:
        return AlertType.ML_ANOMALY, "UNDERUTILIZATION"
    if features.get("operator_match", 1.0) < 0.5:
        return AlertType.ML_ANOMALY, "OPERATOR_IRREGULARITY"
    if features.get("continuous_runtime_minutes", 0.0) > 600:
        return AlertType.ML_ANOMALY, "SUSTAINED_OVERUSE"
    if features.get("fuel_consumption_rate", 0.0) > 0:
        # Abnormal burn relative to work done can indicate a mechanical issue.
        if utilization > 0 and features.get("fuel_consumption_rate", 0.0) > 15:
            return AlertType.ML_ANOMALY, "ABNORMAL_FUEL_CONSUMPTION"
    return AlertType.ML_ANOMALY, "UNUSUAL_USAGE_PATTERN"


def _alert_threshold() -> float:
    """The score below which an asset is treated as anomalous.

    Read from the model artifact, which computed it from the actual score
    distribution at training time. IsolationForest offsets decision_function by
    its ``contamination`` parameter, so the correct boundary depends on how the
    model was fitted -- a hardcoded constant drifts out of date the moment
    anything is retuned. ``settings.ANOMALY_ALERT_THRESHOLD`` is only a fallback
    for an artifact predating this field.
    """
    bundle = model_registry.anomaly_bundle or {}
    metadata = bundle.get("metadata", {})
    value = metadata.get("alert_threshold")
    return float(value) if value is not None else settings.ANOMALY_ALERT_THRESHOLD


def score_asset(asset: Asset) -> dict | None:
    """Score one asset. Returns None when no model is loaded."""
    if not model_registry.anomaly_ready:
        return None

    bundle = model_registry.anomaly_bundle
    model = bundle["model"]
    scaler = bundle.get("scaler")
    stats = bundle.get("stats", {})

    features = asset_to_features(asset)
    row = [features_to_row(features)]

    if scaler is not None:
        row = scaler.transform(row)

    # decision_function: negative = more anomalous.
    score = float(model.decision_function(row)[0])
    is_anomaly = score < _alert_threshold()

    return {
        "score": round(score, 4),
        "is_anomaly": is_anomaly,
        "features": features,
        "reasons": explain(features, stats) if is_anomaly else [],
    }


def _severity_for(score: float) -> AlertSeverity:
    """Map a model score onto a severity band.

    Bands come from the training-time anomaly score quantiles stored in the
    artifact, so HIGH means "in the worst quartile of what this model considers
    anomalous" rather than an arbitrary cutoff.
    """
    bundle = model_registry.anomaly_bundle or {}
    bands = (bundle.get("metadata", {}) or {}).get("severity_bands") or {}
    high = bands.get("high", -0.06)
    medium = bands.get("medium", -0.02)

    if score < high:
        return AlertSeverity.HIGH
    if score < medium:
        return AlertSeverity.MEDIUM
    return AlertSeverity.LOW


def evaluate_fleet(db: Session, commit: bool = True) -> dict:
    """Score every deployed asset and raise/clear ML_ANOMALY alerts.

    Rules own the deterministic conditions (unauthorized operator, low fuel,
    overdue...). This pass exists to catch unusual COMBINATIONS that no single
    threshold would flag.
    """
    if not model_registry.anomaly_ready:
        return {"scored": 0, "anomalies": 0, "skipped": "anomaly model not loaded"}

    from sqlalchemy import select

    deployed = (
        AssetStatus.RENTED.value,
        AssetStatus.ACTIVE.value,
        AssetStatus.IDLE.value,
        AssetStatus.OVERDUE.value,
    )
    assets = db.execute(select(Asset).where(Asset.status.in_(deployed))).scalars().all()

    anomalies = 0
    for asset in assets:
        try:
            result = score_asset(asset)
        except Exception:  # noqa: BLE001 - never let scoring break the sweep
            logger.exception("Anomaly scoring failed for %s", asset.asset_code)
            continue
        if result is None:
            continue

        if not result["is_anomaly"]:
            auto_resolve(
                db,
                asset_id=asset.id,
                alert_type=AlertType.ML_ANOMALY,
                reason="Usage pattern has returned to normal",
            )
            continue

        reasons = result["reasons"]
        if not reasons:
            # A score with no explainable driver is not worth showing a user.
            continue

        _, subtype = classify(result["features"], reasons)
        readable = subtype.replace("_", " ").lower()

        raise_alert(
            db,
            asset_id=asset.id,
            client_id=asset.current_client_id,
            site_id=asset.current_site_id,
            alert_type=AlertType.ML_ANOMALY,
            severity=_severity_for(result["score"]),
            title=f"{asset.asset_code}: {readable} detected",
            description=(
                f"The anomaly model flagged {asset.asset_code} as behaving unusually "
                f"compared with normal operating patterns for this fleet. "
                f"Detected pattern: {readable}."
            ),
            reasons=reasons,
            recommended_action=_action_for(subtype),
            source=AlertSource.ML,
            score=result["score"],
        )
        anomalies += 1

    if commit:
        db.commit()

    return {"scored": len(assets), "anomalies": anomalies}


def _action_for(subtype: str) -> str:
    return {
        "UNDERUTILIZATION": "Investigate why the machine is not producing, reassign it to an active task, or return it.",
        "OPERATOR_IRREGULARITY": "Verify who is operating this machine and correct the operator assignment.",
        "SUSTAINED_OVERUSE": "Review the operating schedule and consider a rest or inspection period.",
        "ABNORMAL_FUEL_CONSUMPTION": "Inspect for a mechanical fault or possible fuel loss.",
        "UNUSUAL_USAGE_PATTERN": "Review this machine's recent telemetry and confirm operations are as expected.",
    }.get(subtype, "Review this machine's recent activity.")
