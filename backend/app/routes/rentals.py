"""Rental endpoints: listing, overdue, and the check-in / check-out console."""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.deps import (
    TenantContext,
    get_asset_or_404,
    get_tenant_context,
    require_admin,
    scope_rentals,
)
from app.database import get_db
from app.models import Asset, Client, Employee, Rental, RentalStatus, Site
from app.schemas.domain import (
    AssetLookupResponse,
    CheckinRequest,
    CheckoutRequest,
    EmployeeOut,
    RentalOut,
)
from app.services import rental_service
from app.services.asset_service import (
    OPEN_RENTAL_STATES,
    _aware,
    active_rental_for,
    hours_until,
    resolve_asset_by_code,
    serialize_assets,
)
from app.services.rules_engine import evaluate_asset

router = APIRouter(prefix="/rentals", tags=["rentals"])


def _serialize_rentals(db: Session, rentals: list[Rental]) -> list[RentalOut]:
    if not rentals:
        return []
    asset_ids = {r.asset_id for r in rentals}
    client_ids = {r.client_id for r in rentals}
    site_ids = {r.site_id for r in rentals if r.site_id}

    assets = {a.id: a for a in db.execute(select(Asset).where(Asset.id.in_(asset_ids))).scalars()}
    clients = {c.id: c for c in db.execute(select(Client).where(Client.id.in_(client_ids))).scalars()}
    sites = {}
    if site_ids:
        sites = {s.id: s for s in db.execute(select(Site).where(Site.id.in_(site_ids))).scalars()}

    out = []
    for r in rentals:
        asset = assets.get(r.asset_id)
        out.append(
            RentalOut(
                id=r.id,
                asset_id=r.asset_id,
                asset_code=asset.asset_code if asset else None,
                product_type=asset.product_type if asset else None,
                client_id=r.client_id,
                client_name=clients[r.client_id].name if r.client_id in clients else None,
                site_id=r.site_id,
                site_code=sites[r.site_id].code if r.site_id in sites else None,
                checkout_at=_aware(r.checkout_at),
                expected_return_at=_aware(r.expected_return_at),
                actual_return_at=_aware(r.actual_return_at),
                status=r.status,
                rental_rate=r.rental_rate,
                hours_until_due=round(hours_until(r.expected_return_at), 2) if r.is_open else None,
                checkin_condition_notes=r.checkin_condition_notes,
            )
        )
    return out


@router.get("", response_model=list[RentalOut])
def list_rentals(
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(get_tenant_context),
    status_filter: RentalStatus | None = Query(default=None, alias="status"),
    limit: int = Query(default=200, ge=1, le=500),
) -> list[RentalOut]:
    stmt = scope_rentals(select(Rental), ctx)
    if status_filter:
        stmt = stmt.where(Rental.status == status_filter.value)
    rows = db.execute(stmt.order_by(Rental.expected_return_at).limit(limit)).scalars().all()
    return _serialize_rentals(db, list(rows))


@router.get("/overdue", response_model=list[RentalOut])
def overdue_rentals(
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(get_tenant_context),
) -> list[RentalOut]:
    stmt = scope_rentals(
        select(Rental).where(Rental.status == RentalStatus.OVERDUE.value),
        ctx,
    )
    rows = db.execute(stmt.order_by(Rental.expected_return_at)).scalars().all()
    return _serialize_rentals(db, list(rows))


@router.get("/lookup/{code}", response_model=AssetLookupResponse)
def lookup_asset(
    code: str,
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(require_admin),
) -> AssetLookupResponse:
    """Resolve an asset by printed code OR QR/RFID token.

    Manual entry and a simulated scan both land here, so the two input paths
    can never drift apart.
    """
    asset = resolve_asset_by_code(db, code)
    if asset is None:
        raise HTTPException(status_code=404, detail=f"No asset matches '{code}'")

    rental = active_rental_for(db, asset.id)

    # Offer the operators who could be assigned: for a checked-out machine,
    # that is the renting client's active roster.
    employees: list[EmployeeOut] = []
    if asset.current_client_id is not None:
        rows = db.execute(
            select(Employee).where(Employee.client_id == asset.current_client_id, Employee.active.is_(True))
        ).scalars().all()
        employees = [EmployeeOut.model_validate(e) for e in rows]

    return AssetLookupResponse(
        asset=serialize_assets(db, [asset])[0],
        active_rental=_serialize_rentals(db, [rental])[0] if rental else None,
        available_employees=employees,
    )


@router.post("/checkout", response_model=RentalOut, status_code=status.HTTP_201_CREATED)
def checkout(
    payload: CheckoutRequest,
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(require_admin),
) -> RentalOut:
    """Check an asset out to a client. Company admins only."""
    asset = _resolve_target(db, payload.asset_id, payload.asset_code, ctx)

    if db.get(Client, payload.client_id) is None:
        raise HTTPException(status_code=404, detail="Client not found")

    rental = rental_service.checkout(
        db,
        asset=asset,
        client_id=payload.client_id,
        site_id=payload.site_id,
        employee_id=payload.employee_id,
        expected_return_at=payload.expected_return_at,
        rental_rate=payload.rental_rate,
        actor_user_id=ctx.user_id,
    )
    # Re-evaluate immediately so a checkout with no site/operator shows its
    # UNASSIGNED_EQUIPMENT alert straight away rather than a tick later.
    evaluate_asset(db, asset, rental)
    db.commit()
    db.refresh(rental)
    return _serialize_rentals(db, [rental])[0]


@router.post("/checkin", response_model=RentalOut)
def checkin(
    payload: CheckinRequest,
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(require_admin),
) -> RentalOut:
    """Check an asset back in, close the rental, return it to the warehouse."""
    asset = _resolve_target(db, payload.asset_id, payload.asset_code, ctx)

    rental = rental_service.checkin(
        db,
        asset=asset,
        condition_notes=payload.condition_notes,
        tire_condition=payload.tire_condition,
        engine_condition=payload.engine_condition,
        send_to_maintenance=payload.send_to_maintenance,
        actor_user_id=ctx.user_id,
    )
    db.commit()
    db.refresh(rental)
    return _serialize_rentals(db, [rental])[0]


def _resolve_target(db: Session, asset_id: int | None, asset_code: str | None, ctx: TenantContext) -> Asset:
    """Accept either an id or a code/QR token, then apply the tenant check."""
    if asset_id is not None:
        return get_asset_or_404(db, asset_id, ctx)
    if asset_code:
        asset = resolve_asset_by_code(db, asset_code)
        if asset is None:
            raise HTTPException(status_code=404, detail=f"No asset matches '{asset_code}'")
        # Route through the same scoped check rather than trusting the lookup.
        return get_asset_or_404(db, asset.id, ctx)
    raise HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        detail="Provide either asset_id or asset_code",
    )
