"""Check-out / check-in and operator assignment.

These are the state transitions of the domain. Every one of them writes an
``AssetEvent`` audit row -- the problem statement requires an audit record for
check-in/out, and having the same trail for assignment changes makes the asset
timeline actually useful.

Ownership re-verification
-------------------------
``assign_employee`` checks BOTH the asset and the employee against the caller's
tenant. Validating only the asset would let Client A attach their own operator
to Client B's excavator: the asset lookup would 404, but if the check were the
other way round the employee lookup would pass and the asset write would land.
Both sides get checked, always.
"""

import logging
from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.deps import TenantContext
from app.models import (
    Asset,
    AssetAssignment,
    AssetEvent,
    AssetStatus,
    Employee,
    EventType,
    HealthState,
    Rental,
    RentalStatus,
    Site,
    WarehouseStatus,
    utcnow,
)
from app.services.alert_service import auto_resolve
from app.services.asset_service import OPEN_RENTAL_STATES, active_rental_for
from app.models.enums import AlertType

logger = logging.getLogger("rental.rentals")


def _record_event(
    db: Session,
    *,
    asset: Asset,
    event_type: EventType,
    actor_user_id: int | None,
    old_value: str | None = None,
    new_value: str | None = None,
    description: str | None = None,
) -> None:
    db.add(
        AssetEvent(
            asset_id=asset.id,
            client_id=asset.current_client_id,
            actor_user_id=actor_user_id,
            event_type=event_type.value,
            old_value=old_value,
            new_value=new_value,
            description=description,
            timestamp=utcnow(),
        )
    )


def checkout(
    db: Session,
    *,
    asset: Asset,
    client_id: int,
    site_id: int | None,
    employee_id: int | None,
    expected_return_at: datetime,
    rental_rate: float | None,
    actor_user_id: int | None,
) -> Rental:
    """Check an asset out to a client.

    Refuses if the asset already has an open rental -- the "one active rental
    per asset" invariant lives here rather than in a partial unique index,
    which would need dialect-specific DDL.
    """
    existing = active_rental_for(db, asset.id)
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"{asset.asset_code} is already checked out (rental #{existing.id}). Check it in first.",
        )

    if asset.status == AssetStatus.MAINTENANCE.value:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"{asset.asset_code} is in maintenance and cannot be rented out.",
        )

    if expected_return_at.tzinfo is None:
        expected_return_at = expected_return_at.replace(tzinfo=timezone.utc)
    if expected_return_at <= utcnow():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Expected return date must be in the future.",
        )

    site = None
    if site_id is not None:
        site = db.get(Site, site_id)
        if site is None:
            raise HTTPException(status_code=404, detail="Site not found")

    employee = None
    if employee_id is not None:
        employee = db.get(Employee, employee_id)
        if employee is None:
            raise HTTPException(status_code=404, detail="Employee not found")
        if employee.client_id != client_id:
            # The operator must belong to the renting client.
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Operator does not belong to the renting client.",
            )

    previous_status = asset.status

    rental = Rental(
        asset_id=asset.id,
        client_id=client_id,
        site_id=site_id,
        checkout_at=utcnow(),
        expected_return_at=expected_return_at,
        status=RentalStatus.ACTIVE.value,
        rental_rate=rental_rate if rental_rate is not None else asset.daily_rate,
        checkout_by_user_id=actor_user_id,
    )
    db.add(rental)

    asset.current_client_id = client_id
    asset.current_site_id = site_id
    asset.status = AssetStatus.RENTED.value
    asset.warehouse_status = WarehouseStatus.DEPLOYED.value
    # Reset the daily counters so utilisation reflects THIS rental, not the last one.
    asset.runtime_minutes_today = 0
    asset.idle_minutes_today = 0
    asset.continuous_runtime_minutes = 0
    asset.is_running = False
    asset.current_operator_id = None

    if site is not None:
        asset.latitude = site.latitude
        asset.longitude = site.longitude

    if employee is not None:
        _set_assignment(db, asset=asset, employee=employee, actor_user_id=actor_user_id)

    _record_event(
        db,
        asset=asset,
        event_type=EventType.CHECKOUT,
        actor_user_id=actor_user_id,
        old_value=previous_status,
        new_value=AssetStatus.RENTED.value,
        description=(
            f"Checked out to client #{client_id}"
            + (f" at {site.code}" if site else "")
            + f", due {expected_return_at:%Y-%m-%d %H:%M}"
        ),
    )

    db.flush()
    return rental


