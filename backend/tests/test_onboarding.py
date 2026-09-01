"""Client onboarding tests.

Two things are being protected here, and they are different in kind:

  SECURITY  -- the endpoint mints a login. Nothing but a company admin may
               reach it, and no password may ever come back out of it.

  ATOMICITY -- onboarding writes across five tables. A partial success is
               worse than a clean failure, because it leaves a half-created
               tenant that somebody has to unpick by hand. Every rejection
               path is asserted to have written NOTHING.
"""

import pytest
from sqlalchemy import func, select

from app.models import Asset, AssetStatus, Client, Rental, Site, User, WarehouseStatus


def _available(db, product_type: str) -> int:
    return db.execute(
        select(func.count(Asset.id)).where(
            Asset.product_type == product_type,
            Asset.status == AssetStatus.AVAILABLE.value,
            Asset.warehouse_status == WarehouseStatus.IN_WAREHOUSE.value,
        )
    ).scalar_one()


def _payload(**overrides) -> dict:
    body = {
        "name": "Kestrel Civil Works",
        "contact_email": "ops@kestrel.local",
        "login_email": "ops@kestrel.local",
        "login_password": "kestrel-demo-1234",
        "login_full_name": "Anita Menon",
        "sites": [
            {
                "name": "Kestrel Metro Package 3",
                "address": "Nagole, Hyderabad",
                "latitude": 17.37,
                "longitude": 78.56,
            }
        ],
        "equipment": [{"product_type": "CRANE", "quantity": 1}],
        "rental_days": 30,
    }
    body.update(overrides)
    return body


# ---------------------------------------------------------------------------
# Access control
# ---------------------------------------------------------------------------


def test_client_cannot_onboard_another_client(client, client_a_headers):
    """403, not 404: the route's existence is not the secret, the right is."""
    response = client.post("/api/clients", json=_payload(), headers=client_a_headers)
    assert response.status_code == 403


def test_client_cannot_read_depot_availability(client, client_a_headers):
    """Depot stock is company information, not a tenant's."""
    response = client.get("/api/clients/availability", headers=client_a_headers)
    assert response.status_code == 403


def test_anonymous_cannot_onboard(client):
    response = client.post("/api/clients", json=_payload())
    assert response.status_code == 401


# ---------------------------------------------------------------------------
# The happy path, end to end
# ---------------------------------------------------------------------------


def test_onboarding_creates_tenant_login_site_and_rentals(client, admin_headers, db_session):
    before = _available(db_session, "CRANE")
    assert before >= 1, "seed should leave at least one crane in the depot"

    response = client.post("/api/clients", json=_payload(), headers=admin_headers)
    assert response.status_code == 201, response.text
    body = response.json()

    # Tenant + login
    assert body["client_name"] == "Kestrel Civil Works"
    assert body["client_code"]
    assert body["login_email"] == "ops@kestrel.local"

    # Site is on the map, owned by the new tenant
    assert len(body["sites"]) == 1
    site = db_session.execute(
        select(Site).where(Site.code == body["sites"][0]["code"])
    ).scalar_one()
    assert site.client_id == body["client_id"]
    assert site.is_warehouse is False

    # Equipment is checked out, not merely reassigned
    assert len(body["allocated"]) == 1
    allocated = body["allocated"][0]
    asset = db_session.get(Asset, allocated["asset_id"])
    db_session.refresh(asset)
    assert asset.current_client_id == body["client_id"]
    assert asset.current_site_id == site.id
    assert asset.status == AssetStatus.RENTED.value

    rental = db_session.get(Rental, allocated["rental_id"])
    assert rental is not None
    assert rental.client_id == body["client_id"]

    # Inventory really moved
    after = next(
        line["available"] for line in body["inventory_after"] if line["product_type"] == "CRANE"
    )
    assert after == before - 1


