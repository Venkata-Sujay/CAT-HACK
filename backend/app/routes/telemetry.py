"""Telemetry ingestion.

The in-process simulator writes through ``services/telemetry_service.py``
directly. This endpoint exists so real hardware -- or a load test, or a second
simulator process -- can post the same payload shape over HTTP.
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.deps import TenantContext, require_admin
from app.database import get_db
from app.models import Employee
from app.schemas.common import MessageResponse
from app.schemas.domain import TelemetryIngest
from app.services.asset_service import resolve_asset_by_code
from app.services.telemetry_service import apply_telemetry

router = APIRouter(prefix="/telemetry", tags=["telemetry"])


@router.post("", response_model=MessageResponse)
def ingest(
    payload: TelemetryIngest,
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(require_admin),
) -> MessageResponse:
    """Ingest one telemetry tick and run the rule engine over the asset."""
    asset = resolve_asset_by_code(db, payload.asset_code)
    if asset is None:
        raise HTTPException(status_code=404, detail=f"No asset matches '{payload.asset_code}'")

    operator_id = None
    if payload.current_operator_code:
        operator = db.execute(
            select(Employee).where(Employee.employee_code == payload.current_operator_code)
        ).scalar_one_or_none()
        if operator is None:
            raise HTTPException(status_code=404, detail=f"No operator matches '{payload.current_operator_code}'")
        operator_id = operator.id

    apply_telemetry(
        db,
        asset=asset,
        is_running=payload.is_running,
        runtime_delta=payload.runtime_delta_minutes,
        idle_delta=payload.idle_delta_minutes,
        fuel_level=payload.fuel_level,
        tire_health=payload.tire_health.value,
        engine_health=payload.engine_health.value,
        engine_temp_c=payload.engine_temp_c,
        latitude=payload.latitude,
        longitude=payload.longitude,
        operator_id=operator_id,
        run_rules=True,
    )
    db.commit()
    return MessageResponse(message=f"Telemetry recorded for {asset.asset_code}")
