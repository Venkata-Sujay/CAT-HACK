"""Telemetry simulator.

Each tick advances every deployed asset by ``SIMULATED_MINUTES_PER_TICK`` of
simulated machine time. In demo mode a tick fires every ``DEMO_TICK_SECONDS``
real seconds, so 10 real seconds represents 15 minutes of site activity and a
demo shows a full working day in a couple of minutes.

Design rules
------------
* **Plausible transitions, not random noise.** A machine that is running keeps
  running with high probability; fuel only ever falls unless a refuel event
  fires. Randomising every field each tick would look broken.
* **Anomalies are rare and they persist.** Health degrades one step at a time
  and never recovers on its own, so an alert raised at minute 2 of the demo is
  still there at minute 8.
* **Seeded.** With ``SIMULATION_SEED`` set, the same run produces the same
  sequence -- the demo behaves identically on the third rehearsal.
* **Shift-aware.** Activity drops outside 06:00-20:00 simulated time, so the
  utilisation chart has a realistic shape instead of a flat line.

Concurrency note: the tick body is synchronous SQLAlchemy work, so it runs via
``asyncio.to_thread`` to avoid blocking the event loop that is also serving API
requests.
"""

import asyncio
import logging
import random
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.database import SessionLocal
from app.models import (
    Asset,
    AssetStatus,
    Employee,
    HealthState,
    Rental,
    utcnow,
)
from app.services.asset_service import OPEN_RENTAL_STATES
from app.services.telemetry_service import apply_telemetry, reset_daily_counters

logger = logging.getLogger("rental.simulator")

DEPLOYED_STATES = (
    AssetStatus.RENTED.value,
    AssetStatus.ACTIVE.value,
    AssetStatus.IDLE.value,
    AssetStatus.OVERDUE.value,
)

# Cadences for the intelligence layer, in ticks. At the default 10s tick that is
# an ML sweep every minute and a forecast refresh every five.
ML_SWEEP_EVERY_N_TICKS = 6
FORECAST_EVERY_N_TICKS = 30


