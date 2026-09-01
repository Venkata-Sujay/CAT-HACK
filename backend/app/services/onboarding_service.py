"""Client onboarding: register a tenant and put machines on its site.

WHY THIS IS ONE CALL AND NOT FIVE
---------------------------------
Bringing a customer on is a single business event. Doing it as five separate
API calls means a half-created client is a normal outcome: a tenant with a
login and no equipment, or sites created against a client whose user creation
then failed. Every one of those states has to be cleaned up by hand.

So the whole thing is one transaction. Either the client exists with a working
login, its sites on the map and its machines checked out to it, or nothing was
written at all.

WHAT THIS DELIBERATELY REUSES
-----------------------------
Allocation goes through ``rental_service.checkout`` rather than setting asset
columns directly. That is the audited path: it writes the AssetEvent, enforces
the one-open-rental-per-asset invariant, refuses machines in maintenance, and
resets the daily counters. Re-implementing it here would give onboarding its
own subtly different rules, and the audit trail would have a hole in it exactly
where a machine first meets its customer.

INVENTORY IS REAL
-----------------
You cannot allocate equipment that is not in the depot. If a request asks for
four excavators and three are available, the whole call fails with a 409 that
names the shortfall, rather than silently handing over three. A rental company
that promises stock it does not have is the problem this system exists to fix.
"""

import logging
import re
from datetime import timedelta

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.models import (
    Asset,
    AssetStatus,
    Client,
    ProductType,
    Site,
    User,
    UserRole,
    WarehouseStatus,
    utcnow,
)
from app.schemas.onboarding import (
    AllocatedAsset,
    ClientOnboardingRequest,
    ClientOnboardingResponse,
    InventoryLine,
    OnboardedSite,
)
from app.services import rental_service

logger = logging.getLogger("rental.onboarding")


def _derive_code(name: str) -> str:
    """Turn a company name into a short tenant code."""
    letters = re.sub(r"[^A-Za-z0-9]", "", name).upper()
    return (letters[:4] or "CLNT")


def _unique_client_code(db: Session, preferred: str | None, name: str) -> str:
    base = (preferred or _derive_code(name)).strip().upper()[:12] or "CLNT"
    candidate = base
    suffix = 2
    while db.execute(select(Client.id).where(Client.code == candidate)).scalar_one_or_none():
        candidate = f"{base}{suffix}"
        suffix += 1
    return candidate


def _next_site_code(db: Session) -> str:
    """Continue the SITE-00N sequence rather than restarting it.

    Reads the highest existing numeric suffix instead of counting rows, so a
    deleted site never causes a code collision.
    """
    highest = 0
    for (code,) in db.execute(select(Site.code)).all():
        match = re.fullmatch(r"SITE-(\d+)", code or "")
        if match:
            highest = max(highest, int(match.group(1)))
    return f"SITE-{highest + 1:03d}"


def warehouse_inventory(db: Session) -> list[InventoryLine]:
    """Depot availability per equipment type -- what can be allocated today."""
    totals = dict(
        db.execute(select(Asset.product_type, func.count(Asset.id)).group_by(Asset.product_type)).all()
    )
    available = dict(
        db.execute(
            select(Asset.product_type, func.count(Asset.id))
            .where(
                Asset.status == AssetStatus.AVAILABLE.value,
                Asset.warehouse_status == WarehouseStatus.IN_WAREHOUSE.value,
            )
            .group_by(Asset.product_type)
        ).all()
    )
    return [
        InventoryLine(
            product_type=pt.value,
            available=int(available.get(pt.value, 0)),
            total=int(totals.get(pt.value, 0)),
        )
        for pt in ProductType
    ]


