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


# ---------------------------------------------------------------------------
# The simulator duty cycle. These constants MUST track backend/app/config.py --
# see the long note in generate_anomaly_data below.
# ---------------------------------------------------------------------------
SHIFT_START_HOUR = 6
SHIFT_END_HOUR = 20
# Must match MIN_SCORING_HOURS in backend/app/ml/anomaly.py.
# Four hours PAST shift start: before then the whole elapsed day was night,
# every machine legitimately reads zero runtime, and a genuinely dead machine
# is indistinguishable from one that simply has not clocked on.
MIN_SCORING_HOURS = 8.0
TICK_MINUTES = 15
P_START_IN_SHIFT = 0.25    # SIM_START_WORK_PROB
P_STOP_IN_SHIFT = 0.15     # SIM_STOP_WORK_PROB
P_START_OFF_SHIFT = 0.02
P_STOP_OFF_SHIFT = 0.85
REFUEL_TRIGGER = 15.0     # settings.REFUEL_TRIGGER_THRESHOLD
REFUEL_PROB = 0.30        # settings.SIM_REFUEL_PROB


def _simulate_day(
    npr: np.random.Generator,
    cut_hour: float,
    running_bias: float = 1.0,
    start_fuel: float | None = None,
) -> dict[str, float]:
    """Walk one asset through a day using the SIMULATOR duty cycle.

    Every quantity here is produced the way app/simulator/engine.py produces
    it, because the model is scored on what that simulator writes:

      runtime / idle   Markov chain, shift-aware, 15-minute ticks
      continuous       the CURRENT unbroken run, reset to 0 on every stop --
                       NOT the day's longest run. Getting this wrong made the
                       training median 165 minutes against a live median of 0.
      fuel             burns 0.8-1.5 per running tick and 0.05-0.15 per idle
                       tick, refuelled to 85-100 when it drops below the
                       trigger. Fuel carries ACROSS days, so it is seeded from
                       a random starting level rather than derived from today.
    """
    ticks = int((cut_hour * 60) // TICK_MINUTES)
    runtime = idle = 0.0
    continuous = 0.0
    is_running = False
    fuel = float(npr.uniform(25, 100) if start_fuel is None else start_fuel)

    for tick in range(ticks):
        hour = (tick * TICK_MINUTES) / 60.0
        in_shift = SHIFT_START_HOUR <= hour < SHIFT_END_HOUR
        p_start = (P_START_IN_SHIFT if in_shift else P_START_OFF_SHIFT) * running_bias
        p_stop = P_STOP_IN_SHIFT if in_shift else P_STOP_OFF_SHIFT

        if is_running:
            is_running = npr.random() > p_stop
        else:
            is_running = npr.random() < min(1.0, p_start)

        if fuel <= 0.5:
            is_running = False

        if is_running:
            runtime += TICK_MINUTES
            continuous += TICK_MINUTES
            fuel -= npr.uniform(0.8, 1.5)
        else:
            idle += TICK_MINUTES
            continuous = 0.0
            fuel -= npr.uniform(0.05, 0.15)

        if fuel < REFUEL_TRIGGER and npr.random() < REFUEL_PROB:
            fuel = float(npr.uniform(85.0, 100.0))
        fuel = float(min(100.0, max(0.0, fuel)))

    return {
        "runtime": runtime,
        "idle": idle,
        "continuous": continuous,
        "fuel_level": fuel,
    }


def _shift_utilization(runtime_minutes: float, hours_elapsed: float) -> float:
    """Runtime as a fraction of the shift time available so far.

    Mirrors backend/app/ml/features.py exactly -- see the note on the feature
    there for why this exists.
    """
    shift_minutes = max(0.0, min(hours_elapsed - SHIFT_START_HOUR, SHIFT_END_HOUR - SHIFT_START_HOUR)) * 60.0
    if shift_minutes <= 0:
        return 0.0
    return min(1.0, runtime_minutes / shift_minutes)


def generate_anomaly_data(rows: int, rng: random.Random, npr: np.random.Generator) -> pd.DataFrame:
    """Asset-day aggregates. ~5% anomalous, matching a realistic base rate.

    IsolationForest is unsupervised, so the ``is_anomaly`` column is NOT used for
    training. It is kept only so evaluate_models.py can report how well the
    unsupervised model separates the injected anomalies -- an honest check that
    the model learned something, without ever showing it the labels.

    -----------------------------------------------------------------------
    WHY THIS GENERATOR MIRRORS THE SIMULATOR, TICK FOR TICK
    -----------------------------------------------------------------------
    An earlier version invented its own idea of a normal working day: about
    380 minutes of runtime against 150 of idle, i.e. 72% utilization. The live
    simulator runs a Markov duty cycle inside an 06:00-20:00 shift and accrues
    idle through the night, which produces roughly 36% utilization and about
    3.5x the idle minutes.

    The model had therefore never seen the world it was deployed into. Its
    verdict on the running system was that 29 of 34 deployed machines were
    anomalous -- an action queue nobody could use, and a fair reading of which
    is "the intelligence layer is crying wolf".

    Nothing was wrong with the model. Training and serving simply disagreed
    about what normal looks like. So this generator now runs the SAME state
    machine the simulator runs, with the same probabilities and the same shift
    window, and each row is cut at a random hour of the day so the model also
    learns the trajectory: a machine with 40 minutes of runtime at 07:00 is
    normal, the same machine at 19:00 is not.

    If you change SIM_START_WORK_PROB, SIM_STOP_WORK_PROB or the shift window
    in backend/app/config.py, update the constants above and RETRAIN. This is
    the rule about sharing feature definitions, applied to the data itself.
    """
    records = []
    anomaly_rate = 0.05

    for _ in range(rows):
        is_anomaly = rng.random() < anomaly_rate
        mode = "normal"

        # Assets are scored throughout the day, not only at midnight, so the
        # training set has to span the day too.
        #
        # The floor is MIN_SCORING_HOURS, not zero, and that matters. Before a
        # machine is a few hours into its day there is no duty cycle to judge:
        # zero runtime at 03:00 is a machine that has not started, zero runtime
        # at 18:00 is a machine nobody is using. Training across hours 0-24
        # forces the model to learn that conditional from density alone, which
        # it cannot -- measured recall on "dead asset" was 32%. Restricting BOTH
        # training and scoring to the window where the question is answerable
        # is the honest fix, and inference enforces the same floor in
        # app/ml/anomaly.py.
        cut_hour = float(np.clip(npr.normal(16.0, 5.0), MIN_SCORING_HOURS, 24.0))
        day_fraction = cut_hour / 24.0

        if not is_anomaly:
            # ---- NORMAL: a machine on a normal duty cycle ----
            # Machines differ: some crews push hard, some sites are quiet.
            bias = float(np.clip(npr.normal(1.0, 0.15), 0.62, 1.45))
            day = _simulate_day(npr, cut_hour, bias)
            runtime, idle = day["runtime"], day["idle"]
            continuous, fuel_level = day["continuous"], day["fuel_level"]

            engaged = runtime + idle
            utilization = runtime / engaged if engaged > 0 else 0.0
            fuel_rate = (100 - fuel_level) / (engaged / 60) if engaged > 0 else 0.0

            engine_health = float(npr.choice([0, 1], p=[0.93, 0.07]))
            tire_health = float(npr.choice([0, 1], p=[0.91, 0.09]))
            operator_match = 1.0
            site_present = 1.0
            rental_active = 1.0
            # The simulator writes telemetry on every tick, so a healthy asset
            # is always freshly seen. A stale reading is itself the signal, and
            # only the lost_asset mode produces one.
            hours_since_seen = float(np.clip(npr.exponential(0.06), 0, 0.5))

        else:
            # ---- ANOMALOUS: one of several plausible failure modes ----
            # Each mode is expressed RELATIVE to the same duty cycle, so it
            # stays separable from normal at every hour of the day rather than
            # only at the end of one.
            # Two modes are deliberately absent, and both absences are load
            # bearing:
            #
            #   unauthorised operator -- a single boolean flip. The rule engine
            #     detects it with certainty; the model scored it at chance
            #     (measured 0/96). Benchmarking an unsupervised model on a case
            #     the architecture assigns to rules only understates it on the
            #     work it does own.
            #
            #   erratic cycling -- tried, then removed. It reads as an unusually
            #     SHORT continuous run, but the simulator stores the CURRENT run
            #     rather than the day's longest, and a normal machine is idle
            #     most ticks, so its current run is near zero too. The mode was
            #     indistinguishable from normal by construction, not by any
            #     failure of the model.
            mode = rng.choice(
                [
                    "dead_asset",
                    "unassigned_asset",
                    "overuse",
                    "fuel_anomaly",
                    "lost_asset",
                    "hard_failure",
                ]
            )

            day = _simulate_day(npr, cut_hour, 1.0)
            runtime, idle = day["runtime"], day["idle"]
            continuous, fuel_level = day["continuous"], day["fuel_level"]
            engine_health = 0.0
            tire_health = 0.0
            operator_match = 1.0
            site_present = 1.0
            rental_active = 1.0
            hours_since_seen = float(np.clip(npr.exponential(0.06), 0, 0.5))

            if mode == "dead_asset":
                # Rented but producing nothing -- the EQX1007 pattern.
                runtime = float(npr.uniform(0, 20) * day_fraction)
                idle = cut_hour * 60 - runtime
                continuous = 0.0
            elif mode == "overuse":
                # Running through the night, barely stopping.
                hard = _simulate_day(npr, cut_hour, 6.0)
                runtime = max(hard["runtime"], cut_hour * 60 * 0.88)
                idle = max(0.0, cut_hour * 60 - runtime)
                # Running for hours without a break is the whole signal here.
                continuous = max(hard["continuous"], runtime * 0.7)
                fuel_level = hard["fuel_level"]
            elif mode == "fuel_anomaly":
                # Burning far more fuel than the work performed justifies --
                # nearly empty despite very little work done.
                fuel_level = float(npr.uniform(1, 12))
                runtime = runtime * npr.uniform(0.15, 0.45)
                idle = cut_hour * 60 - runtime
            elif mode == "lost_asset":
                # Off the grid entirely: no site AND no telemetry for hours.
                site_present = 0.0
                hours_since_seen = float(npr.uniform(12, 96))
                runtime = float(npr.uniform(0, 45) * day_fraction)
                idle = cut_hour * 60 - runtime
            elif mode == "unassigned_asset":
                # Split out of lost_asset after it cost us a real detection.
                #
                # The combined mode always paired "no site" with "no telemetry
                # for hours", so the model learned them as one signal. The
                # problem statement's own row -- EQX1007, on hire, no site,
                # zero runtime -- reports telemetry perfectly well every tick,
                # matched only half the pattern, and scored +0.0088 against a
                # 0.0 threshold. It was missed by a hair, for a reason that had
                # nothing to do with the machine.
                #
                # A machine can be unaccounted for while still talking to you.
                # That is the more common and more expensive failure: it is
                # accruing rent and producing nothing, and nobody is looking.
                site_present = 0.0
                hours_since_seen = float(np.clip(npr.exponential(0.06), 0, 0.5))
                runtime = float(npr.uniform(0, 30) * day_fraction)
                idle = cut_hour * 60 - runtime
                continuous = 0.0
            elif mode == "hard_failure":
                engine_health = float(npr.choice([1, 2], p=[0.35, 0.65]))
                tire_health = float(npr.choice([0, 1, 2], p=[0.3, 0.35, 0.35]))
                runtime = runtime * npr.uniform(0.15, 0.5)
                idle = cut_hour * 60 - runtime

            runtime = max(0.0, runtime)
            idle = max(0.0, idle)
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
                "hours_elapsed_today": round(engaged / 60.0, 3),
                "shift_utilization": round(
                    _shift_utilization(runtime, engaged / 60.0), 4
                ),
                "is_anomaly": int(is_anomaly),
                # Kept for EVALUATION ONLY. IsolationForest never sees it, and
                # the training script drops it. It exists so recall can be
                # reported per failure mode rather than as one flat number that
                # hides which failures the model actually catches.
                "anomaly_mode": mode,
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
