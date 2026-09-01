"""Evaluate both trained models and write a consolidated report.

Run:  python ml/evaluate_models.py

Writes ml/artifacts/evaluation_report.json and prints a summary.

This script exists so model quality is a reportable artifact rather than a claim.
It states plainly when a model fails to beat its baseline, and it repeats the
synthetic-data caveat in the report itself so the number is never quoted without
its context.
"""

import sys
from pathlib import Path as _Path

# Must run before joblib/scikit-learn import -- see app/core/runtime.py.
sys.path.insert(0, str(_Path(__file__).resolve().parent.parent / "backend"))
from app.core.runtime import apply_all as _apply_runtime_fixes  # noqa: E402

_apply_runtime_fixes()

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.metrics import mean_absolute_error, mean_squared_error

from app.ml.features import ANOMALY_FEATURES, DEMAND_FEATURES  # noqa: E402

DATA_DIR = Path(__file__).resolve().parent / "data"
ARTIFACT_DIR = Path(__file__).resolve().parent / "artifacts"


def evaluate_anomaly() -> dict:
    model_path = ARTIFACT_DIR / "anomaly_model.joblib"
    data_path = DATA_DIR / "anomaly_training.csv"

    if not model_path.exists():
        return {"status": "missing", "hint": "Run: python ml/train_anomaly_model.py"}
    if not data_path.exists():
        return {"status": "no_data", "hint": "Run: python ml/generate_training_data.py"}

    bundle = joblib.load(model_path)
    model, scaler = bundle["model"], bundle["scaler"]
    threshold = bundle["metadata"].get("alert_threshold", 0.0)

    df = pd.read_csv(data_path)
    X = scaler.transform(df[ANOMALY_FEATURES].to_numpy(dtype=float))
    scores = model.decision_function(X)
    predicted = (scores < threshold).astype(int)
    actual = df["is_anomaly"].to_numpy()

    tp = int(((predicted == 1) & (actual == 1)).sum())
    fp = int(((predicted == 1) & (actual == 0)).sum())
    fn = int(((predicted == 0) & (actual == 1)).sum())
    tn = int(((predicted == 0) & (actual == 0)).sum())

    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0

    return {
        "status": "ok",
        "model_version": bundle["metadata"]["model_version"],
        "model_type": bundle["metadata"]["model_type"],
        "trained_at": bundle["metadata"]["trained_at"],
        "training_rows": bundle["metadata"]["training_rows"],
        "alert_threshold": threshold,
        "confusion_matrix": {"tp": tp, "fp": fp, "fn": fn, "tn": tn},
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1": round(f1, 4),
        "note": (
            "Labels were never used for training -- IsolationForest is unsupervised. "
            "They exist only to verify the model separates the injected anomalies."
        ),
    }


def evaluate_demand() -> dict:
    model_path = ARTIFACT_DIR / "demand_model.joblib"
    data_path = DATA_DIR / "demand_training.csv"

    if not model_path.exists():
        return {"status": "missing", "hint": "Run: python ml/train_demand_model.py"}
    if not data_path.exists():
        return {"status": "no_data", "hint": "Run: python ml/generate_training_data.py"}

    bundle = joblib.load(model_path)
    model = bundle["model"]
    encoders = bundle["encoders"]
    metadata = bundle["metadata"]

    df = pd.read_csv(data_path)
    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values("date").reset_index(drop=True)
    df["site_encoded"] = df["site"].map(encoders["site"])
    df["product_encoded"] = df["product_type"].map(encoders["product_type"])

    # Same time-aware split as training -- evaluating on training rows would be
    # meaningless.
    split_date = pd.Timestamp(metadata["split_date"])
    test = df[df["date"] >= split_date]

    y_true = test["demand"].to_numpy(dtype=float)
    y_model = np.clip(model.predict(test[DEMAND_FEATURES].to_numpy(dtype=float)), 0, None)
    y_baseline = test["rolling_7d_mean"].to_numpy(dtype=float)

    model_mae = float(mean_absolute_error(y_true, y_model))
    model_rmse = float(np.sqrt(mean_squared_error(y_true, y_model)))
    base_mae = float(mean_absolute_error(y_true, y_baseline))
    base_rmse = float(np.sqrt(mean_squared_error(y_true, y_baseline)))
    improvement = (base_mae - model_mae) / base_mae * 100 if base_mae else 0.0

    return {
        "status": "ok",
        "model_version": metadata["model_version"],
        "model_type": metadata["model_type"],
        "trained_at": metadata["trained_at"],
        "split": metadata["split"],
        "split_date": metadata["split_date"],
        "test_rows": int(len(test)),
        "model": {"mae": round(model_mae, 4), "rmse": round(model_rmse, 4)},
        "baseline_rolling_7d": {"mae": round(base_mae, 4), "rmse": round(base_rmse, 4)},
        "improvement_over_baseline_pct": round(improvement, 2),
        "beats_baseline": bool(improvement > 0),
        "top_features": dict(list(metadata.get("feature_importance", {}).items())[:5]),
    }


def main() -> int:
    print("=" * 62)
    print("  MODEL EVALUATION REPORT")
    print("=" * 62)

    anomaly = evaluate_anomaly()
    demand = evaluate_demand()

    print("\n[1] ANOMALY DETECTION")
    if anomaly["status"] != "ok":
        print(f"    {anomaly['status'].upper()} -- {anomaly.get('hint', '')}")
    else:
        cm = anomaly["confusion_matrix"]
        print(f"    model      : {anomaly['model_type']} ({anomaly['model_version']})")
        print(f"    threshold  : {anomaly['alert_threshold']:+.3f}")
        print(f"    precision  : {anomaly['precision']:.1%}")
        print(f"    recall     : {anomaly['recall']:.1%}")
        print(f"    F1         : {anomaly['f1']:.3f}")
        print(f"    confusion  : TP={cm['tp']}  FP={cm['fp']}  FN={cm['fn']}  TN={cm['tn']}")

    print("\n[2] DEMAND FORECAST")
    if demand["status"] != "ok":
        print(f"    {demand['status'].upper()} -- {demand.get('hint', '')}")
    else:
        print(f"    model      : {demand['model_type']} ({demand['model_version']})")
        print(f"    split      : {demand['split']} at {demand['split_date'][:10]}")
        print(f"    model      : MAE {demand['model']['mae']:.4f}   RMSE {demand['model']['rmse']:.4f}")
        print(f"    baseline   : MAE {demand['baseline_rolling_7d']['mae']:.4f}   "
              f"RMSE {demand['baseline_rolling_7d']['rmse']:.4f}")
        verdict = "BEATS" if demand["beats_baseline"] else "LOSES TO"
        print(f"    verdict    : model {verdict} baseline by {abs(demand['improvement_over_baseline_pct']):.1f}% MAE")

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "anomaly_detection": anomaly,
        "demand_forecast": demand,
        "IMPORTANT": (
            "All metrics are computed on SYNTHETIC data generated by "
            "ml/generate_training_data.py. They measure how well each model fits "
            "our own generator, NOT real-world performance. Do not present these "
            "numbers as evidence of production accuracy."
        ),
    }

    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = ARTIFACT_DIR / "evaluation_report.json"
    out_path.write_text(json.dumps(report, indent=2), encoding="utf-8")

    print("\n" + "-" * 62)
    print("  NOTE: metrics are against SYNTHETIC data. They measure fit to our")
    print("  own generator, not real-world accuracy. State this when presenting.")
    print("-" * 62)
    print(f"\nReport written to {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
