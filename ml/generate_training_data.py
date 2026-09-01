"""Generate synthetic training data for both models.

Run:  python ml/generate_training_data.py

Produces two CSVs under ml/data/:

  anomaly_training.csv  -- asset-day telemetry aggregates, ~95% normal behaviour
  demand_training.csv   -- daily rental demand per (site, product_type)

HONESTY NOTE
------------
This data is synthetic. Metrics computed against it measure how well a model
fits our own generator, NOT real-world performance. That distinction is stated
in the evaluation report and should be stated to anyone reviewing this project.
The generator is built to be *plausible* -- weekly cycles, site preferences,
trends, correlated failures -- not to make the models look good.

Why train on generated aggregates rather than the seeded DB: the app database
holds 24 hours of telemetry for ~34 deployed assets. IsolationForest needs a
few thousand rows to characterise "normal", and the demand model needs months
of history. Generating the training set decouples model quality from how long
the demo has been running.
"""

import sys
from pathlib import Path as _Path

# Must run before joblib/scikit-learn import -- see app/core/runtime.py.
sys.path.insert(0, str(_Path(__file__).resolve().parent.parent / "backend"))
from app.core.runtime import apply_all as _apply_runtime_fixes  # noqa: E402

_apply_runtime_fixes()

import argparse
import random
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

SEED = 42
OUT_DIR = Path(__file__).resolve().parent / "data"

PRODUCT_TYPES = ["EXCAVATOR", "BULLDOZER", "CRANE", "GRADER", "WHEEL_LOADER"]
SITES = ["SITE-001", "SITE-002", "SITE-003"]

# Mirrors app/seed.py -- each site favours particular equipment, which is the
# signal the demand model should learn.
SITE_PREFERENCE = {
    "SITE-001": {"EXCAVATOR": 3.4, "CRANE": 2.2, "WHEEL_LOADER": 1.8, "BULLDOZER": 0.7, "GRADER": 0.5},
    "SITE-002": {"BULLDOZER": 3.1, "EXCAVATOR": 2.4, "WHEEL_LOADER": 1.9, "GRADER": 0.6, "CRANE": 0.4},
    "SITE-003": {"GRADER": 2.9, "WHEEL_LOADER": 2.3, "EXCAVATOR": 1.6, "BULLDOZER": 0.8, "CRANE": 0.3},
}


# ---------------------------------------------------------------------------
# Anomaly training data
# ---------------------------------------------------------------------------


def generate_anomaly_data(rows: int, rng: random.Random, npr: np.random.Generator) -> pd.DataFrame:
    """Asset-day aggregates. ~5% anomalous, matching a realistic base rate.

    IsolationForest is unsupervised, so the ``is_anomaly`` column is NOT used for
    training. It is kept only so evaluate_models.py can report how well the
    unsupervised model separates the injected anomalies -- an honest check that
    the model learned something, without ever showing it the labels.
    """
    records = []
    anomaly_rate = 0.05

    for _ in range(rows):
        is_anomaly = rng.random() < anomaly_rate

        if not is_anomaly:
            # ---- NORMAL: a machine doing a day's work ----
            runtime = float(npr.normal(380, 90))
            runtime = float(np.clip(runtime, 60, 620))
            idle = float(np.clip(npr.normal(150, 60), 20, 400))

            engaged = runtime + idle
            utilization = runtime / engaged

            fuel_level = float(np.clip(npr.normal(58, 20), 18, 100))
            fuel_used = 100 - fuel_level
            fuel_rate = fuel_used / (engaged / 60) if engaged > 0 else 0.0

            continuous = float(np.clip(npr.normal(140, 80), 0, 340))
            engine_health = float(npr.choice([0, 1], p=[0.93, 0.07]))
            tire_health = float(npr.choice([0, 1], p=[0.91, 0.09]))
            operator_match = 1.0
            site_present = 1.0
            rental_active = 1.0
            hours_since_seen = float(np.clip(npr.exponential(0.4), 0, 6))

        else:
            # ---- ANOMALOUS: one of several plausible failure modes ----
            mode = rng.choice(
                ["dead_asset", "operator_mismatch", "overuse", "fuel_anomaly", "lost_asset", "hard_failure"]
            )

            runtime = float(np.clip(npr.normal(380, 90), 60, 620))
            idle = float(np.clip(npr.normal(150, 60), 20, 400))
            fuel_level = float(np.clip(npr.normal(58, 20), 10, 100))
            continuous = float(np.clip(npr.normal(140, 80), 0, 340))
            engine_health = 0.0
            tire_health = 0.0
            operator_match = 1.0
            site_present = 1.0
            rental_active = 1.0
            hours_since_seen = float(np.clip(npr.exponential(0.4), 0, 6))

            if mode == "dead_asset":
                # Rented but producing nothing -- the EQX1007 pattern.
                runtime = float(npr.uniform(0, 25))
                idle = float(npr.uniform(500, 800))
                continuous = 0.0
            elif mode == "operator_mismatch":
                operator_match = 0.0
            elif mode == "overuse":
                runtime = float(npr.uniform(600, 900))
                idle = float(npr.uniform(0, 40))
                continuous = float(npr.uniform(500, 800))
            elif mode == "fuel_anomaly":
                # Burning far more fuel than the work performed justifies.
                fuel_level = float(npr.uniform(2, 18))
                runtime = float(npr.uniform(80, 200))
            elif mode == "lost_asset":
                site_present = 0.0
                hours_since_seen = float(npr.uniform(12, 96))
                runtime = float(npr.uniform(0, 60))
                idle = float(npr.uniform(300, 700))
            elif mode == "hard_failure":
                engine_health = float(npr.choice([1, 2], p=[0.35, 0.65]))
                tire_health = float(npr.choice([0, 1, 2], p=[0.3, 0.35, 0.35]))
                runtime = float(npr.uniform(30, 180))

            engaged = runtime + idle
            utilization = runtime / engaged if engaged > 0 else 0.0
            fuel_used = 100 - fuel_level
            fuel_rate = fuel_used / (engaged / 60) if engaged > 0 else 0.0

        records.append(
            {
                "runtime_minutes_today": round(runtime, 1),
                "idle_minutes_today": round(idle, 1),
                "utilization": round(utilization, 4),
                "fuel_consumption_rate": round(fuel_rate, 4),
                "fuel_level": round(fuel_level, 1),
                "continuous_runtime_minutes": round(continuous, 1),
                "engine_health_numeric": engine_health,
                "tire_health_numeric": tire_health,
                "operator_match": operator_match,
                "site_assignment_present": site_present,
                "rental_active": rental_active,
                "hours_since_last_seen": round(hours_since_seen, 3),
                "is_anomaly": int(is_anomaly),
            }
        )

    return pd.DataFrame(records)


