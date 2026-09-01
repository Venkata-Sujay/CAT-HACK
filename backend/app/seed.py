"""Deterministic demo seed.

Run with:  python -m app.seed         (recreates everything)
           python -m app.seed --keep  (only seeds if the DB is empty)

Everything here is driven by a seeded RNG, so the demo behaves identically on
the third rehearsal as on the first. The eight scenes in PROJECT_STATE.md ->
Demo Scenario are engineered to work every run, not to happen by luck.

The scripted anomaly is EQX1007: an Excavator with no site, no operator, zero
runtime and 12 hours of idle. That is lifted verbatim from the row in the
original problem statement -- the demo villain is their own sample data.
"""

import argparse
import logging
import random
import sys
from datetime import timedelta

from sqlalchemy import func, select

from app.core.security import hash_password
from app.database import Base, SessionLocal, engine
from app.models import (
    Asset,
    AssetAssignment,
    AssetEvent,
    AssetStatus,
    Client,
    Employee,
    EventType,
    HealthState,
    ProductType,
    Rental,
    RentalStatus,
    Site,
    TelemetryLog,
    User,
    UserRole,
    WarehouseStatus,
    utcnow,
)

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger("seed")

SEED = 42
DEMO_PASSWORD = "demo1234"  # DEVELOPMENT ONLY. Documented in PROJECT_STATE.md.

rng = random.Random(SEED)

# ---------------------------------------------------------------------------
# Reference data
# ---------------------------------------------------------------------------

# Real coordinates around Telangana, India -- a plausible ~60km operating radius
# for one depot. Real places make the map read as a real deployment.
SITES = [
    {
        "code": "WH-001",
        "name": "Central Equipment Depot",
        "address": "Balanagar Industrial Estate, Hyderabad",
        "latitude": 17.4720,
        "longitude": 78.4380,
        "is_warehouse": True,
    },
    {
        "code": "SITE-001",
        "name": "Northgate Metro Corridor",
        "address": "Medchal, Telangana",
        "latitude": 17.6288,
        "longitude": 78.4810,
        "is_warehouse": False,
    },
    {
        "code": "SITE-002",
        "name": "Bhongir Aggregate Quarry",
        "address": "Bhongir, Yadadri District",
        "latitude": 17.5117,
        "longitude": 78.8853,
        "is_warehouse": False,
    },
    {
        "code": "SITE-003",
        "name": "Patancheru Industrial Park",
        "address": "Patancheru, Sangareddy District",
        "latitude": 17.5300,
        "longitude": 78.2640,
        "is_warehouse": False,
    },
]

CLIENTS = [
    {
        "code": "ACME",
        "name": "Acme Construction Pvt Ltd",
        "email": "client1@demo.local",
        "contact": "ops@acmeconstruction.example",
        "phone": "+91 40 5550 1201",
        "user_name": "Priya Raghavan",
    },
    {
        "code": "NSTAR",
        "name": "Northstar Mining Corp",
        "email": "client2@demo.local",
        "contact": "fleet@northstarmining.example",
        "phone": "+91 40 5550 3382",
        "user_name": "Arun Krishnan",
    },
    {
        "code": "VRTX",
        "name": "Vertex Infrastructure",
        "email": "client3@demo.local",
        "contact": "yard@vertexinfra.example",
        "phone": "+91 40 5550 7745",
        "user_name": "Meera Joshi",
    },
]

OPERATOR_NAMES = [
    "Rahul Sharma", "Vikram Patel", "Sunil Reddy", "Anil Kumar", "Deepak Nair",
    "Ravi Verma", "Manoj Pillai", "Sanjay Gupta", "Kiran Rao", "Ajay Menon",
    "Prakash Iyer", "Nitin Desai", "Rajesh Bhat", "Suresh Naidu", "Harish Kulkarni",
    "Mahesh Chauhan", "Gopal Shetty", "Vinod Prasad",
]

# 50 assets across 5 types.
FLEET_MIX = [
    (ProductType.EXCAVATOR, 14),
    (ProductType.BULLDOZER, 11),
    (ProductType.WHEEL_LOADER, 9),
    (ProductType.CRANE, 8),
    (ProductType.GRADER, 8),
]

