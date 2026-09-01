"""Verify every demo scene is ready, against a RUNNING server.

    python verify_demo.py            # against http://localhost:8000
    python verify_demo.py --url ...  # against another host

Run this immediately before presenting. Each of the eight scenes in
PROJECT_STATE.md -> Demo Scenario is checked through the real HTTP API with real
credentials, so a pass here means the demo path genuinely works -- not that the
database merely contains plausible-looking rows.

Exit code 0 = every scene ready. Non-zero = something would fail on stage.
"""

import argparse
import sys

import httpx

PASSWORD = "demo1234"
ADMIN = "admin@rental.local"
CLIENT_A = "client1@demo.local"   # Acme Construction -- owns EQX1007
CLIENT_B = "client2@demo.local"   # Northstar Mining

GREEN, RED, YELLOW, DIM, RESET = "\033[32m", "\033[31m", "\033[33m", "\033[2m", "\033[0m"

results: list[tuple[bool, str, str]] = []


def check(ok: bool, scene: str, detail: str) -> bool:
    results.append((ok, scene, detail))
    mark = f"{GREEN}PASS{RESET}" if ok else f"{RED}FAIL{RESET}"
    print(f"  [{mark}] {scene}")
    print(f"         {DIM}{detail}{RESET}")
    return ok


