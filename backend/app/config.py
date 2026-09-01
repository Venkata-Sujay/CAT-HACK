"""Application configuration.

All tunables live here and are overridable via environment variables or a .env
file. Nothing in the codebase should hardcode a threshold -- the rule engine and
simulator both read their constants from this object so a demo can be retuned
without touching logic.
"""

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# backend/app/config.py -> backend/app -> backend -> <repo root>
REPO_ROOT = Path(__file__).resolve().parent.parent.parent
BACKEND_ROOT = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(BACKEND_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ------------------------------------------------------------------
    # Core
    # ------------------------------------------------------------------
    APP_NAME: str = "Smart Rental Tracking System"
    API_PREFIX: str = "/api"
    DEBUG: bool = True

    # ------------------------------------------------------------------
    # Database
    # ------------------------------------------------------------------
    # SQLite is the default because the target machine has no PostgreSQL and no
    # running Docker daemon (see PROJECT_STATE.md -> Environment Audit).
    # The schema is deliberately portable: swapping this to
    # postgresql+psycopg://user:pass@localhost:5432/rental requires no code change.
    DATABASE_URL: str = f"sqlite:///{(BACKEND_ROOT / 'rental.db').as_posix()}"
    SQL_ECHO: bool = False

    # ------------------------------------------------------------------
    # Auth
    # ------------------------------------------------------------------
    # Demo-only default. Override in production via environment.
    SECRET_KEY: str = "dev-only-insecure-key-change-me-in-production"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 8  # 8h: outlasts a demo, no refresh flow
    BCRYPT_ROUNDS: int = 12

    # ------------------------------------------------------------------
    # CORS
    # ------------------------------------------------------------------
    CORS_ORIGINS: str = "http://localhost:5173,http://127.0.0.1:5173,http://localhost:4173"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]

    # ------------------------------------------------------------------
    # Simulator
    # ------------------------------------------------------------------
    SIMULATION_SEED: int = 42
    DEMO_TICK_SECONDS: int = 10          # real seconds between ticks
    SIMULATED_MINUTES_PER_TICK: int = 15  # simulated asset-minutes per tick
    SIMULATOR_AUTOSTART: bool = True

    # Anomaly injection probabilities, per RUNNING asset, per tick.
    #
    # CALIBRATED FROM OBSERVED BEHAVIOUR, not from intuition. The brief suggested
    # 2-5% for tire degradation, but that was measured against a tick and demo
    # mode compresses time ~90x: at DEMO_TICK_SECONDS=10 and 15 simulated minutes
    # per tick, 22 real minutes of demo is 34 simulated hours.
    #
    # At p=0.03 only 13% of assets survive 134 ticks without degrading. Running
    # the simulator for 22 minutes produced 52 open tire/engine alerts across a
    # 50-machine fleet -- an epidemic, not an anomaly, and an unusable action
    # queue. Health is deliberately monotonic (it only recovers via maintenance),
    # so degradation accumulates and never washes out.
    #
    # These values target a handful of NEW degradations over a 20-30 minute demo:
    #   ~150 ticks x ~17 running assets = ~2,500 asset-ticks
    #   0.0015 x 2,500 = ~4 new tire events. Visible, still rare.
    SIM_TIRE_DEGRADE_PROB: float = 0.0015
    SIM_ENGINE_DEGRADE_PROB: float = 0.0010
    # Higher than the health rates because operator mismatch AUTO-RESOLVES when
    # the correct operator returns -- it is self-limiting, so it can churn
    # without accumulating. Yields roughly 1-2 live at any moment.
    SIM_OPERATOR_MISMATCH_PROB: float = 0.005
    SIM_UNEXPECTED_INACTIVITY_PROB: float = 0.004
    SIM_START_WORK_PROB: float = 0.25     # IDLE -> RUNNING
    SIM_STOP_WORK_PROB: float = 0.15      # RUNNING -> IDLE
    SIM_REFUEL_PROB: float = 0.30         # chance/tick once fuel < refuel threshold

    # Assets the simulator keeps parked: checked out, but nobody is using them.
    #
    # EQX1007 is the scripted demo anomaly (the row lifted from the original
    # problem statement: Excavator, NULL site, 0 engine hours, 12 idle hours).
    # Without this the simulator would start running it like any other machine
    # within a minute or two, its UNDERUTILIZED alert would auto-resolve, and
    # Demo Scene 2 would silently disappear partway through a presentation.
    #
    # This models a real situation, not just a demo hack: equipment that is
    # rented, forgotten, and accruing cost while producing nothing.
    SIM_PARKED_ASSET_CODES: str = "EQX1007"

    # Assets where the simulator KEEPS REPORTING whoever telemetry last saw in
    # the cab, instead of re-rolling the operator each tick.
    #
    # EQX1012 is seeded with a deliberate mismatch (assigned to one Acme operator,
    # telemetry reports a different one) for Demo Scene 4. Without stickiness the
    # simulator reassigns the correct operator within a tick or two and the
    # CRITICAL unauthorized-operator alert auto-resolves before it can be shown.
    #
    # This models the real situation: the same unauthorized person keeps
    # operating the machine until somebody intervenes. The scene's payoff still
    # works -- assigning the operator who is ACTUALLY in the cab makes
    # assigned == reported, and the alert resolves for good.
    SIM_STICKY_OPERATOR_ASSET_CODES: str = "EQX1012"

    @property
    def parked_asset_codes(self) -> set[str]:
        return {code.strip() for code in self.SIM_PARKED_ASSET_CODES.split(",") if code.strip()}

    @property
    def sticky_operator_asset_codes(self) -> set[str]:
        return {
            code.strip() for code in self.SIM_STICKY_OPERATOR_ASSET_CODES.split(",") if code.strip()
        }

    # ------------------------------------------------------------------
    # Rule engine thresholds
    #
    # These are configurable OPERATIONAL RECOMMENDATIONS for a demo. They are
    # not certified machinery safety limits and the UI labels them as such.
    # ------------------------------------------------------------------
    CONTINUOUS_USAGE_THRESHOLD_MINUTES: int = 360   # 6h continuous operation
    UNDERUTILIZED_WINDOW_MINUTES: int = 360         # look-back window
    UNDERUTILIZED_MAX_RUNTIME_MINUTES: int = 30     # near-zero productive runtime
    LOW_FUEL_THRESHOLD: float = 20.0                # percent
    REFUEL_TRIGGER_THRESHOLD: float = 15.0          # simulator refuels below this
    DUE_SOON_HOURS: int = 48                        # rental deadline warning window
    CLIENT_HIGH_UTILIZATION_THRESHOLD: float = 0.85  # triggers "request more assets"

    # ------------------------------------------------------------------
    # ML
    # ------------------------------------------------------------------
    ML_ARTIFACTS_DIR: str = str(REPO_ROOT / "ml" / "artifacts")
    ML_DATA_DIR: str = str(REPO_ROOT / "ml" / "data")
    ANOMALY_MODEL_FILE: str = "anomaly_model.joblib"
    DEMAND_MODEL_FILE: str = "demand_model.joblib"
    # IsolationForest score below this is treated as anomalous enough to alert.
    # Fallback only. The live value is calibrated at training time and stored in
    # the model artifact (see ml/train_anomaly_model.py); inference reads it there.
    ANOMALY_ALERT_THRESHOLD: float = 0.0

    @property
    def artifacts_path(self) -> Path:
        return Path(self.ML_ARTIFACTS_DIR)

    @property
    def data_path(self) -> Path:
        return Path(self.ML_DATA_DIR)

    @property
    def is_sqlite(self) -> bool:
        return self.DATABASE_URL.startswith("sqlite")


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
