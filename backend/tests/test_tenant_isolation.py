"""TENANT ISOLATION TESTS -- the security gate for this project.

Client A must never be able to reach Client B's data through any route, by any
parameter, in any shape. These tests run against the real seeded dataset with
three tenants and 50 assets.

The central assertion is that a cross-tenant fetch returns **404**, not 403: a
403 would confirm the resource exists, which leaks fleet size and valid IDs to
an enumeration attack.
"""

import pytest
from sqlalchemy import select

from app.models import Alert, Asset, Client, Employee, Rental


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _client_by_code(db, code: str) -> Client:
    return db.execute(select(Client).where(Client.code == code)).scalar_one()


def _assets_of(db, code: str) -> list[Asset]:
    client = _client_by_code(db, code)
    return db.execute(select(Asset).where(Asset.current_client_id == client.id)).scalars().all()


# ---------------------------------------------------------------------------
# Read isolation
# ---------------------------------------------------------------------------


def test_client_asset_list_excludes_other_tenants(client, client_a_headers, db_session):
    """Client A's asset list must contain none of Client B's assets."""
    response = client.get("/api/assets", headers=client_a_headers)
    assert response.status_code == 200

    returned_ids = {a["id"] for a in response.json()["items"]}
    assert returned_ids, "Client A should own at least one asset in the demo data"

    b_ids = {a.id for a in _assets_of(db_session, "NSTAR")}
    assert b_ids, "Client B should own assets in the demo data"

    leaked = returned_ids & b_ids
    assert not leaked, f"Client A can see Client B's assets: {leaked}"


def test_client_asset_list_only_contains_own_client_id(client, client_a_headers, db_session):
    acme = _client_by_code(db_session, "ACME")
    response = client.get("/api/assets", headers=client_a_headers)

    for asset in response.json()["items"]:
        assert asset["current_client_id"] == acme.id, (
            f"Asset {asset['asset_code']} belongs to client {asset['current_client_id']}, not Acme"
        )


def test_cross_tenant_asset_detail_returns_404(client, client_a_headers, db_session):
    """THE core security test: fetching B's asset by ID must 404, not 403."""
    b_asset = _assets_of(db_session, "NSTAR")[0]

    response = client.get(f"/api/assets/{b_asset.id}", headers=client_a_headers)
    assert response.status_code == 404, (
        f"Expected 404 for cross-tenant access, got {response.status_code}. "
        "A 403 would confirm the resource exists and enable ID enumeration."
    )


def test_cross_tenant_telemetry_returns_404(client, client_a_headers, db_session):
    b_asset = _assets_of(db_session, "NSTAR")[0]
    response = client.get(f"/api/assets/{b_asset.id}/telemetry", headers=client_a_headers)
    assert response.status_code == 404


def test_cross_tenant_events_returns_404(client, client_a_headers, db_session):
    b_asset = _assets_of(db_session, "NSTAR")[0]
    response = client.get(f"/api/assets/{b_asset.id}/events", headers=client_a_headers)
    assert response.status_code == 404


def test_client_id_query_param_cannot_widen_scope(client, client_a_headers, db_session):
    """A client supplying another tenant's client_id must have it IGNORED.

    This is the parameter-injection case: the scope comes from the token, so a
    hostile query string changes nothing.
    """
    acme = _client_by_code(db_session, "ACME")
    northstar = _client_by_code(db_session, "NSTAR")

    response = client.get(f"/api/assets?client_id={northstar.id}", headers=client_a_headers)
    assert response.status_code == 200

    for asset in response.json()["items"]:
        assert asset["current_client_id"] == acme.id, "client_id query param widened the caller's scope"


def test_employee_list_is_tenant_scoped(client, client_a_headers, db_session):
    response = client.get("/api/employees", headers=client_a_headers)
    assert response.status_code == 200

    acme = _client_by_code(db_session, "ACME")
    returned = {e["id"] for e in response.json()}
    assert returned, "Acme should have employees"

    for employee in response.json():
        assert employee["client_id"] == acme.id

    b_employees = {
        e.id
        for e in db_session.execute(
            select(Employee).where(Employee.client_id == _client_by_code(db_session, "NSTAR").id)
        ).scalars()
    }
    assert not (returned & b_employees)


def test_employee_client_id_filter_ignored_for_clients(client, client_a_headers, db_session):
    """The admin-only client_id filter must be a no-op for a client caller."""
    acme = _client_by_code(db_session, "ACME")
    northstar = _client_by_code(db_session, "NSTAR")

    response = client.get(f"/api/employees?client_id={northstar.id}", headers=client_a_headers)
    assert response.status_code == 200
    for employee in response.json():
        assert employee["client_id"] == acme.id


def test_alerts_are_tenant_scoped(client, client_a_headers, db_session):
    response = client.get("/api/alerts", headers=client_a_headers)
    assert response.status_code == 200

    acme = _client_by_code(db_session, "ACME")
    for alert in response.json():
        assert alert["client_id"] == acme.id


def test_rentals_are_tenant_scoped(client, client_a_headers, db_session):
    response = client.get("/api/rentals", headers=client_a_headers)
    assert response.status_code == 200

    acme = _client_by_code(db_session, "ACME")
    for rental in response.json():
        assert rental["client_id"] == acme.id