def checkin(
    db: Session,
    *,
    asset: Asset,
    condition_notes: str | None,
    tire_condition: HealthState | None,
    engine_condition: HealthState | None,
    send_to_maintenance: bool,
    actor_user_id: int | None,
) -> Rental:
    """Close the active rental and return the asset to the warehouse."""
    rental = active_rental_for(db, asset.id)
    if rental is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"{asset.asset_code} has no active rental to check in.",
        )

    previous_status = asset.status

    rental.status = RentalStatus.RETURNED.value
    rental.actual_return_at = utcnow()
    rental.checkin_by_user_id = actor_user_id
    rental.checkin_condition_notes = condition_notes

    # Condition assessed by the receiving inspector overrides simulated health.
    # This is the ONLY path that can improve a health state -- see
    # HealthState docstring on monotonic degradation.
    if tire_condition is not None:
        asset.tire_condition = tire_condition.value
    if engine_condition is not None:
        asset.engine_condition = engine_condition.value

    # Clear the operator assignment: the machine is no longer with the client.
    _clear_assignment(db, asset=asset, actor_user_id=actor_user_id)

    asset.current_client_id = None
    asset.current_site_id = None
    asset.current_operator_id = None
    asset.is_running = False
    asset.continuous_runtime_minutes = 0

    if send_to_maintenance or asset.tire_condition == HealthState.CRITICAL.value or asset.engine_condition == HealthState.CRITICAL.value:
        asset.status = AssetStatus.MAINTENANCE.value
        asset.warehouse_status = WarehouseStatus.MAINTENANCE.value
    else:
        asset.status = AssetStatus.AVAILABLE.value
        asset.warehouse_status = WarehouseStatus.IN_WAREHOUSE.value

    # Rental-scoped alerts are meaningless once the machine is back.
    for alert_type in (
        AlertType.DUE_SOON,
        AlertType.OVERDUE,
        AlertType.UNAUTHORIZED_OPERATOR,
        AlertType.UNASSIGNED_EQUIPMENT,
        AlertType.UNDERUTILIZED,
        AlertType.CONTINUOUS_USAGE,
    ):
        auto_resolve(db, asset_id=asset.id, alert_type=alert_type, reason="Asset checked in")

    _record_event(
        db,
        asset=asset,
        event_type=EventType.CHECKIN,
        actor_user_id=actor_user_id,
        old_value=previous_status,
        new_value=asset.status,
        description=(
            f"Checked in from rental #{rental.id}"
            + (f". Notes: {condition_notes}" if condition_notes else "")
        ),
    )

    db.flush()
    return rental


# ---------------------------------------------------------------------------
# Operator assignment
# ---------------------------------------------------------------------------


def _set_assignment(db: Session, *, asset: Asset, employee: Employee, actor_user_id: int | None) -> None:
    """Close any open assignment and open a new one. Caller must have verified ownership."""
    _close_open_assignments(db, asset_id=asset.id)

    db.add(
        AssetAssignment(
            asset_id=asset.id,
            employee_id=employee.id,
            client_id=employee.client_id,
            assigned_at=utcnow(),
            active=True,
            assigned_by_user_id=actor_user_id,
        )
    )
    old = asset.assigned_employee_id
    asset.assigned_employee_id = employee.id

    _record_event(
        db,
        asset=asset,
        event_type=EventType.ASSIGN_OPERATOR,
        actor_user_id=actor_user_id,
        old_value=str(old) if old else None,
        new_value=employee.employee_code,
        description=f"Assigned operator {employee.employee_code} ({employee.name})",
    )


