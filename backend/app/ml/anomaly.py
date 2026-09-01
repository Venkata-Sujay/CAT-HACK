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


# Feature pairs that describe the SAME finding in two ways. When both deviate,
# only the stronger one is shown -- three reasons that are really one reason
# read as padding, and padding is how an explanation loses a reader's trust.
REDUNDANT_WITH = {
    "utilization": "shift_utilization",
    "shift_utilization": "utilization",
    "runtime_minutes_today": "shift_utilization",
    "idle_minutes_today": "utilization",
}


def explain(features: dict[str, float], stats: dict, top_n: int = 3) -> list[str]:
    """Top-N feature deviations, rendered as natural language."""
    medians = stats.get("median", {})
    iqrs = stats.get("iqr", {})

    scored: list[tuple[float, str, str]] = []
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
                scored.append((deviation, sentence, name))

    scored.sort(key=lambda item: item[0], reverse=True)

    chosen: list[str] = []
    used: set[str] = set()
    for _deviation, sentence, name in scored:
        if REDUNDANT_WITH.get(name) in used:
            continue
        chosen.append(sentence)
        used.add(name)
        if len(chosen) == top_n:
            break
    return chosen


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


# Hours into the machine's day before its behaviour is judged at all. The
# shift starts at 06:00, so this is two hours into actual work.
#
# Zero runtime at 03:00 is a machine that has not started. Zero runtime at
# 18:00 is a machine nobody is using. Only the second is an anomaly, and no
# amount of density estimation separates them from a feature vector that spans
# the whole day -- measured "dead asset" recall across hours 0-24 was 32%.
#
# So the model is only ASKED the question once it is answerable. The training
# generator applies the identical floor (MIN_SCORING_HOURS in
# ml/generate_training_data.py); changing one without the other reintroduces
# exactly the train/serve skew this was added to remove.
MIN_SCORING_HOURS = 8.0


def score_asset(asset: Asset) -> dict | None:
    """Score one asset.

    Returns None when no model is loaded, or when too little of the machine's
    day has elapsed for its duty cycle to mean anything yet.
    """
    if not model_registry.anomaly_ready:
        return None

    bundle = model_registry.anomaly_bundle
    model = bundle["model"]
    scaler = bundle.get("scaler")
    stats = bundle.get("stats", {})

    features = asset_to_features(asset)

    if features.get("hours_elapsed_today", 0.0) < MIN_SCORING_HOURS:
        return None

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


# Fraction of the scored fleet above which a sweep is treated as a MODEL
# problem rather than a fleet problem.
#
# The model is calibrated to a 3% false-positive rate. If a single sweep says a
# third of every machine on hire is behaving abnormally, the likelier
# explanation by far is that the fleet has moved somewhere the model was not
# trained -- a shift boundary, a counter rollover, a simulator parameter
# change -- not that thirty machines broke in the same ten seconds.
#
# So the sweep is discarded and the reason is logged loudly. The rule engine is
# unaffected and keeps firing throughout, which is the point of splitting them:
# the deterministic layer never goes quiet just because the probabilistic one
# lost its footing.
ALERT_STORM_FRACTION = 0.40


def evaluate_fleet(db: Session, commit: bool = True) -> dict:
    """Score every deployed asset and raise/clear ML_ANOMALY alerts.

    Rules own the deterministic conditions (unauthorized operator, low fuel,
    overdue...). This pass exists to catch unusual COMBINATIONS that no single
    threshold would flag.

    Runs in two phases so the storm guard above can see the whole picture
    before anything is written.
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

    # ---- phase 1: score everything, write nothing ------------------------
    scored: list[tuple[Asset, dict]] = []
    for asset in assets:
        try:
            result = score_asset(asset)
        except Exception:  # noqa: BLE001 - never let scoring break the sweep
            logger.exception("Anomaly scoring failed for %s", asset.asset_code)
            continue
        if result is not None:
            scored.append((asset, result))

    flagged = sum(1 for _, r in scored if r["is_anomaly"])
    if scored and flagged / len(scored) > ALERT_STORM_FRACTION:
        logger.warning(
            "ML sweep SUPPRESSED: %d of %d scored assets flagged (%.0f%%, limit %.0f%%). "
            "A fleet-wide flag rate this far above the model's 3%% calibrated "
            "false-positive rate indicates distribution drift, not %d simultaneous "
            "faults. Rule-based alerting is unaffected.",
            flagged,
            len(scored),
            100 * flagged / len(scored),
            100 * ALERT_STORM_FRACTION,
            flagged,
        )
        return {
            "scored": len(scored),
            "anomalies": 0,
            "suppressed": True,
            "would_have_flagged": flagged,
            "reason": "flag rate above storm threshold -- suspected distribution drift",
        }

    # ---- phase 2: raise and clear ----------------------------------------
    anomalies = 0
    for asset, result in scored:
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