MODELS = {
    ProductType.EXCAVATOR: ["CAT 320", "CAT 336", "Komatsu PC210"],
    ProductType.BULLDOZER: ["CAT D6", "CAT D8T", "Komatsu D65"],
    ProductType.CRANE: ["Grove GMK3060", "Liebherr LTM 1050", "Tadano GR-1000"],
    ProductType.GRADER: ["CAT 140M", "CAT 120K", "Volvo G930"],
    ProductType.WHEEL_LOADER: ["CAT 950M", "CAT 966", "Volvo L120"],
}

DAILY_RATE = {
    ProductType.EXCAVATOR: 18500.0,
    ProductType.BULLDOZER: 22000.0,
    ProductType.CRANE: 31000.0,
    ProductType.GRADER: 15500.0,
    ProductType.WHEEL_LOADER: 16800.0,
}

# Which equipment each site actually uses. Drives realistic demand patterns so
# the forecast model has a signal to learn rather than uniform noise.
SITE_PREFERENCE = {
    "SITE-001": [ProductType.EXCAVATOR, ProductType.CRANE, ProductType.WHEEL_LOADER],
    "SITE-002": [ProductType.BULLDOZER, ProductType.EXCAVATOR, ProductType.WHEEL_LOADER],
    "SITE-003": [ProductType.GRADER, ProductType.WHEEL_LOADER, ProductType.EXCAVATOR],
}


def reset_database() -> None:
    logger.info("Dropping and recreating all tables...")
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)