# ---------------------------------------------------------------------------
# Demand training data
# ---------------------------------------------------------------------------


def generate_demand_data(days: int, npr: np.random.Generator, rng: random.Random) -> pd.DataFrame:
    """Daily demand per (site, product_type) with learnable structure.

    Patterns injected:
      * site preference   -- each site favours certain equipment
      * weekly cycle      -- weekends run at ~45%
      * gradual trend     -- demand grows across the period
      * seasonal ripple   -- a slow sinusoid on top
      * occasional spikes -- ~6% of days, 1.6-2.2x

    Without structure the model could not beat a rolling average, and the
    comparison in evaluate_models.py would be meaningless.
    """
    end = date.today()
    start = end - timedelta(days=days)

    records = []
    for offset in range(days):
        day = start + timedelta(days=offset)
        weekday = day.weekday()
        iso = day.isocalendar()

        weekend_factor = 0.45 if weekday >= 5 else 1.0
        trend_factor = 0.75 + (offset / days) * 0.55
        seasonal = 1.0 + 0.18 * np.sin(2 * np.pi * offset / 30.0)
        spike = rng.uniform(1.6, 2.2) if rng.random() < 0.06 else 1.0

        for site in SITES:
            for product in PRODUCT_TYPES:
                base = SITE_PREFERENCE[site][product]
                demand = base * weekend_factor * trend_factor * seasonal * spike
                demand += npr.normal(0, 0.35)
                records.append(
                    {
                        "date": day.isoformat(),
                        "site": site,
                        "product_type": product,
                        "demand": max(0.0, round(demand, 3)),
                    }
                )

    df = pd.DataFrame(records)

    # Lag and rolling features, computed per (site, product) series.
    df = df.sort_values(["site", "product_type", "date"]).reset_index(drop=True)
    grouped = df.groupby(["site", "product_type"], group_keys=False)

    df["prev_day_demand"] = grouped["demand"].shift(1)
    df["prev_week_demand"] = grouped["demand"].shift(7)
    for window in (7, 14, 30):
        df[f"rolling_{window}d_mean"] = grouped["demand"].transform(
            lambda s, w=window: s.shift(1).rolling(w, min_periods=1).mean()
        )

    parsed = pd.to_datetime(df["date"])
    df["day_of_week"] = parsed.dt.weekday
    df["week_of_year"] = parsed.dt.isocalendar().week.astype(int)
    df["month"] = parsed.dt.month
    df["is_weekend"] = (df["day_of_week"] >= 5).astype(int)

    # Utilisation correlates with demand -- busy sites run their fleet harder.
    df["avg_utilization_7d"] = np.clip(
        df["rolling_7d_mean"] / (df["rolling_7d_mean"].max() or 1) + npr.normal(0, 0.06, len(df)), 0, 1
    )
    df["active_rentals"] = np.round(df["rolling_7d_mean"].fillna(0)).astype(int)

    # Drop the warm-up rows where lags are undefined.
    return df.dropna().reset_index(drop=True)


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate synthetic ML training data")
    parser.add_argument("--anomaly-rows", type=int, default=12000)
    parser.add_argument("--demand-days", type=int, default=270)
    args = parser.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    rng = random.Random(SEED)
    npr = np.random.default_rng(SEED)

    print("Generating anomaly training data...")
    anomaly_df = generate_anomaly_data(args.anomaly_rows, rng, npr)
    anomaly_path = OUT_DIR / "anomaly_training.csv"
    anomaly_df.to_csv(anomaly_path, index=False)
    print(f"  {len(anomaly_df):,} rows -> {anomaly_path}")
    print(f"  anomaly fraction: {anomaly_df['is_anomaly'].mean():.1%}")

    print("\nGenerating demand training data...")
    demand_df = generate_demand_data(args.demand_days, npr, rng)
    demand_path = OUT_DIR / "demand_training.csv"
    demand_df.to_csv(demand_path, index=False)
    print(f"  {len(demand_df):,} rows -> {demand_path}")
    print(f"  date range: {demand_df['date'].min()} .. {demand_df['date'].max()}")
    print(f"  mean demand: {demand_df['demand'].mean():.2f}")

    print("\nDone. Next: python ml/train_anomaly_model.py && python ml/train_demand_model.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
