"""Client (tenant) endpoints. Company roles only."""

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.deps import TenantContext, require_admin
from app.database import get_db
from app.models import Alert, AlertSeverity, AlertStatus, Asset, Client, Employee
from app.schemas.onboarding import (
    ClientOnboardingRequest,
    ClientOnboardingResponse,
    InventoryLine,
)
from app.services import onboarding_service

router = APIRouter(prefix="/clients", tags=["clients"])


class ClientOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    code: str
    contact_email: str | None = None
    contact_phone: str | None = None
    active: bool


class ClientWithStats(ClientOut):
    rented_assets: int = 0
    employees: int = 0
    open_alerts: int = 0
    critical_alerts: int = 0
    avg_utilization: float = 0.0


@router.get("", response_model=list[ClientWithStats])
def list_clients(
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(require_admin),
) -> list[ClientWithStats]:
    """All tenants with a rollup. Admin-only: a client must never enumerate other clients."""
    clients = db.execute(select(Client).order_by(Client.name)).scalars().all()
    if not clients:
        return []

    asset_counts = dict(
        db.execute(
            select(Asset.current_client_id, func.count(Asset.id))
            .where(Asset.current_client_id.is_not(None))
            .group_by(Asset.current_client_id)
        ).all()
    )
    employee_counts = dict(
        db.execute(select(Employee.client_id, func.count(Employee.id)).group_by(Employee.client_id)).all()
    )

    live = (AlertStatus.OPEN.value, AlertStatus.ACKNOWLEDGED.value)
    open_alerts = dict(
        db.execute(
            select(Alert.client_id, func.count(Alert.id))
            .where(Alert.status.in_(live), Alert.client_id.is_not(None))
            .group_by(Alert.client_id)
        ).all()
    )
    critical = dict(
        db.execute(
            select(Alert.client_id, func.count(Alert.id))
            .where(
                Alert.status.in_(live),
                Alert.severity == AlertSeverity.CRITICAL.value,
                Alert.client_id.is_not(None),
            )
            .group_by(Alert.client_id)
        ).all()
    )

    utilization: dict[int, float] = {}
    for client_id, runtime, idle in db.execute(
        select(
            Asset.current_client_id,
            func.sum(Asset.runtime_minutes_today),
            func.sum(Asset.idle_minutes_today),
        )
        .where(Asset.current_client_id.is_not(None))
        .group_by(Asset.current_client_id)
    ).all():
        denom = (runtime or 0) + (idle or 0)
        utilization[client_id] = (runtime or 0) / denom if denom else 0.0

    return [
        ClientWithStats(
            id=c.id,
            name=c.name,
            code=c.code,
            contact_email=c.contact_email,
            contact_phone=c.contact_phone,
            active=c.active,
            rented_assets=asset_counts.get(c.id, 0),
            employees=employee_counts.get(c.id, 0),
            open_alerts=open_alerts.get(c.id, 0),
            critical_alerts=critical.get(c.id, 0),
            avg_utilization=round(utilization.get(c.id, 0.0), 4),
        )
        for c in clients
    ]


# ---------------------------------------------------------------------------
# Onboarding
# ---------------------------------------------------------------------------


@router.get("/availability", response_model=list[InventoryLine])
def depot_availability(
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(require_admin),
) -> list[InventoryLine]:
    """What can be allocated to a new client right now, by equipment type.

    The onboarding wizard reads this so an admin sees the ceiling while they
    are choosing, instead of finding out on submit. Admin-only for the same
    reason the client list is: depot stock is not a client's business.
    """
    return onboarding_service.warehouse_inventory(db)


@router.post(
    "",
    response_model=ClientOnboardingResponse,
    status_code=status.HTTP_201_CREATED,
)
def onboard_client(
    payload: ClientOnboardingRequest,
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(require_admin),
) -> ClientOnboardingResponse:
    """Register a new client: tenant, portal login, sites, and opening fleet.

    One transaction. Either all of it lands or none of it does -- see
    app/services/onboarding_service.py for why that matters.

    Admin-only, and this one really is admin-only: it mints a login. A client
    calling it gets 403, not 404, because the route existing is not a secret.
    """
    return onboarding_service.onboard_client(db, payload, actor_user_id=ctx.user_id)