class SimulatorEngine:
    """Owns the simulated clock and the per-tick state machine."""

    def __init__(self) -> None:
        self._task: asyncio.Task | None = None
        self._running = False
        self.tick_count = 0
        self.last_tick_at: str | None = None
        self.assets_updated_last_tick = 0
        # Seeded generator: reproducible demos.
        self.rng = random.Random(settings.SIMULATION_SEED)
        # The simulated wall clock. Starts at real now and advances
        # SIMULATED_MINUTES_PER_TICK each tick.
        self.sim_clock = utcnow()

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------
    @property
    def running(self) -> bool:
        return self._running

    def start(self) -> bool:
        if self._running:
            return False
        self._running = True
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            # No event loop (e.g. called from a script) -- caller should use tick_once().
            self._running = False
            return False
        self._task = loop.create_task(self._loop())
        return True

    def stop(self) -> bool:
        if not self._running:
            return False
        self._running = False
        if self._task is not None:
            self._task.cancel()
            self._task = None
        return True

    async def _loop(self) -> None:
        while self._running:
            try:
                await asyncio.sleep(settings.DEMO_TICK_SECONDS)
                if not self._running:
                    break
                # Sync DB work off the event loop.
                await asyncio.to_thread(self.tick_once)
            except asyncio.CancelledError:
                break
            except Exception:  # noqa: BLE001 - a bad tick must not kill the loop
                logger.exception("Simulator tick failed; continuing")

    # ------------------------------------------------------------------
    # Tick
    # ------------------------------------------------------------------
    def tick_once(self) -> dict:
        """Advance the simulation by one interval. Safe to call manually."""
        with SessionLocal() as db:
            result = self._tick(db)
            db.commit()
        return result

    def _tick(self, db: Session) -> dict:
        minutes = settings.SIMULATED_MINUTES_PER_TICK
        previous_day = self.sim_clock.date()
        self.sim_clock = self.sim_clock + timedelta(minutes=minutes)

        assets = db.execute(select(Asset).where(Asset.status.in_(DEPLOYED_STATES))).scalars().all()

        # Simulated midnight: roll the per-day counters for the WHOLE fleet.
        if self.sim_clock.date() != previous_day:
            all_assets = db.execute(select(Asset)).scalars().all()
            reset_daily_counters(db, list(all_assets))
            logger.info("Simulated day rolled to %s; daily counters reset", self.sim_clock.date())

        # Operator rosters, loaded once per tick rather than per asset.
        rosters = self._operator_rosters(db, assets)

        updated = 0
        for asset in assets:
            try:
                self._advance_asset(db, asset, minutes, rosters)
                updated += 1
            except Exception:  # noqa: BLE001 - isolate a bad asset
                logger.exception("Failed to advance asset %s", asset.asset_code)

        self.tick_count += 1
        self.last_tick_at = utcnow().isoformat()
        self.assets_updated_last_tick = updated

        result = {
            "tick": self.tick_count,
            "assets_updated": updated,
            "simulated_clock": self.sim_clock.isoformat(),
        }

        # The ML sweep runs on a slower cadence than the rule engine. Rules are
        # cheap comparisons and must fire the instant a condition appears;
        # scoring 34 assets through IsolationForest every 10 seconds would burn
        # CPU to re-derive an answer that barely moves between ticks.
        if self.tick_count % ML_SWEEP_EVERY_N_TICKS == 0:
            try:
                from app.ml.anomaly import evaluate_fleet

                ml_result = evaluate_fleet(db, commit=False)
                result["ml_sweep"] = ml_result
                logger.info(
                    "ML sweep: scored %s assets, %s anomalies",
                    ml_result.get("scored", 0),
                    ml_result.get("anomalies", 0),
                )
            except Exception:  # noqa: BLE001 - intelligence must not break telemetry
                logger.exception("ML sweep failed; telemetry continues")

        # Forecast + recommendations refresh on a slower cadence still -- they
        # describe next week, so recomputing them every few seconds is pointless.
        if self.tick_count % FORECAST_EVERY_N_TICKS == 0:
            try:
                from app.ml.forecast import generate_forecasts
                from app.services.recommendation_service import regenerate_all

                generate_forecasts(db, commit=False)
                regenerate_all(db, commit=False)
                result["forecast_refreshed"] = True
            except Exception:  # noqa: BLE001
                logger.exception("Forecast refresh failed; telemetry continues")

        return result

    def _operator_rosters(self, db: Session, assets: list[Asset]) -> dict[int, list[Employee]]:
        """Active operators per client, used for the operator-mismatch event."""
        client_ids = {a.current_client_id for a in assets if a.current_client_id}
        if not client_ids:
            return {}
        rosters: dict[int, list[Employee]] = {}
        rows = db.execute(
            select(Employee).where(Employee.client_id.in_(client_ids), Employee.active.is_(True))
        ).scalars().all()
        for employee in rows:
            rosters.setdefault(employee.client_id, []).append(employee)
        return rosters

    # ------------------------------------------------------------------
    def _advance_asset(self, db: Session, asset: Asset, minutes: int, rosters: dict) -> None:
        rng = self.rng
        hour = self.sim_clock.hour
        within_shift = 6 <= hour < 20

        # A parked asset is checked out but never operated -- rented, forgotten,
        # accruing cost while producing nothing. It still reports telemetry (the
        # machine is powered and tracked), so idle time accumulates and the
        # under-utilization signal keeps strengthening rather than washing out.
        if asset.asset_code in settings.parked_asset_codes:
            apply_telemetry(
                db,
                asset=asset,
                is_running=False,
                runtime_delta=0,
                idle_delta=minutes,
                # Idling burns a trickle of fuel; the machine is not refuelled
                # because nobody is attending it.
                fuel_level=max(0.0, asset.fuel_level - rng.uniform(0.02, 0.06)),
                tire_health=asset.tire_condition,
                engine_health=asset.engine_condition,
                engine_temp_c=round(asset.engine_temp_c + (28.0 - asset.engine_temp_c) * 0.3, 1),
                latitude=asset.latitude,
                longitude=asset.longitude,
                operator_id=None,
                run_rules=True,
                flush=False,
            )
            return

        # --- 1. running / idle transition -------------------------------
        if asset.is_running:
            stop_prob = settings.SIM_STOP_WORK_PROB if within_shift else 0.85
            is_running = rng.random() > stop_prob
        else:
            start_prob = settings.SIM_START_WORK_PROB if within_shift else 0.02
            is_running = rng.random() < start_prob

        # An unexpected-inactivity event parks a machine that should be working.
        if within_shift and rng.random() < settings.SIM_UNEXPECTED_INACTIVITY_PROB:
            is_running = False

        # No fuel means no running, whatever the transition said.
        if asset.fuel_level <= 0.5:
            is_running = False

        runtime_delta = minutes if is_running else 0
        idle_delta = 0 if is_running else minutes

        # --- 2. fuel ----------------------------------------------------
        # Fuel only ever decreases here. The single exception is an explicit
        # refuel event below.
        if is_running:
            burn = rng.uniform(0.8, 1.5)
        else:
            burn = rng.uniform(0.05, 0.15)
        fuel = asset.fuel_level - burn

        if fuel < settings.REFUEL_TRIGGER_THRESHOLD and rng.random() < settings.SIM_REFUEL_PROB:
            fuel = rng.uniform(85.0, 100.0)
            logger.debug("%s refuelled to %.0f%%", asset.asset_code, fuel)

        fuel = max(0.0, min(100.0, fuel))

        # --- 3. component health (degrades only, one step at a time) -----
        tire = HealthState(asset.tire_condition)
        engine = HealthState(asset.engine_condition)
        if is_running:
            if rng.random() < settings.SIM_TIRE_DEGRADE_PROB:
                tire = tire.degraded()
            if rng.random() < settings.SIM_ENGINE_DEGRADE_PROB:
                engine = engine.degraded()

        # --- 4. engine temperature --------------------------------------
        if is_running:
            target = 78.0 + (12.0 if engine != HealthState.GOOD else 0.0)
            temp = asset.engine_temp_c + (target - asset.engine_temp_c) * 0.35 + rng.uniform(-1.5, 1.5)
        else:
            temp = asset.engine_temp_c + (30.0 - asset.engine_temp_c) * 0.30 + rng.uniform(-1.0, 1.0)

        # --- 5. operator ------------------------------------------------
        operator_id = self._choose_operator(asset, is_running, rosters, rng)

        # --- 6. position drift ------------------------------------------
        lat, lng = asset.latitude, asset.longitude
        if is_running and lat is not None and lng is not None:
            # ~10-50 m of movement per tick; keeps the machine on its site.
            lat += rng.uniform(-0.00045, 0.00045)
            lng += rng.uniform(-0.00045, 0.00045)

        apply_telemetry(
            db,
            asset=asset,
            is_running=is_running,
            runtime_delta=runtime_delta,
            idle_delta=idle_delta,
            fuel_level=fuel,
            tire_health=tire.value,
            engine_health=engine.value,
            engine_temp_c=round(temp, 1),
            latitude=lat,
            longitude=lng,
            operator_id=operator_id,
            run_rules=True,
            flush=False,
        )

    def _choose_operator(self, asset: Asset, is_running: bool, rosters: dict, rng: random.Random) -> int | None:
        """Decide who telemetry reports is operating the machine.

        Normally the assigned operator. With ``SIM_OPERATOR_MISMATCH_PROB`` a
        different operator from the same client is reported instead, which is
        what the UNAUTHORIZED_OPERATOR rule detects.
        """
        assigned = asset.assigned_employee_id
        roster = rosters.get(asset.current_client_id or -1, [])

        # Sticky assets keep whoever telemetry last reported, so a seeded
        # mismatch persists until a human intervenes rather than evaporating on
        # the next tick. See SIM_STICKY_OPERATOR_ASSET_CODES.
        if asset.asset_code in settings.sticky_operator_asset_codes:
            if asset.current_operator_id is not None:
                return asset.current_operator_id
            # Nobody recorded yet -- pick someone who is NOT the assigned
            # operator so the scripted mismatch establishes itself.
            candidates = [e.id for e in roster if e.id != assigned]
            return rng.choice(candidates) if candidates else assigned

        if not is_running:
            return None  # nobody in the cab

        if rng.random() < settings.SIM_OPERATOR_MISMATCH_PROB and roster:
            candidates = [e.id for e in roster if e.id != assigned]
            if candidates:
                return rng.choice(candidates)

        if assigned is not None:
            return assigned
        # No operator assigned but the machine is running -- someone is using an
        # unregistered machine. UNASSIGNED_EQUIPMENT covers this case.
        return rng.choice([e.id for e in roster]) if roster else None

    # ------------------------------------------------------------------
    def status(self) -> dict:
        return {
            "running": self._running,
            "tick_count": self.tick_count,
            "simulated_clock": self.sim_clock.isoformat(),
            "tick_seconds": settings.DEMO_TICK_SECONDS,
            "simulated_minutes_per_tick": settings.SIMULATED_MINUTES_PER_TICK,
            "seed": settings.SIMULATION_SEED,
            "last_tick_at": self.last_tick_at,
            "assets_updated_last_tick": self.assets_updated_last_tick,
        }


simulator = SimulatorEngine()