def seed_all(db) -> dict:
    now = utcnow()
    summary: dict = {}

    # ------------------------------------------------------------------
    # Sites
    # ------------------------------------------------------------------
    sites: dict[str, Site] = {}
    for spec in SITES:
        site = Site(
            code=spec["code"],
            name=spec["name"],
            address=spec["address"],
            latitude=spec["latitude"],
            longitude=spec["longitude"],
            is_warehouse=spec["is_warehouse"],
            active=True,
        )
        db.add(site)
        sites[spec["code"]] = site
    db.flush()
    warehouse = sites["WH-001"]
    work_sites = [sites[c] for c in ("SITE-001", "SITE-002", "SITE-003")]
    summary["sites"] = len(sites)

    # ------------------------------------------------------------------
    # Clients + users
    # ------------------------------------------------------------------
    admin = User(
        email="admin@rental.local",
        password_hash=hash_password(DEMO_PASSWORD),
        full_name="Fleet Control Administrator",
        role=UserRole.COMPANY_ADMIN.value,
        client_id=None,
        is_active=True,
    )
    db.add(admin)

    clients: dict[str, Client] = {}
    for spec in CLIENTS:
        client = Client(
            name=spec["name"],
            code=spec["code"],
            contact_email=spec["contact"],
            contact_phone=spec["phone"],
            active=True,
        )
        db.add(client)
        db.flush()
        clients[spec["code"]] = client

        db.add(
            User(
                email=spec["email"],
                password_hash=hash_password(DEMO_PASSWORD),
                full_name=spec["user_name"],
                role=UserRole.CLIENT.value,
                client_id=client.id,
                is_active=True,
            )
        )
    db.flush()
    summary["clients"] = len(clients)

    # ------------------------------------------------------------------
    # Employees (operators) -- 6 per client
    # ------------------------------------------------------------------
    employees: dict[str, list[Employee]] = {code: [] for code in clients}
    name_pool = list(OPERATOR_NAMES)
    rng.shuffle(name_pool)
    counter = 101

    for code, client in clients.items():
        for _ in range(6):
            employee = Employee(
                client_id=client.id,
                employee_code=f"OP-{counter}",
                name=name_pool.pop(),
                phone=f"+91 9{rng.randint(100000000, 999999999)}",
                active=True,
            )
            db.add(employee)
            employees[code].append(employee)
            counter += 1
    db.flush()
    summary["employees"] = sum(len(v) for v in employees.values())

    # ------------------------------------------------------------------
    # Assets -- EQX1001..EQX1050
    # ------------------------------------------------------------------
    assets: list[Asset] = []
    asset_num = 1001
    for product_type, count in FLEET_MIX:
        for _ in range(count):
            code = f"EQX{asset_num}"
            asset = Asset(
                asset_code=code,
                product_type=product_type.value,
                model=rng.choice(MODELS[product_type]),
                serial_number=f"SN{rng.randint(100000, 999999)}",
                status=AssetStatus.AVAILABLE.value,
                warehouse_status=WarehouseStatus.IN_WAREHOUSE.value,
                current_site_id=warehouse.id,
                fuel_level=round(rng.uniform(70, 100), 1),
                tire_condition=HealthState.GOOD.value,
                engine_condition=HealthState.GOOD.value,
                engine_temp_c=round(rng.uniform(28, 35), 1),
                is_running=False,
                latitude=warehouse.latitude + rng.uniform(-0.002, 0.002),
                longitude=warehouse.longitude + rng.uniform(-0.002, 0.002),
                last_seen_at=now,
                qr_token=f"QR-{code}-{rng.randint(4096, 65535):04X}",
                daily_rate=DAILY_RATE[product_type],
                runtime_minutes=rng.randint(20000, 180000),
                idle_minutes=rng.randint(8000, 70000),
            )
            db.add(asset)
            assets.append(asset)
            asset_num += 1
    db.flush()
    summary["assets"] = len(assets)

    by_code = {a.asset_code: a for a in assets}
    by_type: dict[str, list[Asset]] = {}
    for a in assets:
        by_type.setdefault(a.product_type, []).append(a)

    # ------------------------------------------------------------------
    # Historical rentals -- 90 days, for the demand model to learn from
    # ------------------------------------------------------------------
    history_count = 0
    for day_offset in range(90, 3, -1):
        day = now - timedelta(days=day_offset)

        # Weekly cycle: less activity at weekends.
        weekday_factor = 0.45 if day.weekday() >= 5 else 1.0
        # Gentle upward trend across the quarter.
        trend_factor = 0.75 + (90 - day_offset) / 90 * 0.5
        # Occasional demand spike.
        spike = 1.9 if rng.random() < 0.07 else 1.0

        starts = int(round(rng.uniform(1.2, 3.0) * weekday_factor * trend_factor * spike))

        for _ in range(starts):
            site = rng.choice(work_sites)
            preferred = SITE_PREFERENCE[site.code]
            # 80% of the time a site rents equipment it actually favours.
            product_type = rng.choice(preferred) if rng.random() < 0.8 else rng.choice(list(ProductType))

            candidates = by_type.get(product_type.value, [])
            if not candidates:
                continue
            asset = rng.choice(candidates)
            client = rng.choice(list(clients.values()))

            duration = rng.randint(4, 21)
            checkout_at = day
            expected = checkout_at + timedelta(days=duration)
            actual = expected + timedelta(hours=rng.uniform(-18, 30))

            # Historical rentals are all closed -- the "one open rental per
            # asset" invariant must hold before we create the live ones.
            if actual >= now - timedelta(days=3):
                continue

            db.add(
                Rental(
                    asset_id=asset.id,
                    client_id=client.id,
                    site_id=site.id,
                    checkout_at=checkout_at,
                    expected_return_at=expected,
                    actual_return_at=actual,
                    status=RentalStatus.RETURNED.value,
                    rental_rate=asset.daily_rate,
                    checkout_by_user_id=admin.id,
                    checkin_by_user_id=admin.id,
                )
            )
            history_count += 1
    db.flush()
    summary["historical_rentals"] = history_count

    # ------------------------------------------------------------------
    # Live deployment -- 34 of 50 assets out on rental
    # ------------------------------------------------------------------
    # Reserved for scripted demo scenes; excluded from random deployment.
    scripted = {
        "EQX1007",  # Scene 2: the problem-statement anomaly
        "EQX1012",  # unauthorized operator
        "EQX1021",  # overdue
        "EQX1030",  # due soon
        "EQX1008",  # engine warning
        "EQX1014",  # continuous usage
        "EQX1003",  # low fuel
    }

    deployable = [a for a in assets if a.asset_code not in scripted]
    rng.shuffle(deployable)
    to_deploy = deployable[:27]

    active_rentals: list[Rental] = []

    def deploy(
        asset: Asset,
        client: Client,
        site: Site | None,
        operator: Employee | None,
        days_remaining: float,
        runtime_today: int,
        idle_today: int,
        fuel: float,
        tire: HealthState = HealthState.GOOD,
        engine: HealthState = HealthState.GOOD,
        running: bool = True,
        continuous: int = 0,
        reported_operator: Employee | None = None,
    ) -> Rental:
        checkout_at = now - timedelta(days=rng.uniform(3, 20))
        expected = now + timedelta(days=days_remaining)

        rental = Rental(
            asset_id=asset.id,
            client_id=client.id,
            site_id=site.id if site else None,
            checkout_at=checkout_at,
            expected_return_at=expected,
            status=RentalStatus.OVERDUE.value if days_remaining < 0 else RentalStatus.ACTIVE.value,
            rental_rate=asset.daily_rate,
            checkout_by_user_id=admin.id,
        )
        db.add(rental)

        asset.current_client_id = client.id
        asset.current_site_id = site.id if site else None
        asset.warehouse_status = WarehouseStatus.DEPLOYED.value
        asset.status = (
            AssetStatus.OVERDUE.value
            if days_remaining < 0
            else (AssetStatus.ACTIVE.value if running else AssetStatus.IDLE.value)
        )
        asset.runtime_minutes_today = runtime_today
        asset.idle_minutes_today = idle_today
        asset.continuous_runtime_minutes = continuous
        asset.fuel_level = fuel
        asset.tire_condition = tire.value
        asset.engine_condition = engine.value
        asset.is_running = running
        asset.engine_temp_c = round(rng.uniform(74, 88) if running else rng.uniform(28, 40), 1)
        asset.last_seen_at = now - timedelta(minutes=rng.randint(1, 12))

        if site:
            asset.latitude = site.latitude + rng.uniform(-0.004, 0.004)
            asset.longitude = site.longitude + rng.uniform(-0.004, 0.004)

        if operator:
            asset.assigned_employee_id = operator.id
            db.add(
                AssetAssignment(
                    asset_id=asset.id,
                    employee_id=operator.id,
                    client_id=client.id,
                    assigned_at=checkout_at,
                    active=True,
                    assigned_by_user_id=admin.id,
                )
            )

        asset.current_operator_id = (reported_operator.id if reported_operator else (operator.id if operator and running else None))

        db.add(
            AssetEvent(
                asset_id=asset.id,
                client_id=client.id,
                actor_user_id=admin.id,
                event_type=EventType.CHECKOUT.value,
                new_value=AssetStatus.RENTED.value,
                description=f"Checked out to {client.name}" + (f" at {site.code}" if site else ""),
                timestamp=checkout_at,
            )
        )
        active_rentals.append(rental)
        return rental

    client_list = list(clients.values())
    for i, asset in enumerate(to_deploy):
        client = client_list[i % len(client_list)]
        client_code = next(c for c, v in clients.items() if v.id == client.id)
        site = rng.choice(work_sites)
        operator = rng.choice(employees[client_code])

        running = rng.random() < 0.55
        runtime = rng.randint(180, 520) if running else rng.randint(30, 240)
        idle = rng.randint(40, 260)

        deploy(
            asset=asset,
            client=client,
            site=site,
            operator=operator,
            days_remaining=rng.uniform(4, 25),
            runtime_today=runtime,
            idle_today=idle,
            fuel=round(rng.uniform(28, 95), 1),
            tire=HealthState.WARNING if rng.random() < 0.12 else HealthState.GOOD,
            engine=HealthState.WARNING if rng.random() < 0.08 else HealthState.GOOD,
            running=running,
            continuous=rng.randint(0, 180) if running else 0,
        )

    # ------------------------------------------------------------------
    # SCRIPTED DEMO SCENES
    # ------------------------------------------------------------------
    acme = clients["ACME"]
    nstar = clients["NSTAR"]
    vrtx = clients["VRTX"]

    # Scene 2 -- EQX1007. Straight from the problem statement:
    # Excavator, NULL site, 0 engine hours, 12 idle hours, NULL operator.
    deploy(
        asset=by_code["EQX1007"],
        client=acme,
        site=None,            # no site  -> UNASSIGNED_EQUIPMENT
        operator=None,        # no operator -> UNASSIGNED_EQUIPMENT
        days_remaining=6.0,
        runtime_today=0,      # zero runtime -> UNDERUTILIZED
        idle_today=720,       # 12h idle
        fuel=41.0,
        running=False,
    )

    # Scene 3/company -- unauthorized operator on EQX1012.
    # Assigned to one Acme operator, telemetry reports a different one.
    acme_ops = employees["ACME"]
    deploy(
        asset=by_code["EQX1012"],
        client=acme,
        site=work_sites[0],
        operator=acme_ops[0],
        days_remaining=11.0,
        runtime_today=395,
        idle_today=85,
        fuel=63.5,
        running=True,
        continuous=120,
        reported_operator=acme_ops[3],   # <-- the mismatch
    )

    # Scene 6 -- overdue by ~3 days.
    deploy(
        asset=by_code["EQX1021"],
        client=nstar,
        site=work_sites[1],
        operator=employees["NSTAR"][0],
        days_remaining=-3.2,
        runtime_today=210,
        idle_today=180,
        fuel=52.0,
        running=False,
    )

    # Scene 6 -- due soon (inside the 48h window).
    deploy(
        asset=by_code["EQX1030"],
        client=vrtx,
        site=work_sites[2],
        operator=employees["VRTX"][0],
        days_remaining=1.3,
        runtime_today=330,
        idle_today=120,
        fuel=71.0,
        running=True,
        continuous=90,
    )

    # Engine warning.
    deploy(
        asset=by_code["EQX1008"],
        client=nstar,
        site=work_sites[1],
        operator=employees["NSTAR"][1],
        days_remaining=9.0,
        runtime_today=410,
        idle_today=70,
        fuel=44.0,
        engine=HealthState.CRITICAL,
        running=True,
        continuous=240,
    )

    # Continuous usage -- 7.5h uninterrupted, past the 6h review threshold.
    deploy(
        asset=by_code["EQX1014"],
        client=acme,
        site=work_sites[0],
        operator=acme_ops[1],
        days_remaining=14.0,
        runtime_today=470,
        idle_today=30,
        fuel=38.0,
        running=True,
        continuous=450,
    )

    # Low fuel + tire warning.
    deploy(
        asset=by_code["EQX1003"],
        client=vrtx,
        site=work_sites[2],
        operator=employees["VRTX"][1],
        days_remaining=7.0,
        runtime_today=360,
        idle_today=110,
        fuel=12.5,
        tire=HealthState.CRITICAL,
        running=True,
        continuous=180,
    )

    db.flush()
    summary["active_rentals"] = len(active_rentals)

    # A couple of machines held back in maintenance so the inventory view is
    # not uniformly "available".
    for code in ("EQX1045", "EQX1050"):
        asset = by_code.get(code)
        if asset and asset.current_client_id is None:
            asset.status = AssetStatus.MAINTENANCE.value
            asset.warehouse_status = WarehouseStatus.MAINTENANCE.value
            asset.tire_condition = HealthState.WARNING.value
    db.flush()

    # ------------------------------------------------------------------
    # Telemetry history -- 24h at 15-minute intervals, for charts + ML
    # ------------------------------------------------------------------
    deployed_assets = [a for a in assets if a.current_client_id is not None]
    telemetry_rows = 0
    ticks = 96  # 24h / 15min

    for asset in deployed_assets:
        fuel = min(100.0, asset.fuel_level + rng.uniform(10, 30))
        for tick in range(ticks, 0, -1):
            ts = now - timedelta(minutes=15 * tick)
            hour = ts.hour
            within_shift = 6 <= hour < 20

            # EQX1007 is the scripted dead asset: it never runs.
            if asset.asset_code == "EQX1007":
                running = False
            else:
                running = within_shift and rng.random() < 0.6

            burn = rng.uniform(0.8, 1.5) if running else rng.uniform(0.05, 0.15)
            fuel = max(asset.fuel_level, fuel - burn)

            db.add(
                TelemetryLog(
                    asset_id=asset.id,
                    client_id=asset.current_client_id,
                    timestamp=ts,
                    runtime_delta_minutes=15 if running else 0,
                    idle_delta_minutes=0 if running else 15,
                    fuel_level=round(fuel, 1),
                    tire_health=asset.tire_condition,
                    engine_health=asset.engine_condition,
                    engine_temp_c=round(rng.uniform(74, 88) if running else rng.uniform(28, 42), 1),
                    latitude=asset.latitude,
                    longitude=asset.longitude,
                    site_id=asset.current_site_id,
                    current_operator_id=asset.assigned_employee_id if running else None,
                    is_running=running,
                )
            )
            telemetry_rows += 1

    db.commit()
    summary["telemetry_rows"] = telemetry_rows

    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description="Seed deterministic demo data")
    parser.add_argument("--keep", action="store_true", help="Only seed when the database is empty")
    args = parser.parse_args()

    with SessionLocal() as db:
        if args.keep:
            Base.metadata.create_all(engine)
            existing = db.execute(select(func.count(Asset.id))).scalar_one()
            if existing:
                logger.info("Database already has %s assets; nothing to do (--keep).", existing)
                return 0

    reset_database()

    with SessionLocal() as db:
        summary = seed_all(db)

    # Everything below runs after the commit so it reflects the final seeded
    # state. Order matters: rules -> ML anomalies -> forecast -> recommendations,
    # because recommendations are derived from forecast shortfalls.
    from app.ml.anomaly import evaluate_fleet
    from app.ml.forecast import generate_forecasts
    from app.ml.registry import model_registry
    from app.services.recommendation_service import regenerate_all
    from app.services.rules_engine import evaluate_all

    with SessionLocal() as db:
        rule_result = evaluate_all(db)

    # Load the trained artifacts. Missing models are not fatal -- the forecast
    # falls back to a rolling-mean baseline and the ML sweep no-ops, so the demo
    # still works, just with less intelligence.
    model_registry.load()

    ml_result = {"anomalies": 0}
    with SessionLocal() as db:
        try:
            ml_result = evaluate_fleet(db)
        except Exception:  # noqa: BLE001 - seeding must not fail on ML
            logger.warning("  (ML anomaly sweep skipped)")

    # Demo Scenes 7 and 8 need forecasts and recommendations to exist the moment
    # the app boots. Waiting for the simulator's slow refresh cadence would leave
    # the forecasting screen empty for the first few minutes of a presentation.
    forecast_result = {"generated": 0, "source": "n/a"}
    reco_result = {"total": 0}
    with SessionLocal() as db:
        try:
            forecast_result = generate_forecasts(db)
            reco_result = regenerate_all(db)
        except Exception:  # noqa: BLE001
            logger.warning("  (forecast generation skipped)")

    logger.info("")
    logger.info("=" * 62)
    logger.info("  SEED COMPLETE")
    logger.info("=" * 62)
    for key, value in summary.items():
        logger.info("  %-22s %s", key.replace("_", " ") + ":", value)
    logger.info("  %-22s %s", "rule alerts:", rule_result["alerts_raised"])
    logger.info("  %-22s %s", "ML anomalies:", ml_result.get("anomalies", 0))
    logger.info(
        "  %-22s %s (%s)",
        "forecasts:",
        forecast_result.get("generated", 0),
        forecast_result.get("source", "n/a"),
    )
    logger.info("  %-22s %s", "recommendations:", reco_result.get("total", 0))
    logger.info("")
    logger.info("  DEMO LOGINS  (password: %s)", DEMO_PASSWORD)
    logger.info("    admin@rental.local    COMPANY_ADMIN")
    for spec in CLIENTS:
        logger.info("    %-21s CLIENT (%s)", spec["email"], spec["name"])
    logger.info("=" * 62)
    return 0


if __name__ == "__main__":
    sys.exit(main())