def login(client: httpx.Client, base: str, email: str) -> dict[str, str]:
    response = client.post(f"{base}/auth/login", json={"email": email, "password": PASSWORD})
    response.raise_for_status()
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify the demo scenario end to end")
    parser.add_argument("--url", default="http://localhost:8000/api")
    args = parser.parse_args()
    base = args.url.rstrip("/")

    print(f"\n{'=' * 66}")
    print("  DEMO READINESS CHECK")
    print(f"  target: {base}")
    print(f"{'=' * 66}\n")

    with httpx.Client(timeout=20.0) as client:
        # ---- Preflight -------------------------------------------------
        try:
            health = client.get(f"{base}/health").json()
        except Exception as exc:  # noqa: BLE001
            print(f"{RED}Cannot reach the API at {base}{RESET}")
            print(f"  {exc}")
            print("\n  Start it with:  cd backend && python -m uvicorn app.main:app --port 8000")
            return 2

        print(f"{DIM}Preflight{RESET}")
        check(health["database"], "Database reachable", f"status={health['status']}")
        check(
            health["anomaly_model_loaded"],
            "Anomaly model loaded",
            "run: python ml/train_anomaly_model.py" if not health["anomaly_model_loaded"] else "artifact loaded",
        )
        check(
            health["demand_model_loaded"],
            "Demand model loaded",
            "run: python ml/train_demand_model.py" if not health["demand_model_loaded"] else "artifact loaded",
        )
        print()

        admin = login(client, base, ADMIN)
        acme = login(client, base, CLIENT_A)
        northstar = login(client, base, CLIENT_B)

        # ---- Scene 1: company control tower ----------------------------
        print(f"{DIM}Scene 1 -- Company login / control tower{RESET}")
        dash = client.get(f"{base}/dashboard/company", headers=admin).json()
        kpis = dash["kpis"]
        check(
            kpis["total_fleet"] == 50,
            "Fleet of 50 assets",
            f"total_fleet={kpis['total_fleet']}, rented={kpis['rented']}, active={kpis['active']}",
        )
        check(
            len([s for s in dash["sites"] if not s["is_warehouse"]]) >= 3,
            "At least 3 work sites on the map",
            f"{len(dash['sites'])} sites with coordinates",
        )
        check(
            len(dash["action_queue"]) > 0,
            "Action queue is populated",
            f"{len(dash['action_queue'])} open alerts, top = {dash['action_queue'][0]['severity']}",
        )
        print()

        # ---- Scene 2: the EQX1007 anomaly ------------------------------
        print(f"{DIM}Scene 2 -- The scripted anomaly (EQX1007){RESET}")
        assets = client.get(f"{base}/assets?q=EQX1007", headers=admin).json()["items"]
        eqx = assets[0] if assets else None
        check(eqx is not None, "EQX1007 exists", f"found={bool(eqx)}")
        if eqx:
            check(
                eqx["current_site_id"] is None and eqx["assigned_employee_id"] is None,
                "EQX1007 is unaccounted for (no site, no operator)",
                f"site={eqx['site_code']}, operator={eqx['assigned_employee_code']}",
            )
            check(
                eqx["runtime_minutes_today"] == 0 and eqx["idle_minutes_today"] > 300,
                "EQX1007 has zero runtime and high idle",
                f"runtime={eqx['runtime_minutes_today']}min, idle={eqx['idle_minutes_today']}min, "
                f"util={eqx['utilization']:.0%}",
            )
            detail = client.get(f"{base}/assets/{eqx['id']}", headers=admin).json()
            explained = [a for a in detail["alerts"]]
            check(
                len(explained) >= 2,
                "EQX1007 raises multiple explained alerts",
                f"{len(explained)} alerts: {', '.join(a['type'] for a in explained)}",
            )
            alerts = client.get(f"{base}/alerts", headers=admin).json()
            eqx_alerts = [a for a in alerts if a["asset_id"] == eqx["id"]]
            all_explained = all(a["reasons"] and a["recommended_action"] for a in eqx_alerts)
            check(
                all_explained and bool(eqx_alerts),
                "Every EQX1007 alert has reasons + recommended action",
                f"checked {len(eqx_alerts)} alerts -- no bare scores",
            )
        print()

        # ---- Scene 3: tenant isolation ---------------------------------
        print(f"{DIM}Scene 3 -- Tenant isolation{RESET}")
        acme_assets = client.get(f"{base}/assets", headers=acme).json()["items"]
        ns_assets = client.get(f"{base}/assets", headers=northstar).json()["items"]
        acme_ids = {a["id"] for a in acme_assets}
        ns_ids = {a["id"] for a in ns_assets}

        check(
            bool(acme_ids) and bool(ns_ids) and not (acme_ids & ns_ids),
            "Acme and Northstar asset sets do not overlap",
            f"Acme={len(acme_ids)}, Northstar={len(ns_ids)}, shared={len(acme_ids & ns_ids)}",
        )
        if ns_ids:
            victim = next(iter(ns_ids))
            status = client.get(f"{base}/assets/{victim}", headers=acme).status_code
            check(
                status == 404,
                "Cross-tenant asset fetch returns 404 (not 403)",
                f"GET /assets/{victim} as Acme -> {status}",
            )
            ns_client_id = ns_assets[0]["current_client_id"]
            injected = client.get(f"{base}/assets?client_id={ns_client_id}", headers=acme).json()["items"]
            check(
                all(a["current_client_id"] != ns_client_id for a in injected),
                "client_id query param cannot widen scope",
                f"?client_id={ns_client_id} as Acme still returns {len(injected)} own assets only",
            )
        check(
            client.get(f"{base}/clients", headers=acme).status_code == 403,
            "Client cannot enumerate other tenants",
            "GET /clients as a client -> 403",
        )
        acme_sees_eqx = any(a["asset_code"] == "EQX1007" for a in acme_assets)
        check(acme_sees_eqx, "Acme sees its own EQX1007", "the same alert appears on both dashboards")
        print()

        # ---- Scene 4: operator assignment ------------------------------
        print(f"{DIM}Scene 4 -- Employee assignment{RESET}")
        employees = client.get(f"{base}/employees", headers=acme).json()
        check(
            len(employees) >= 3,
            "Acme has registered operators to assign",
            f"{len(employees)} operators on the roster",
        )
        unauth = [a for a in client.get(f"{base}/alerts", headers=admin).json()
                  if a["type"] == "UNAUTHORIZED_OPERATOR"]
        check(
            len(unauth) >= 1,
            "At least one unauthorized-operator alert to resolve on stage",
            f"{len(unauth)} live: {', '.join(a['asset_code'] or '?' for a in unauth[:3])}",
        )
        print()

        # ---- Scene 5: live telemetry -----------------------------------
        print(f"{DIM}Scene 5 -- Live telemetry{RESET}")
        sim = client.get(f"{base}/simulator/status", headers=admin).json()
        check(
            sim["running"],
            "Simulator is running",
            f"tick={sim['tick_count']}, +{sim['simulated_minutes_per_tick']}min per {sim['tick_seconds']}s, "
            f"seed={sim['seed']}",
        )
        before = client.get(f"{base}/simulator/status", headers=admin).json()["tick_count"]
        client.post(f"{base}/simulator/tick", headers=admin)
        after = client.get(f"{base}/simulator/status", headers=admin).json()["tick_count"]
        check(after > before, "Manual [Tick once] advances the simulation", f"tick {before} -> {after}")
        print()

        # ---- Scene 6: deadlines ----------------------------------------
        print(f"{DIM}Scene 6 -- Deadlines{RESET}")
        rentals = client.get(f"{base}/rentals", headers=admin).json()
        overdue = [r for r in rentals if r["status"] == "OVERDUE"]
        due_soon = [
            r for r in rentals
            if r["status"] == "ACTIVE" and r["hours_until_due"] is not None and 0 < r["hours_until_due"] <= 48
        ]
        check(
            len(overdue) >= 1,
            "At least one overdue rental",
            f"{len(overdue)} overdue: {', '.join(r['asset_code'] or '?' for r in overdue[:3])}",
        )
        check(
            len(due_soon) >= 1,
            "At least one due-soon rental",
            f"{len(due_soon)} due within 48h: {', '.join(r['asset_code'] or '?' for r in due_soon[:3])}",
        )
        print()

        # ---- Scene 7: forecast -----------------------------------------
        print(f"{DIM}Scene 7 -- Demand forecast{RESET}")
        forecasts = client.get(f"{base}/forecast", headers=admin).json()
        shortfalls = sorted(
            [f for f in forecasts if f["expected_shortfall"] > 0.5],
            key=lambda f: -f["expected_shortfall"],
        )
        check(len(forecasts) > 0, "Forecasts exist", f"{len(forecasts)} site x type predictions")
        check(
            len(shortfalls) >= 1,
            "At least one predicted shortfall to show",
            (
                f"top: {shortfalls[0]['site_code']} {shortfalls[0]['product_type']} "
                f"need {shortfalls[0]['predicted_demand']:.1f} / have {shortfalls[0]['currently_available']} "
                f"-> shortfall {shortfalls[0]['expected_shortfall']:.1f}"
            )
            if shortfalls
            else "none -- run POST /forecast/regenerate",
        )
        if forecasts:
            check(
                forecasts[0]["model_version"] is not None,
                "Forecast is attributed to a model version",
                f"model_version={forecasts[0]['model_version']}",
            )
        print()

        # ---- Scene 8: recommendations ----------------------------------
        print(f"{DIM}Scene 8 -- Recommendations{RESET}")
        company_recs = client.get(f"{base}/recommendations", headers=admin).json()
        preposition = [r for r in company_recs if r["type"] == "PREPOSITION_ASSET"]
        check(
            len(preposition) >= 1,
            "Company pre-positioning recommendation exists",
            f"{len(preposition)} recs, e.g. \"{preposition[0]['title']}\"" if preposition else "none",
        )
        check(
            all(r["rationale"] for r in company_recs) and bool(company_recs),
            "Every recommendation shows its rationale",
            f"checked {len(company_recs)} recommendations",
        )
        acme_recs = client.get(f"{base}/recommendations", headers=acme).json()
        check(
            all(r["client_id"] in (None, acme_assets[0]["current_client_id"]) for r in acme_recs),
            "Client recommendations are tenant-scoped",
            f"{len(acme_recs)} visible to Acme",
        )

    # ---- Summary -------------------------------------------------------
    passed = sum(1 for ok, _, _ in results if ok)
    total = len(results)
    failed = [(scene, detail) for ok, scene, detail in results if not ok]

    print(f"\n{'=' * 66}")
    if not failed:
        print(f"  {GREEN}ALL {total} CHECKS PASSED -- the demo is ready.{RESET}")
    else:
        print(f"  {RED}{len(failed)} of {total} CHECKS FAILED{RESET}")
        for scene, detail in failed:
            print(f"    {RED}x{RESET} {scene}")
            print(f"      {DIM}{detail}{RESET}")
        print(f"\n  {YELLOW}Try: cd backend && python -m app.seed{RESET}")
    print(f"{'=' * 66}\n")

    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
