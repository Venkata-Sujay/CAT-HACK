"""Train the IsolationForest anomaly detector.

Run:  python ml/train_anomaly_model.py

Why IsolationForest
-------------------
We have no labelled misuse data, and labelling our own synthetic anomalies then
"detecting" them would be circular reasoning dressed up as machine learning.
IsolationForest is unsupervised, strong on low-dimensional tabular data, trains
in seconds, and produces a tiny artifact. Deep learning on 12 tabular features
would be unjustifiable.

Trained on MOSTLY-NORMAL data
-----------------------------
IsolationForest characterises normality and flags departures from it. Feeding it
a heavily contaminated set teaches it that anomalies are normal. So the injected
anomalies are dropped before fitting, and ``contamination`` is set to the small
residual rate we expect in genuinely unlabelled production data.

Explainability statistics
-------------------------
The artifact stores each feature's MEDIAN and IQR from the training set. At
inference those turn a raw score into sentences like "Runtime is 87% below the
normal range" -- see app/ml/anomaly.py. Median/IQR rather than mean/std because
telemetry is skewed: a few 20-hour days would drag a mean far enough to make
ordinary assets look anomalous.
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
from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import StandardScaler

from app.ml.features import ANOMALY_FEATURES  # noqa: E402

DATA_DIR = Path(__file__).resolve().parent / "data"
ARTIFACT_DIR = Path(__file__).resolve().parent / "artifacts"
MODEL_VERSION = "anomaly-iforest-v1"
SEED = 42

# Residual contamination expected in unlabelled production data. Deliberately
# lower than the 5% we injected: the model is fit on the clean subset.
CONTAMINATION = 0.03


def main() -> int:
    data_path = DATA_DIR / "anomaly_training.csv"
    if not data_path.exists():
        print(f"ERROR: {data_path} not found.\n  Run: python ml/generate_training_data.py")
        return 1

    df = pd.read_csv(data_path)
    print(f"Loaded {len(df):,} rows from {data_path.name}")

    # Fit on normal behaviour only.
    normal = df[df["is_anomaly"] == 0].copy()
    print(f"  training on {len(normal):,} normal rows ({len(df) - len(normal):,} anomalies withheld)")

    X = normal[ANOMALY_FEATURES].to_numpy(dtype=float)

    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)

    model = IsolationForest(
        n_estimators=250,
        contamination=CONTAMINATION,
        max_samples="auto",
        random_state=SEED,
        # n_jobs=1 deliberately: joblib's loky backend cannot spawn workers under
        # Windows Store Python and dumps a CreateProcess traceback on every
        # predict() call. n_jobs is baked into the pickled model, so leaving it
        # at -1 would make the running API print that traceback too.
        n_jobs=1,
    )
    model.fit(X_scaled)
    print(f"  fitted IsolationForest(n_estimators=250, contamination={CONTAMINATION})")

    # ---- explainability statistics (robust: median + IQR) ----
    stats = {"median": {}, "iqr": {}, "p05": {}, "p95": {}}
    for name in ANOMALY_FEATURES:
        col = normal[name].to_numpy(dtype=float)
        q1, q3 = np.percentile(col, [25, 75])
        stats["median"][name] = float(np.median(col))
        stats["iqr"][name] = float(q3 - q1)
        stats["p05"][name] = float(np.percentile(col, 5))
        stats["p95"][name] = float(np.percentile(col, 95))

    # ---- calibrate the alert threshold from the actual score distribution ----
    #
    # IsolationForest.decision_function is offset by `contamination`, so the
    # natural boundary sits at 0.0 -- NOT at some hand-picked negative number.
    # Hardcoding a threshold silently breaks whenever contamination, features or
    # data change: an earlier -0.15 guess here produced a 0% detection rate
    # because no score ever reached it. Compute it, store it, let inference read
    # it back from the artifact.
    normal_scores = model.decision_function(X_scaled)
    held_out = df[df["is_anomaly"] == 1]

    alert_threshold = 0.0
    detection_rate = None
    false_positive_rate = None
    severity_bands = {"high": -0.06, "medium": -0.02}

    if len(held_out) > 0:
        anomaly_scores = model.decision_function(
            scaler.transform(held_out[ANOMALY_FEATURES].to_numpy(dtype=float))
        )
        detection_rate = float((anomaly_scores < alert_threshold).mean())
        false_positive_rate = float((normal_scores < alert_threshold).mean())

        print(f"\n  score ranges  normal: [{normal_scores.min():+.3f}, {normal_scores.max():+.3f}]"
              f"   anomalous: [{anomaly_scores.min():+.3f}, {anomaly_scores.max():+.3f}]")
        print(f"  calibrated alert threshold: {alert_threshold:+.3f}")
        print(f"  held-out anomaly detection rate: {detection_rate:.1%}")
        print(f"  false positive rate on normal:   {false_positive_rate:.1%}")

        # Severity bands from the anomaly score quantiles, so "HIGH" means
        # "in the worst quartile of what this model considers anomalous".
        severity_bands = {
            "high": float(np.percentile(anomaly_scores, 25)),
            "medium": float(np.percentile(anomaly_scores, 60)),
        }
        print(f"  severity bands: HIGH < {severity_bands['high']:+.3f}, "
              f"MEDIUM < {severity_bands['medium']:+.3f}")

    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    metadata = {
        "model_version": MODEL_VERSION,
        "model_type": "IsolationForest",
        "trained_at": datetime.now(timezone.utc).isoformat(),
        "training_rows": int(len(normal)),
        "total_rows_available": int(len(df)),
        "feature_list": ANOMALY_FEATURES,
        "contamination": CONTAMINATION,
        "n_estimators": 250,
        "random_state": SEED,
        # Read back by app/ml/anomaly.py at inference time -- retraining
        # recalibrates the threshold without any code change.
        "alert_threshold": alert_threshold,
        "severity_bands": severity_bands,
        "metrics": {
            "held_out_detection_rate": detection_rate,
            "false_positive_rate": false_positive_rate,
            "alert_threshold": alert_threshold,
        },
        "data_note": (
            "Trained on SYNTHETIC data from ml/generate_training_data.py. "
            "Metrics measure fit to that generator, not real-world performance."
        ),
    }

    bundle = {"model": model, "scaler": scaler, "stats": stats, "metadata": metadata}
    out_path = ARTIFACT_DIR / "anomaly_model.joblib"
    joblib.dump(bundle, out_path)

    (ARTIFACT_DIR / "anomaly_metadata.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")

    size_kb = out_path.stat().st_size / 1024
    print(f"\nSaved {out_path}  ({size_kb:.0f} KB)")
    print(f"  version: {MODEL_VERSION}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
