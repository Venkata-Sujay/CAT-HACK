"""Simulator control.

``POST /simulator/tick`` is deliberately exposed: firing a tick manually lets a
presenter advance the simulation on cue instead of waiting for the timer.
"""

from fastapi import APIRouter, Depends

from app.core.deps import TenantContext, require_admin
from app.schemas.common import MessageResponse
from app.schemas.dashboard import SimulatorStatus
from app.simulator.engine import simulator

router = APIRouter(prefix="/simulator", tags=["simulator"])


@router.get("/status", response_model=SimulatorStatus)
def status(ctx: TenantContext = Depends(require_admin)) -> SimulatorStatus:
    return SimulatorStatus(**simulator.status())


@router.post("/start", response_model=MessageResponse)
def start(ctx: TenantContext = Depends(require_admin)) -> MessageResponse:
    started = simulator.start()
    return MessageResponse(
        message="Simulator started" if started else "Simulator was already running",
        ok=started,
    )


@router.post("/stop", response_model=MessageResponse)
def stop(ctx: TenantContext = Depends(require_admin)) -> MessageResponse:
    stopped = simulator.stop()
    return MessageResponse(
        message="Simulator stopped" if stopped else "Simulator was not running",
        ok=stopped,
    )


@router.post("/tick", response_model=dict)
def manual_tick(ctx: TenantContext = Depends(require_admin)) -> dict:
    """Advance the simulation by exactly one interval, on demand."""
    return simulator.tick_once()