def _close_open_assignments(db: Session, *, asset_id: int) -> None:
    open_rows = (
        db.execute(select(AssetAssignment).where(AssetAssignment.asset_id == asset_id, AssetAssignment.active.is_(True)))
        .scalars()
        .all()
    )
    for row in open_rows:
        row.active = False
        row.unassigned_at = utcnow()


def _clear_assignment(db: Session, *, asset: Asset, actor_user_id: int | None) -> None:
    if asset.assigned_employee_id is None:
        return
    _close_open_assignments(db, asset_id=asset.id)
    old = asset.assigned_employee_id
    asset.assigned_employee_id = None
    _record_event(
        db,
        asset=asset,
        event_type=EventType.UNASSIGN_OPERATOR,
        actor_user_id=actor_user_id,
        old_value=str(old),
        description="Operator assignment cleared",
    )


def assign_employee(db: Session, *, asset: Asset, employee: Employee, ctx: TenantContext) -> Asset:
    """Assign an operator to an asset.

    Both objects must already have passed a tenant-scoped lookup. This function
    re-checks that they belong to the SAME client, which closes the cross-tenant
    hole where an admin (or a bug) pairs mismatched records.
    """
    if asset.current_client_id is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"{asset.asset_code} is not currently rented, so it cannot have an operator assigned.",
        )
    if employee.client_id != asset.current_client_id:
        # Not 403: revealing "that employee exists but belongs to someone else"
        # is exactly the disclosure we avoid elsewhere.
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Resource not found")
    if not employee.active:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Cannot assign an inactive employee.",
        )

    _set_assignment(db, asset=asset, employee=employee, actor_user_id=ctx.user_id)

    # If the newly assigned operator is the one already in the cab, the
    # unauthorized-operator condition has cleared. Resolve immediately rather
    # than waiting for the next tick -- this is Demo Scene 4.
    if asset.current_operator_id == employee.id:
        auto_resolve(
            db,
            asset_id=asset.id,
            alert_type=AlertType.UNAUTHORIZED_OPERATOR,
            reason=f"{employee.employee_code} is now the registered operator",
        )

    db.flush()
    return asset


def unassign_employee(db: Session, *, asset: Asset, ctx: TenantContext) -> Asset:
    _clear_assignment(db, asset=asset, actor_user_id=ctx.user_id)
    db.flush()
    return asset


def set_maintenance(db: Session, *, asset: Asset, active: bool, actor_user_id: int | None, notes: str | None = None) -> Asset:
    """Start or end a maintenance window.

    Ending maintenance is the ONLY way component health returns to GOOD --
    health degrades monotonically otherwise (see HealthState).
    """
    previous = asset.status
    if active:
        if active_rental_for(db, asset.id) is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Check the asset in before sending it to maintenance.",
            )
        asset.status = AssetStatus.MAINTENANCE.value
        asset.warehouse_status = WarehouseStatus.MAINTENANCE.value
        asset.is_running = False
        event = EventType.MAINTENANCE_START
        description = notes or "Withdrawn from service for maintenance"
    else:
        asset.status = AssetStatus.AVAILABLE.value
        asset.warehouse_status = WarehouseStatus.IN_WAREHOUSE.value
        asset.tire_condition = HealthState.GOOD.value
        asset.engine_condition = HealthState.GOOD.value
        asset.fuel_level = 100.0
        asset.continuous_runtime_minutes = 0
        event = EventType.MAINTENANCE_END
        description = notes or "Maintenance completed; condition restored to GOOD"

        for alert_type in (AlertType.TIRE_WARNING, AlertType.ENGINE_WARNING, AlertType.LOW_FUEL):
            auto_resolve(db, asset_id=asset.id, alert_type=alert_type, reason="Maintenance completed")

    _record_event(
        db,
        asset=asset,
        event_type=event,
        actor_user_id=actor_user_id,
        old_value=previous,
        new_value=asset.status,
        description=description,
    )
    db.flush()
    return asset
