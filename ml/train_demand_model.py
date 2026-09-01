"""Train the demand forecasting model.

Run:  python ml/train_demand_model.py

Model: HistGradientBoostingRegressor
------------------------------------
Chosen over XGBoost because it is already installed, handles NaN natively, is
strong on small tabular data, and adds no new artifact format. XGBoost remains
available as a swap if this fails to beat the baseline -- but adding a
dependency for a marginal gain is a poor trade.

TIME-AWARE SPLIT
----------------
Train on the earliest ~80% of the timeline, test on the most recent ~20%.
A shuffled split would let the model see future values while predicting the
past, inflating the metrics into meaninglessness. This is the single most
common way a time-series model is accidentally cheated into looking good.

BASELINE COMPARISON
-------------------
The model is compared against a 7-day rolling mean on the SAME test window.
A gradient booster that cannot beat a rolling average is not worth deploying,
and if that happens this script says so plainly rather than hiding it.
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
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.metrics import mean_absolute_error, mean_squared_error

from app.ml.features import DEMAND_FEATURES  # noqa: E402

DATA_DIR = Path(__file__).resolve().parent / "data"
ARTIFACT_DIR = Path(__file__).resolve().parent / "artifacts"
MODEL_VERSION = "demand-histgbr-v1"
SEED = 42
TRAIN_FRACTION = 0.8


def main() -> int:
    data_path = DATA_DIR / "demand_training.csv"
    if not data_path.exists():
        print(f"ERROR: {data_path} not found.\n  Run: python ml/generate_training_data.py")
        return 1

    df = pd.read_csv(data_path)
    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values("date").reset_index(drop=True)
    print(f"Loaded {len(df):,} rows spanning {df['date'].min():%Y-%m-%d} .. {df['date'].max():%Y-%m-%d}")

    # ---- categorical encoding (persisted so inference matches training) ----
    sites = sorted(df["site"].unique())
    products = sorted(df["product_type"].unique())
    site_encoder = {name: i for i, name in enumerate(sites)}
    product_encoder = {name: i for i, name in enumerate(products)}

    df["site_encoded"] = df["site"].map(site_encoder)
    df["product_encoded"] = df["product_type"].map(product_encoder)

    # ---- TIME-AWARE split: never shuffle a time series ----
    cutoff_index = int(len(df) * TRAIN_FRACTION)
    cutoff_date = df.iloc[cutoff_index]["date"]

    train = df[df["date"] < cutoff_date]
    test = df[df["date"] >= cutoff_date]

    print(f"\nTime-aware split at {cutoff_date:%Y-%m-%d}")
    print(f"  train: {len(train):,} rows  ({train['date'].min():%Y-%m-%d} .. {train['date'].max():%Y-%m-%d})")
    print(f"  test:  {len(test):,} rows  ({test['date'].min():%Y-%m-%d} .. {test['date'].max():%Y-%m-%d})")

    X_train = train[DEMAND_FEATURES].to_numpy(dtype=float)
    y_train = train["demand"].to_numpy(dtype=float)
    X_test = test[DEMAND_FEATURES].to_numpy(dtype=float)
    y_test = test["demand"].to_numpy(dtype=float)

    model = HistGradientBoostingRegressor(
        max_iter=300,
        learning_rate=0.06,
        max_depth=6,
        min_samples_leaf=15,
        l2_regularization=0.1,
        random_state=SEED,
        early_stopping=True,
        validation_fraction=0.15,
    )
    model.fit(X_train, y_train)

    predictions = np.clip(model.predict(X_test), 0, None)
    model_mae = float(mean_absolute_error(y_test, predictions))
    model_rmse = float(np.sqrt(mean_squared_error(y_test, predictions)))

    # ---- BASELINE: 7-day rolling mean, evaluated on the same test window ----
    baseline_predictions = test["rolling_7d_mean"].to_numpy(dtype=float)
    baseline_mae = float(mean_absolute_error(y_test, baseline_predictions))
    baseline_rmse = float(np.sqrt(mean_squared_error(y_test, baseline_predictions)))

    improvement = (baseline_mae - model_mae) / baseline_mae * 100 if baseline_mae else 0.0

    print("\n" + "=" * 58)
    print("  MODEL vs BASELINE  (7-day rolling mean)")
    print("=" * 58)
    print(f"  {'':14}{'MAE':>10}{'RMSE':>10}")
    print(f"  {'HistGBR':14}{model_mae:>10.4f}{model_rmse:>10.4f}")
    print(f"  {'Baseline':14}{baseline_mae:>10.4f}{baseline_rmse:>10.4f}")
    print("-" * 58)
    if improvement > 0:
        print(f"  Model beats baseline by {improvement:.1f}% on MAE")
    else:
        print(f"  WARNING: model is {abs(improvement):.1f}% WORSE than the baseline.")
        print("  The rolling average would be the better choice here.")
    print("=" * 58)

    # Feature importances via permutation -- HistGBR has no native attribute.
    print("\nComputing permutation importance...")
    from sklearn.inspection import permutation_importance

    # n_jobs=1 deliberately: joblib's loky backend fails to spawn workers under
    # Windows Store Python and dumps a CreateProcess traceback before falling
    # back. The dataset is small enough that serial is fast.
    perm = permutation_importance(model, X_test, y_test, n_repeats=5, random_state=SEED, n_jobs=1)
    importances = sorted(
        zip(DEMAND_FEATURES, perm.importances_mean), key=lambda pair: pair[1], reverse=True
    )
    print("  top drivers:")
    for name, value in importances[:5]:
        print(f"    {name:24} {value:+.4f}")

    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    metadata = {
        "model_version": MODEL_VERSION,
        "model_type": "HistGradientBoostingRegressor",
        "trained_at": datetime.now(timezone.utc).isoformat(),
        "training_rows": int(len(train)),
        "test_rows": int(len(test)),
        "split": "time-aware (no shuffling)",
        "split_date": cutoff_date.isoformat(),
        "feature_list": DEMAND_FEATURES,
        "metrics": {
            "model_mae": round(model_mae, 4),
            "model_rmse": round(model_rmse, 4),
            "baseline_mae": round(baseline_mae, 4),
            "baseline_rmse": round(baseline_rmse, 4),
            "improvement_over_baseline_pct": round(improvement, 2),
            "beats_baseline": bool(improvement > 0),
        },
        "feature_importance": {name: round(float(v), 5) for name, v in importances},
        "data_note": (
            "Trained on SYNTHETIC data from ml/generate_training_data.py. "
            "Metrics measure fit to that generator, not real-world performance."
        ),
    }

    bundle = {
        "model": model,
        "encoders": {"site": site_encoder, "product_type": product_encoder},
        "metadata": metadata,
    }
    out_path = ARTIFACT_DIR / "demand_model.joblib"
    joblib.dump(bundle, out_path)
    (ARTIFACT_DIR / "demand_metadata.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")

    print(f"\nSaved {out_path}  ({out_path.stat().st_size / 1024:.0f} KB)")
    print(f"  version: {MODEL_VERSION}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