def test_onboarded_client_can_log_in_and_sees_only_its_own_fleet(client, admin_headers):
    """The point of the whole feature: the tenant walks away with a working login."""
    payload = _payload(
        name="Halcyon Earthworks",
        login_email="ops@halcyon.local",
        contact_email="ops@halcyon.local",
        equipment=[{"product_type": "GRADER", "quantity": 1}],
        sites=[{"name": "Halcyon Bypass", "latitude": 17.3, "longitude": 78.6}],
    )
    created = client.post("/api/clients", json=payload, headers=admin_headers)
    assert created.status_code == 201, created.text
    allocated_codes = {a["asset_code"] for a in created.json()["allocated"]}

    login = client.post(
        "/api/auth/login",
        json={"email": "ops@halcyon.local", "password": "kestrel-demo-1234"},
    )
    assert login.status_code == 200, login.text
    token = login.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    assert login.json()["user"]["role"] == "CLIENT"

    assets = client.get("/api/assets", headers=headers)
    assert assets.status_code == 200
    visible = {a["asset_code"] for a in assets.json()["items"]}
    assert visible == allocated_codes, "a new tenant must see its own machines and nothing else"

    # And is a client, not an admin.
    assert client.get("/api/clients", headers=headers).status_code == 403


def test_onboarding_response_never_contains_the_password(client, admin_headers):
    payload = _payload(
        name="Ironvale Aggregates",
        login_email="ops@ironvale.local",
        contact_email="ops@ironvale.local",
        login_password="ironvale-secret-99",
        equipment=[],
        sites=[],
    )
    response = client.post("/api/clients", json=payload, headers=admin_headers)
    assert response.status_code == 201, response.text
    assert "ironvale-secret-99" not in response.text
    assert "password" not in response.text.lower()


# ---------------------------------------------------------------------------
# Rejection paths must write nothing
# ---------------------------------------------------------------------------


def test_over_allocation_is_refused_and_writes_nothing(client, admin_headers, db_session):
    """Asking for more than the depot holds fails cleanly, leaving no half-tenant."""
    clients_before = db_session.execute(select(func.count(Client.id))).scalar_one()
    users_before = db_session.execute(select(func.count(User.id))).scalar_one()
    sites_before = db_session.execute(select(func.count(Site.id))).scalar_one()

    payload = _payload(
        name="Overreach Constructions",
        login_email="ops@overreach.local",
        contact_email="ops@overreach.local",
        equipment=[{"product_type": "EXCAVATOR", "quantity": 25}],
    )
    response = client.post("/api/clients", json=payload, headers=admin_headers)
    assert response.status_code == 409
    assert "depot" in response.json()["detail"].lower()

    db_session.expire_all()
    assert db_session.execute(select(func.count(Client.id))).scalar_one() == clients_before
    assert db_session.execute(select(func.count(User.id))).scalar_one() == users_before
    assert db_session.execute(select(func.count(Site.id))).scalar_one() == sites_before


def test_duplicate_login_email_is_refused(client, admin_headers, db_session):
    clients_before = db_session.execute(select(func.count(Client.id))).scalar_one()

    payload = _payload(
        name="Someone Else Entirely",
        login_email="client1@demo.local",  # already belongs to Acme
        contact_email="client1@demo.local",
        equipment=[],
        sites=[],
    )
    response = client.post("/api/clients", json=payload, headers=admin_headers)
    assert response.status_code == 409
    assert "already registered" in response.json()["detail"].lower()

    db_session.expire_all()
    assert db_session.execute(select(func.count(Client.id))).scalar_one() == clients_before


def test_duplicate_client_name_is_refused(client, admin_headers):
    payload = _payload(
        name="acme construction pvt ltd",  # same name, different case
        login_email="ops@notacme.local",
        contact_email="ops@notacme.local",
        equipment=[],
        sites=[],
    )
    response = client.post("/api/clients", json=payload, headers=admin_headers)
    assert response.status_code == 409


@pytest.mark.parametrize(
    "bad",
    [
        {"login_password": "short"},                       # under the minimum length
        {"login_email": "not-an-email"},                   # no @
        {"equipment": [{"product_type": "CRANE", "quantity": 0}]},   # zero units
        {"equipment": [                                    # same type twice
            {"product_type": "CRANE", "quantity": 1},
            {"product_type": "CRANE", "quantity": 1},
        ]},
        {"rental_days": 0},
    ],
)
def test_invalid_payloads_are_rejected(client, admin_headers, bad):
    payload = _payload(
        name=f"Invalid {sorted(bad)[0]}",
        login_email="ops@invalid.local",
        contact_email="ops@invalid.local",
    )
    payload.update(bad)
    response = client.post("/api/clients", json=payload, headers=admin_headers)
    assert response.status_code == 422


def test_depot_availability_matches_the_database(client, admin_headers, db_session):
    response = client.get("/api/clients/availability", headers=admin_headers)
    assert response.status_code == 200
    for line in response.json():
        assert line["available"] == _available(db_session, line["product_type"])
        assert line["available"] <= line["total"]