def test_client_cannot_enumerate_other_clients(client, client_a_headers):
    """/api/clients is admin-only -- a tenant must not enumerate other tenants."""
    response = client.get("/api/clients", headers=client_a_headers)
    assert response.status_code == 403


# ---------------------------------------------------------------------------
# Write isolation
# ---------------------------------------------------------------------------


def test_cross_tenant_assign_employee_returns_404(client, client_a_headers, db_session):
    """Client A assigning an operator onto Client B's asset must 404."""
    b_asset = _assets_of(db_session, "NSTAR")[0]
    a_employee = db_session.execute(
        select(Employee).where(Employee.client_id == _client_by_code(db_session, "ACME").id)
    ).scalars().first()

    response = client.post(
        f"/api/assets/{b_asset.id}/assign-employee",
        json={"employee_id": a_employee.id},
        headers=client_a_headers,
    )
    assert response.status_code == 404


def test_assigning_other_tenants_employee_to_own_asset_returns_404(client, client_a_headers, db_session):
    """The reverse direction: A's own asset, but B's employee.

    This is the case that a naive implementation misses -- the asset check
    passes, so only re-verifying the employee's tenancy catches it.
    """
    a_assets = _assets_of(db_session, "ACME")
    assert a_assets, "Acme should own assets"
    a_asset = a_assets[0]

    b_employee = db_session.execute(
        select(Employee).where(Employee.client_id == _client_by_code(db_session, "NSTAR").id)
    ).scalars().first()

    response = client.post(
        f"/api/assets/{a_asset.id}/assign-employee",
        json={"employee_id": b_employee.id},
        headers=client_a_headers,
    )
    assert response.status_code == 404


def test_client_cannot_create_site(client, client_a_headers):
    """Admin-only WRITE returns 403 -- the route is not a secret, only data is."""
    response = client.post(
        "/api/sites",
        json={"code": "SITE-999", "name": "Rogue Site", "latitude": 17.0, "longitude": 78.0},
        headers=client_a_headers,
    )
    assert response.status_code == 403


def test_client_cannot_checkout(client, client_a_headers, db_session):
    b_asset = _assets_of(db_session, "NSTAR")[0]
    response = client.post(
        "/api/rentals/checkout",
        json={
            "asset_id": b_asset.id,
            "client_id": _client_by_code(db_session, "ACME").id,
            "expected_return_at": "2030-01-01T00:00:00Z",
        },
        headers=client_a_headers,
    )
    assert response.status_code == 403


def test_client_cannot_acknowledge_other_tenants_alert(client, client_a_headers, db_session):
    northstar = _client_by_code(db_session, "NSTAR")
    b_alert = db_session.execute(select(Alert).where(Alert.client_id == northstar.id)).scalars().first()
    if b_alert is None:
        pytest.skip("No Northstar alert in the seeded data")

    response = client.patch(f"/api/alerts/{b_alert.id}/acknowledge", headers=client_a_headers)
    assert response.status_code == 404


# ---------------------------------------------------------------------------
# Authentication
# ---------------------------------------------------------------------------


def test_missing_token_returns_401(client):
    assert client.get("/api/assets").status_code == 401


def test_malformed_token_returns_401(client):
    response = client.get("/api/assets", headers={"Authorization": "Bearer not-a-real-token"})
    assert response.status_code == 401


def test_tampered_token_returns_401(client, client_a_headers):
    """A token with a flipped payload byte must fail signature verification."""
    token = client_a_headers["Authorization"].split(" ", 1)[1]
    head, payload, signature = token.split(".")
    tampered = f"{head}.{payload[:-4]}AAAA.{signature}"

    response = client.get("/api/assets", headers={"Authorization": f"Bearer {tampered}"})
    assert response.status_code == 401


def test_expired_token_returns_401(client, db_session):
    from app.core.security import create_access_token
    from app.models import User

    user = db_session.execute(select(User).where(User.email == "client1@demo.local")).scalar_one()
    expired = create_access_token(
        user_id=user.id, role=user.role, client_id=user.client_id, expires_minutes=-10
    )
    response = client.get("/api/assets", headers={"Authorization": f"Bearer {expired}"})
    assert response.status_code == 401


def test_login_wrong_password_returns_401(client):
    response = client.post(
        "/api/auth/login", json={"email": "client1@demo.local", "password": "wrong-password"}
    )
    assert response.status_code == 401


def test_login_response_never_contains_password_hash(client):
    response = client.post(
        "/api/auth/login", json={"email": "admin@rental.local", "password": "demo1234"}
    )
    assert response.status_code == 200
    assert "password_hash" not in response.text
    assert "password" not in response.json()["user"]


# ---------------------------------------------------------------------------
# Admin visibility (the other half of the contract)
# ---------------------------------------------------------------------------


def test_admin_sees_all_tenants(client, admin_headers, db_session):
    response = client.get("/api/assets", headers=admin_headers)
    assert response.status_code == 200

    total_assets = db_session.execute(select(Asset)).scalars().all()
    assert response.json()["total"] == len(total_assets) == 50


def test_admin_can_read_any_asset(client, admin_headers, db_session):
    for code in ("ACME", "NSTAR", "VRTX"):
        assets = _assets_of(db_session, code)
        if not assets:
            continue
        response = client.get(f"/api/assets/{assets[0].id}", headers=admin_headers)
        assert response.status_code == 200
