"""Test fixtures.

Each test run gets its own throwaway SQLite file. Importantly the tests exercise
the REAL seed data, not a hand-built minimal fixture: the isolation guarantees
must hold against the same 50-asset, 3-tenant dataset the demo runs on, and a
simplified fixture could hide a leak that only appears with real relationships.
"""

import os
import tempfile
from pathlib import Path

import pytest

# Point the app at a temporary database BEFORE any app module is imported --
# config is read at import time.
_TMP_DB = Path(tempfile.gettempdir()) / "rental_test.db"
if _TMP_DB.exists():
    _TMP_DB.unlink()
os.environ["DATABASE_URL"] = f"sqlite:///{_TMP_DB.as_posix()}"
os.environ["SIMULATOR_AUTOSTART"] = "false"
os.environ["SECRET_KEY"] = "test-only-key"

from fastapi.testclient import TestClient  # noqa: E402

from app.database import Base, SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402
from app.seed import seed_all  # noqa: E402

DEMO_PASSWORD = "demo1234"


@pytest.fixture(scope="session", autouse=True)
def seeded_database():
    """Build the full demo dataset once for the whole session.

    Model artifacts are loaded too. The app normally loads them in its lifespan
    handler, which TestClient does not run here -- without this the ML tests
    would silently skip and we would ship untested inference code.
    """
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        seed_all(db)

    from app.ml.registry import model_registry
    from app.services.rules_engine import evaluate_all

    # No-op with a clear warning if the artifacts have not been trained yet;
    # the ML tests skip in that case rather than failing.
    model_registry.load()

    with SessionLocal() as db:
        evaluate_all(db)

    yield

    Base.metadata.drop_all(engine)


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def _login(client: TestClient, email: str) -> str:
    response = client.post("/api/auth/login", json={"email": email, "password": DEMO_PASSWORD})
    assert response.status_code == 200, f"Login failed for {email}: {response.text}"
    return response.json()["access_token"]


def auth_headers(client: TestClient, email: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {_login(client, email)}"}


@pytest.fixture
def admin_headers(client: TestClient) -> dict[str, str]:
    return auth_headers(client, "admin@rental.local")


@pytest.fixture
def client_a_headers(client: TestClient) -> dict[str, str]:
    """Acme Construction."""
    return auth_headers(client, "client1@demo.local")


@pytest.fixture
def client_b_headers(client: TestClient) -> dict[str, str]:
    """Northstar Mining."""
    return auth_headers(client, "client2@demo.local")


@pytest.fixture
def db_session():
    with SessionLocal() as session:
        yield session
