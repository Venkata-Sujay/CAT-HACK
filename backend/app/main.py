"""FastAPI application entrypoint.

Run with:  uvicorn app.main:app --reload --port 8000
Docs at:   http://localhost:8000/docs
"""

import logging
from contextlib import asynccontextmanager

# Must precede any scikit-learn/joblib import. See app/core/runtime.py.
from app.core.runtime import apply_all as _apply_runtime_fixes

_apply_runtime_fixes()

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app.config import settings
from app.database import Base, SessionLocal, engine
from app.schemas.dashboard import HealthResponse

# Importing the models package registers every mapper on Base.metadata.
# Without this create_all() would produce an empty schema.
import app.models  # noqa: F401  (side-effectful import, must precede create_all)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("rental")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup/shutdown.

    Model artifacts are loaded here rather than lazily so a missing model is
    reported once at boot with instructions, instead of surfacing as a confusing
    500 on the first dashboard request.
    """
    Base.metadata.create_all(engine)
    logger.info("Database ready: %s", settings.DATABASE_URL)

    from app.ml.registry import model_registry

    model_registry.load()
    if not model_registry.anomaly_ready:
        logger.warning("Anomaly model not loaded -- run: python ml/train_anomaly_model.py")
    if not model_registry.demand_ready:
        logger.warning("Demand model not loaded -- run: python ml/train_demand_model.py")

    from app.simulator.engine import simulator

    if settings.SIMULATOR_AUTOSTART:
        simulator.start()
        logger.info(
            "Simulator started: tick=%ss -> +%s simulated minutes (seed=%s)",
            settings.DEMO_TICK_SECONDS,
            settings.SIMULATED_MINUTES_PER_TICK,
            settings.SIMULATION_SEED,
        )

    yield

    simulator.stop()
    logger.info("Shutdown complete")


app = FastAPI(
    title=settings.APP_NAME,
    description=(
        "Smart equipment rental tracking platform.\n\n"
        "**TELEMETRY -> PLATFORM -> INTELLIGENCE -> ACTION**\n\n"
        "All client-scoped endpoints derive tenancy from the JWT. A `client_id` "
        "supplied in a query string is ignored, never honoured."
    ),
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Routers
# ---------------------------------------------------------------------------
from app.routes import (  # noqa: E402  (imported after app config by design)
    alerts,
    assets,
    auth,
    clients,
    dashboard,
    employees,
    intelligence,
    rentals,
    simulator as simulator_routes,
    sites,
    telemetry,
)

for _router in (
    auth.router,
    assets.router,
    sites.router,
    clients.router,
    employees.router,
    rentals.router,
    telemetry.router,
    alerts.router,
    intelligence.router,
    dashboard.router,
    simulator_routes.router,
):
    app.include_router(_router, prefix=settings.API_PREFIX)


@app.get(f"{settings.API_PREFIX}/health", response_model=HealthResponse, tags=["system"])
def health() -> HealthResponse:
    """Liveness plus a readiness picture of the intelligence layer."""
    from app.ml.registry import model_registry
    from app.simulator.engine import simulator as sim

    db_ok = True
    try:
        with SessionLocal() as db:
            db.execute(text("SELECT 1"))
    except Exception:  # noqa: BLE001 - health must never raise
        db_ok = False

    messages = []
    if not model_registry.anomaly_ready:
        messages.append("anomaly model missing (run ml/train_anomaly_model.py)")
    if not model_registry.demand_ready:
        messages.append("demand model missing (run ml/train_demand_model.py)")

    return HealthResponse(
        status="ok" if db_ok else "degraded",
        database=db_ok,
        anomaly_model_loaded=model_registry.anomaly_ready,
        demand_model_loaded=model_registry.demand_ready,
        simulator_running=sim.running,
        message="; ".join(messages) or None,
    )


@app.get("/", tags=["system"])
def root() -> dict:
    return {
        "name": settings.APP_NAME,
        "docs": "/docs",
        "health": f"{settings.API_PREFIX}/health",
    }
