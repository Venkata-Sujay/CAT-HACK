"""Authentication dependencies and the TENANT ISOLATION layer.

This module is the security boundary of the whole application. Read it before
adding any endpoint.

THE RULES
=========

1. ``client_id`` comes from the JWT and NOWHERE else. A client sending
   ``?client_id=2`` gets that parameter ignored, not honoured. There is no code
   path where a request body or query string can widen a caller's scope.

2. Every list query goes through a ``scope_*`` helper before pagination.

3. Every single-object fetch goes through ``get_*_or_404``, which applies the
   tenant filter INSIDE the lookup. A cross-tenant fetch is therefore
   indistinguishable from a row that does not exist.

4. Cross-tenant reads return **404, not 403**. A 403 would confirm the resource
   exists, leaking fleet size and valid IDs to an enumeration attack. 404 leaks
   nothing. 403 is reserved for *route-level* permission (e.g. a client calling
   an admin-only endpoint), where the route's existence is not a secret.

5. Write endpoints re-verify ownership of EVERY referenced foreign key. Checking
   only the primary object would let Client A attach their own employee to
   Client B's asset.
"""

from dataclasses import dataclass

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import Select
from sqlalchemy.orm import Session

from app.config import settings
from app.core.security import decode_access_token
from app.database import get_db
from app.models import (
    Alert,
    Asset,
    AssetEvent,
    Employee,
    Recommendation,
    Rental,
    TelemetryLog,
    User,
    UserRole,
)

oauth2_scheme = OAuth2PasswordBearer(tokenUrl=f"{settings.API_PREFIX}/auth/login", auto_error=False)

CREDENTIALS_EXCEPTION = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Could not validate credentials",
    headers={"WWW-Authenticate": "Bearer"},
)


@dataclass(frozen=True)
class TenantContext:
    """The authenticated caller and their data scope.

    ``client_id is None`` means a company role, which sees all tenants.
    Anything else is a hard filter applied to every query.
    """

    user: User
    client_id: int | None
    is_admin: bool

    @property
    def user_id(self) -> int:
        return self.user.id

    def owns(self, client_id: int | None) -> bool:
        """True if this caller may touch data belonging to ``client_id``."""
        return self.is_admin or (client_id is not None and client_id == self.client_id)


# ---------------------------------------------------------------------------
# Authentication
# ---------------------------------------------------------------------------


def get_current_user(
    token: str | None = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> User:
    if not token:
        raise CREDENTIALS_EXCEPTION

    payload = decode_access_token(token)
    if payload is None:
        raise CREDENTIALS_EXCEPTION

    raw_sub = payload.get("sub")
    if raw_sub is None:
        raise CREDENTIALS_EXCEPTION
    try:
        user_id = int(raw_sub)
    except (TypeError, ValueError):
        raise CREDENTIALS_EXCEPTION from None

    user = db.get(User, user_id)
    if user is None or not user.is_active:
        raise CREDENTIALS_EXCEPTION
    return user


def get_tenant_context(user: User = Depends(get_current_user)) -> TenantContext:
    """Build the request's data scope.

    Note the scope is derived from the *database* user row, not from the token's
    client_id claim. A token forged with a different client_id would still be
    rejected by signature verification, but deriving from the DB means a
    revoked/changed tenancy takes effect immediately rather than at token expiry.
    """
    is_admin = user.role in (UserRole.COMPANY_ADMIN.value, UserRole.COMPANY_OPERATOR.value)
    return TenantContext(
        user=user,
        client_id=None if is_admin else user.client_id,
        is_admin=is_admin,
    )


def require_admin(ctx: TenantContext = Depends(get_tenant_context)) -> TenantContext:
    """Gate an endpoint to company roles.

    Returns 403 (not 404) deliberately: the *route* is not a secret, only the
    data is. A client learning that /api/sites POST exists reveals nothing.
    """
    if not ctx.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This action requires a company administrator account",
        )
    return ctx


def require_client(ctx: TenantContext = Depends(get_tenant_context)) -> TenantContext:
    """Gate an endpoint to client roles (e.g. 'request more assets')."""
    if ctx.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This action is performed by a client account",
        )
    return ctx


# ---------------------------------------------------------------------------
# Query scoping -- apply to EVERY list query
# ---------------------------------------------------------------------------


def scope_assets(stmt: Select, ctx: TenantContext) -> Select:
    if ctx.is_admin:
        return stmt
    return stmt.where(Asset.current_client_id == ctx.client_id)


def scope_employees(stmt: Select, ctx: TenantContext) -> Select:
    if ctx.is_admin:
        return stmt
    return stmt.where(Employee.client_id == ctx.client_id)


def scope_rentals(stmt: Select, ctx: TenantContext) -> Select:
    if ctx.is_admin:
        return stmt
    return stmt.where(Rental.client_id == ctx.client_id)


def scope_alerts(stmt: Select, ctx: TenantContext) -> Select:
    if ctx.is_admin:
        return stmt
    return stmt.where(Alert.client_id == ctx.client_id)


def scope_recommendations(stmt: Select, ctx: TenantContext) -> Select:
    if ctx.is_admin:
        return stmt
    return stmt.where(Recommendation.client_id == ctx.client_id)


def scope_telemetry(stmt: Select, ctx: TenantContext) -> Select:
    if ctx.is_admin:
        return stmt
    return stmt.where(TelemetryLog.client_id == ctx.client_id)


def scope_events(stmt: Select, ctx: TenantContext) -> Select:
    if ctx.is_admin:
        return stmt
    return stmt.where(AssetEvent.client_id == ctx.client_id)


# ---------------------------------------------------------------------------
# Scoped single-object fetch -- 404 on cross-tenant, never 403
# ---------------------------------------------------------------------------

NOT_FOUND = HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Resource not found")


def get_asset_or_404(db: Session, asset_id: int, ctx: TenantContext) -> Asset:
    asset = db.get(Asset, asset_id)
    if asset is None:
        raise NOT_FOUND
    if not ctx.is_admin and asset.current_client_id != ctx.client_id:
        # Deliberately identical to the "does not exist" response.
        raise NOT_FOUND
    return asset


def get_employee_or_404(db: Session, employee_id: int, ctx: TenantContext) -> Employee:
    employee = db.get(Employee, employee_id)
    if employee is None:
        raise NOT_FOUND
    if not ctx.is_admin and employee.client_id != ctx.client_id:
        raise NOT_FOUND
    return employee


def get_rental_or_404(db: Session, rental_id: int, ctx: TenantContext) -> Rental:
    rental = db.get(Rental, rental_id)
    if rental is None:
        raise NOT_FOUND
    if not ctx.is_admin and rental.client_id != ctx.client_id:
        raise NOT_FOUND
    return rental


def get_alert_or_404(db: Session, alert_id: int, ctx: TenantContext) -> Alert:
    alert = db.get(Alert, alert_id)
    if alert is None:
        raise NOT_FOUND
    if not ctx.is_admin and alert.client_id != ctx.client_id:
        raise NOT_FOUND
    return alert


def get_recommendation_or_404(db: Session, rec_id: int, ctx: TenantContext) -> Recommendation:
    rec = db.get(Recommendation, rec_id)
    if rec is None:
        raise NOT_FOUND
    if not ctx.is_admin and rec.client_id != ctx.client_id:
        raise NOT_FOUND
    return rec