def onboard_client(
    db: Session,
    payload: ClientOnboardingRequest,
    actor_user_id: int | None,
) -> ClientOnboardingResponse:
    """Create a client, its login, its sites, and check its equipment out to it."""

    # ---- 1. Uniqueness, checked before anything is written ---------------
    name = payload.name.strip()
    login_email = payload.login_email.strip().lower()

    if db.execute(select(Client.id).where(func.lower(Client.name) == name.lower())).scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"A client named {name} already exists.",
        )
    if db.execute(select(User.id).where(func.lower(User.email) == login_email)).scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"{login_email} is already registered. Choose a different login email.",
        )

    # ---- 2. Reserve the equipment BEFORE creating anything ---------------
    #
    # Availability is checked and the specific machines are picked up front, so
    # an impossible request fails without having created a client that then has
    # to be deleted.
    picked: list[tuple[Asset, ProductType]] = []
    shortfalls: list[str] = []

    for line in payload.equipment:
        candidates = (
            db.execute(
                select(Asset)
                .where(
                    Asset.product_type == line.product_type.value,
                    Asset.status == AssetStatus.AVAILABLE.value,
                    Asset.warehouse_status == WarehouseStatus.IN_WAREHOUSE.value,
                )
                .order_by(Asset.asset_code)
                .limit(line.quantity)
            )
            .scalars()
            .all()
        )
        readable = line.product_type.value.replace("_", " ").title()
        if len(candidates) < line.quantity:
            shortfalls.append(
                f"{readable}: asked for {line.quantity}, {len(candidates)} in the depot"
            )
            continue
        picked.extend((asset, line.product_type) for asset in candidates)

    if shortfalls:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Not enough equipment in the depot — " + "; ".join(shortfalls),
        )

    # ---- 3. Client + login ----------------------------------------------
    client = Client(
        name=name,
        code=_unique_client_code(db, payload.code, name),
        contact_email=(payload.contact_email or None),
        contact_phone=(payload.contact_phone or None),
        active=True,
        created_at=utcnow(),
    )
    db.add(client)
    db.flush()  # need client.id for the user and sites

    user = User(
        email=login_email,
        password_hash=hash_password(payload.login_password),
        full_name=payload.login_full_name.strip(),
        # The User model's invariant: role CLIENT if and only if client_id is
        # set. Getting this pair wrong is how a new account would silently see
        # the whole fleet.
        role=UserRole.CLIENT.value,
        client_id=client.id,
        is_active=True,
        created_at=utcnow(),
    )
    db.add(user)
    db.flush()

    # ---- 4. Sites --------------------------------------------------------
    created_sites: list[Site] = []
    for spec in payload.sites:
        site = Site(
            code=_next_site_code(db),
            name=spec.name.strip(),
            address=spec.address,
            latitude=spec.latitude,
            longitude=spec.longitude,
            client_id=client.id,
            is_warehouse=False,
            active=True,
            created_at=utcnow(),
        )
        db.add(site)
        db.flush()  # so the next _next_site_code sees this one
        created_sites.append(site)

    # Everything goes to the client's first site. Spreading an opening
    # allocation across sites is a dispatch decision, and dispatch already has
    # a screen -- guessing here would just produce moves to undo.
    target_site = created_sites[0] if created_sites else None

    # ---- 5. Check the equipment out --------------------------------------
    expected_return_at = utcnow() + timedelta(days=payload.rental_days)
    allocated: list[AllocatedAsset] = []

    for asset, product_type in picked:
        rental = rental_service.checkout(
            db,
            asset=asset,
            client_id=client.id,
            site_id=target_site.id if target_site else None,
            employee_id=None,  # the client assigns its own operators
            expected_return_at=expected_return_at,
            rental_rate=None,  # falls back to the asset's daily rate
            actor_user_id=actor_user_id,
        )
        db.flush()
        allocated.append(
            AllocatedAsset(
                asset_id=asset.id,
                asset_code=asset.asset_code,
                product_type=product_type.value,
                model=asset.model,
                site_code=target_site.code if target_site else None,
                rental_id=rental.id,
            )
        )

    db.commit()
    db.refresh(client)

    logger.info(
        "Onboarded client %s (%s): %d site(s), %d machine(s)",
        client.name,
        client.code,
        len(created_sites),
        len(allocated),
    )

    return ClientOnboardingResponse(
        client_id=client.id,
        client_name=client.name,
        client_code=client.code,
        login_email=user.email,
        user_id=user.id,
        sites=[OnboardedSite.model_validate(s) for s in created_sites],
        allocated=allocated,
        inventory_after=warehouse_inventory(db),
        expected_return_at=expected_return_at.isoformat(),
    )
