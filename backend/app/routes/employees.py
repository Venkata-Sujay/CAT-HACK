"""Employee (operator) endpoints.

Tenant handling worth noting: ``EmployeeCreate.client_id`` is accepted only from
company admins. When a client calls this endpoint their own ``client_id`` from
the token is used and any value they supplied in the body is ignored -- that is
the "clients cannot provide an arbitrary client_id" rule in practice.
"""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.deps import (
    TenantContext,
    get_employee_or_404,
    get_tenant_context,
    scope_employees,
)
from app.database import get_db
from app.models import Asset, Client, Employee
from app.schemas.domain import EmployeeCreate, EmployeeOut, EmployeeUpdate, EmployeeWithAssignment

router = APIRouter(prefix="/employees", tags=["employees"])


@router.get("", response_model=list[EmployeeWithAssignment])
def list_employees(
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(get_tenant_context),
    client_id: int | None = Query(default=None, description="Admin-only filter; ignored for client accounts"),
    active_only: bool = False,
) -> list[EmployeeWithAssignment]:
    stmt = scope_employees(select(Employee), ctx)

    # An admin may narrow to one tenant. For a client this parameter is a no-op:
    # scope_employees already pinned the query to their own client_id.
    if ctx.is_admin and client_id is not None:
        stmt = stmt.where(Employee.client_id == client_id)
    if active_only:
        stmt = stmt.where(Employee.active.is_(True))

    employees = db.execute(stmt.order_by(Employee.employee_code)).scalars().all()
    if not employees:
        return []

    # Which asset (if any) each operator is currently assigned to.
    emp_ids = [e.id for e in employees]
    assignments = {
        a.assigned_employee_id: a
        for a in db.execute(select(Asset).where(Asset.assigned_employee_id.in_(emp_ids))).scalars()
    }

    return [
        EmployeeWithAssignment(
            id=e.id,
            client_id=e.client_id,
            employee_code=e.employee_code,
            name=e.name,
            phone=e.phone,
            active=e.active,
            assigned_asset_id=assignments[e.id].id if e.id in assignments else None,
            assigned_asset_code=assignments[e.id].asset_code if e.id in assignments else None,
        )
        for e in employees
    ]


@router.post("", response_model=EmployeeOut, status_code=status.HTTP_201_CREATED)
def create_employee(
    payload: EmployeeCreate,
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(get_tenant_context),
) -> EmployeeOut:
    if ctx.is_admin:
        if payload.client_id is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="client_id is required when creating an employee as a company admin",
            )
        target_client_id = payload.client_id
        if db.get(Client, target_client_id) is None:
            raise HTTPException(status_code=404, detail="Client not found")
    else:
        # The client_id in the body is deliberately discarded here.
        target_client_id = ctx.client_id

    code = (payload.employee_code or "").strip()
    if not code:
        last = db.execute(select(func.count(Employee.id))).scalar_one()
        code = f"OP-{100 + last + 1}"
    if db.execute(select(Employee).where(Employee.employee_code == code)).scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"Employee code {code} already exists")

    employee = Employee(
        client_id=target_client_id,
        employee_code=code,
        name=payload.name.strip(),
        phone=payload.phone,
        active=True,
    )
    db.add(employee)
    db.commit()
    db.refresh(employee)
    return EmployeeOut.model_validate(employee)


@router.patch("/{employee_id}", response_model=EmployeeOut)
def update_employee(
    employee_id: int,
    payload: EmployeeUpdate,
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(get_tenant_context),
) -> EmployeeOut:
    employee = get_employee_or_404(db, employee_id, ctx)

    if payload.name is not None:
        employee.name = payload.name.strip()
    if payload.phone is not None:
        employee.phone = payload.phone
    if payload.active is not None:
        employee.active = payload.active
        if not payload.active:
            # Deactivating must not leave a machine pointing at an inactive operator.
            for asset in db.execute(select(Asset).where(Asset.assigned_employee_id == employee.id)).scalars():
                asset.assigned_employee_id = None

    db.commit()
    db.refresh(employee)
    return EmployeeOut.model_validate(employee)
