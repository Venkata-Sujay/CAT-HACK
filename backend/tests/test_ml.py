"""ML layer tests.

These assert the CONTRACT, not model accuracy -- accuracy belongs in
ml/evaluate_models.py where it can be reported honestly against a baseline.
What must hold here:

  * The system degrades gracefully when a model artifact is missing.
  * Feature extraction never divides by zero and never drifts from the
    canonical column list shared with training.
  * Anomalies are always explained in words, never as a bare score.
"""

import pytest
from sqlalchemy import select

from app.ml.features import ANOMALY_FEATURES, asset_to_features, features_to_row
from app.ml.registry import model_registry
from app.models import Asset


def test_feature_vector_matches_canonical_order(db_session):
    """Training and serving must build features identically or the model scores noise."""
    asset = db_session.execute(select(Asset)).scalars().first()
    features = asset_to_features(asset)

    assert set(features.keys()) == set(ANOMALY_FEATURES)

    row = features_to_row(features)
    assert len(row) == len(ANOMALY_FEATURES)
    assert all(isinstance(value, float) for value in row)


def test_features_handle_zero_denominator(db_session):
    """A brand-new asset has no engaged time. That must be 0.0, not a crash."""
    asset = Asset(
        asset_code="TEST-ZERO",
        product_type="EXCAVATOR",
        qr_token="QR-TEST-ZERO",
        runtime_minutes_today=0,
        idle_minutes_today=0,
        fuel_level=100.0,
        tire_condition="GOOD",
        engine_condition="GOOD",
        status="AVAILABLE",
        warehouse_status="IN_WAREHOUSE",
    )
    features = asset_to_features(asset)

    assert features["utilization"] == 0.0
    assert features["fuel_consumption_rate"] == 0.0
    assert all(value == value for value in features.values())  # no NaN


def test_missing_operator_counts_as_match(db_session):
    """A parked machine with nobody in the cab is not an authorisation violation."""
    asset = Asset(
        asset_code="TEST-NOOP",
        product_type="CRANE",
        qr_token="QR-TEST-NOOP",
        assigned_employee_id=5,
        current_operator_id=None,
        fuel_level=50.0,
        tire_condition="GOOD",
        engine_condition="GOOD",
        status="IDLE",
        warehouse_status="DEPLOYED",
    )
    assert asset.operator_match is True
    assert asset_to_features(asset)["operator_match"] == 1.0


def test_mismatched_operator_is_detected():
    asset = Asset(
        asset_code="TEST-MISMATCH",
        product_type="CRANE",
        qr_token="QR-TEST-MISMATCH",
        assigned_employee_id=5,
        current_operator_id=9,
        fuel_level=50.0,
        tire_condition="GOOD",
        engine_condition="GOOD",
        status="ACTIVE",
        warehouse_status="DEPLOYED",
    )
    assert asset.operator_match is False
    assert asset_to_features(asset)["operator_match"] == 0.0


def test_forecast_falls_back_to_baseline_without_a_model(db_session):
    """A missing demand artifact must degrade to the rolling-mean baseline,
    not blank the forecasting screen."""
    from app.ml.forecast import generate_forecasts

    saved = model_registry.demand_bundle
    model_registry.demand_bundle = None
    try:
        result = generate_forecasts(db_session, commit=False)
        assert result["source"] == "baseline-rolling-7d"
        assert result["generated"] >= 0
    finally:
        model_registry.demand_bundle = saved
    db_session.rollback()


def test_anomaly_scoring_returns_none_without_a_model(db_session):
    from app.ml.anomaly import score_asset

    saved = model_registry.anomaly_bundle
    model_registry.anomaly_bundle = None
    try:
        asset = db_session.execute(select(Asset)).scalars().first()
        assert score_asset(asset) is None
    finally:
        model_registry.anomaly_bundle = saved


def test_anomaly_sweep_reports_skip_without_a_model(db_session):
    from app.ml.anomaly import evaluate_fleet

    saved = model_registry.anomaly_bundle
    model_registry.anomaly_bundle = None
    try:
        result = evaluate_fleet(db_session, commit=False)
        assert "skipped" in result
        assert result["anomalies"] == 0
    finally:
        model_registry.anomaly_bundle = saved


def test_explanations_are_natural_language():
    """The whole point of the explainability layer: no bare scores in the output."""
    from app.ml.anomaly import explain

    stats = {
        "median": {name: 100.0 for name in ANOMALY_FEATURES},
        "iqr": {name: 20.0 for name in ANOMALY_FEATURES},
    }
    features = dict.fromkeys(ANOMALY_FEATURES, 100.0)
    features["idle_minutes_today"] = 900.0  # far above the median
    features["operator_match"] = 0.0
    features["site_assignment_present"] = 0.0

    reasons = explain(features, stats)

    assert reasons, "An anomaly must produce at least one reason"
    for reason in reasons:
        assert len(reason.split()) >= 3, f"Not a sentence: {reason!r}"
        # No raw model internals leaking into user-facing copy.
        assert "isolation" not in reason.lower()
        assert "decision_function" not in reason.lower()

    joined = " ".join(reasons).lower()
    assert "operator" in joined or "site" in joined or "idle" in joined


def test_severity_bands_come_from_the_artifact():
    """Thresholds are calibrated at training time, not hardcoded.

    A hardcoded -0.15 previously produced a 0% detection rate because no score
    ever reached it. This guards the regression.
    """
    from app.ml.anomaly import _alert_threshold

    if not model_registry.anomaly_ready:
        pytest.skip("Anomaly model not trained in this environment")

    metadata = model_registry.anomaly_bundle["metadata"]
    assert "alert_threshold" in metadata
    assert "severity_bands" in metadata
    assert _alert_threshold() == metadata["alert_threshold"]


def test_scored_anomalies_always_carry_reasons(db_session):
    """An alert a user cannot act on is noise. Enforce it at the scoring layer."""
    from app.ml.anomaly import score_asset

    # Checked at runtime, not via @skipif: the decorator is evaluated at
    # collection time, before the session fixture loads the artifacts.
    if not model_registry.anomaly_ready:
        pytest.skip("Anomaly model not trained in this environment")

    assets = db_session.execute(select(Asset).limit(30)).scalars().all()
    for asset in assets:
        result = score_asset(asset)
        if result and result["is_anomaly"]:
            assert isinstance(result["reasons"], list)
            assert isinstance(result["score"], float)
