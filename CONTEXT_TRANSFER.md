# Context Transfer — Smart Rental Tracking System

**Paste this whole file as your first message in a new chat.**

---

## Who you are and what this is

You are continuing work on a **completed** hackathon project called the **Smart Rental Tracking
System** — a fleet intelligence platform for construction and mining equipment rentals, built for a
Caterpillar hackathon.

- **Repository:** `C:\Users\venka\CAT_HACK`
- **GitHub:** https://github.com/Venkata-Sujay/CAT-HACK
- **Platform:** Windows 11, PowerShell + Git Bash both available
- **Status:** Phases 1–7 complete and verified. Do **not** rebuild anything.

**Read `PROJECT_STATE.md` in the repo root first.** It is 685 lines and is the single source of truth
for architecture, all design decisions, known debt, and handoff instructions. This file is only a
quick primer so you know what to look for.

---

## What was built

A platform that turns rental telemetry into operational decisions:
`TELEMETRY → PLATFORM → INTELLIGENCE → ACTION`

Two dashboards in one app, split by login role:
- **Company control tower** — whole fleet across all clients: live map, action queue, forecasting,
  inventory, check-in/check-out console
- **Client dashboard** — only that tenant's machines, operators, alerts and recommendations

### Verified numbers (do not inflate these)

| Metric | Value |
|---|---|
| Backend | 35 REST endpoints, 12 DB tables, ~8,500 lines Python |
| Frontend | 14 screens, ~5,500 lines TypeScript |
| Tests | **62 passing, 0 skipped** (24 tenant-isolation, 28 domain, 10 ML) |
| Demo readiness | **28/28 checks** via `backend/verify_demo.py` |
| Anomaly model | IsolationForest — **81.6% detection @ 3.0% false-positive**; precision 58%, recall 82% |
| Forecast model | HistGradientBoosting — **beats 7-day rolling baseline by 27.6% MAE** (0.504 vs 0.697) |
| Demo data | 50 assets, 5 types, 4 sites, 3 client tenants, 18 operators, 34 live rentals |

---

## Tech stack

**Frontend:** React 19 · TypeScript · **Vite 7 (pinned)** · Tailwind CSS · TanStack Query (5s polling)
· React Router 7 · Recharts · Leaflet + OpenStreetMap

**Backend:** Python 3.12 · FastAPI · Uvicorn · Pydantic v2 · SQLAlchemy 2.x · **SQLite**
(PostgreSQL-ready via `DATABASE_URL`) · JWT HS256 + bcrypt

**ML:** scikit-learn · pandas · NumPy · joblib

---

## How to run

```bash
# Backend (simulator autostarts)
cd C:\Users\venka\CAT_HACK\backend
python -m app.seed
python -m uvicorn app.main:app --reload --port 8000

# Frontend
cd C:\Users\venka\CAT_HACK\frontend
npm run dev            # http://localhost:5173

# Verify
cd C:\Users\venka\CAT_HACK\backend
python -m pytest tests/ -q     # expect: 62 passed
python verify_demo.py          # expect: ALL 28 CHECKS PASSED (server must be running)
```

**Logins** (password `demo1234` for all; the login screen has one-click buttons):

| Role | Email |
|---|---|
| Company admin | `admin@rental.local` |
| Client — Acme Construction | `client1@demo.local` |
| Client — Northstar Mining | `client2@demo.local` |
| Client — Vertex Infrastructure | `client3@demo.local` |

**Stopping the backend on Windows** — the process shows as `python3.12.exe`, so bash `pkill -f uvicorn`
does **not** match it. Use:
```powershell
Get-NetTCPConnection -LocalPort 8000 -State Listen | ForEach-Object { Stop-Process -Id $_.OwningProcess -Force }
```

---

## The intelligence layer — 2 ML models + 2 rule engines

**Never describe this as "4 ML models."** It is a deliberate hybrid:

| # | Component | ML? | What |
|---|---|---|---|
| 1 | Anomaly detection | ✅ trained | IsolationForest, unsupervised, 12 features, 250 trees, contamination 0.03 |
| 2 | Demand forecasting | ✅ trained | HistGradientBoostingRegressor, 13 features, time-aware split |
| 3 | Rule engine | ❌ | 8 deterministic rules |
| 4 | Recommendation engine | ❌ | Business logic over forecast + inventory + utilization |

**The reasoning matters and is defensible:** deterministic facts (unauthorized operator, overdue, low
fuel) must never be probabilistic. A missed alert because a model scored 0.51 instead of 0.49 would be
indefensible. Rules own certainties; ML earns only the fuzzy pattern cases.

**Explainability is enforced.** A raw model score is never shown to a user. Each feature is compared to
the training distribution's median/IQR and the top deviations render as sentences. A test fails the
build if any alert lacks reasons + a recommended action.

---

## ⚠️ Seven rules — breaking any of these breaks something

1. **Never reintroduce `passlib`.** passlib 1.7.4 reads `bcrypt.__about__.__version__`, removed in
   bcrypt ≥4.1. It prints a trapped traceback on every hash. We call `bcrypt` directly.

2. **Keep `from app.core.runtime import apply_all` FIRST** in `main.py` and every `ml/*.py`, before
   joblib/sklearn. joblib/loky shells out to `wmic` (absent on this machine) and dumps an
   unsuppressable traceback; `runtime.py` pre-seeds loky's core cache so the probe never runs.

3. **Do not upgrade to Vite 8.** Its rolldown native binding fails to install here (npm/cli#4828) and
   produces a build that cannot run. Pinned to Vite 7 + `@vitejs/plugin-react@4`.

4. **Do not hardcode the ML threshold.** It is computed at training time from the actual score
   distribution and stored in the artifact; inference reads it back. A hardcoded `-0.15` previously
   caused a silent **0% detection rate** because `contamination` offsets the boundary to 0.0.

5. **Do not raise the simulator anomaly probabilities.** Demo mode compresses time ~90×, so the
   brief's suggested 2–5% produced 52 open alerts (a fleet-wide epidemic) in 22 minutes. Current
   values (0.0015 tire / 0.0010 engine) are calibrated from measurement.

6. **`EQX1007` and `EQX1012` are load-bearing for the demo.** EQX1007 is the problem statement's own
   row (kept parked via `SIM_PARKED_ASSET_CODES`); EQX1012 carries the scripted operator mismatch
   (kept alive via `SIM_STICKY_OPERATOR_ASSET_CODES`). Do not "fix" either into normal behaviour.

7. **Do not weaken tenant isolation.** `backend/app/core/deps.py` is the security boundary. New
   endpoints must use `scope_*()` for lists and `get_*_or_404()` for single fetches, and re-verify
   **every** referenced FK on writes. Add an isolation test. Frontend guards are not security.

**After any change to the simulator, rule engine or seed, run `python backend/verify_demo.py`.**
It has already caught two scene-breaking regressions that unit tests did not.

---

## Key files

| Purpose | Path |
|---|---|
| **Architecture + handoff (read first)** | `PROJECT_STATE.md` |
| **Security boundary** ⭐ | `backend/app/core/deps.py` |
| 8 alert rules | `backend/app/services/rules_engine.py` |
| Anomaly ML + explainability ⭐ | `backend/app/ml/anomaly.py` |
| Demand forecasting | `backend/app/ml/forecast.py` |
| Shared feature engineering | `backend/app/ml/features.py` |
| Telemetry simulator | `backend/app/simulator/engine.py` |
| Alert dedup logic | `backend/app/services/alert_service.py` |
| DB models (12 tables) | `backend/app/models/` |
| Demo data generation | `backend/app/seed.py` |
| Security tests ⭐ | `backend/tests/test_tenant_isolation.py` |
| Demo verification | `backend/verify_demo.py` |
| Control tower UI | `frontend/src/pages/company/ControlTower.tsx` |
| Model metrics (auditable) | `ml/artifacts/evaluation_report.json` |

---

## What remains (nothing blocks the demo)

| # | Task |
|---|---|
| 1 | **Rehearse the 8 demo scenes out loud with a timer** — highest value; data is verified, the human run-through is not |
| 2 | Frontend smoke tests (backend has 62, frontend has none) |
| 3 | Alembic squashed initial migration (schema is now stable) |
| 4 | `docker-compose.yml` for the PostgreSQL path |
| 5 | Bundle code-splitting (941 kB / 275 kB gzipped) |
| 6 | Real QR camera scanner (backend endpoint already supports it) |

**Explicitly deferred:** predictive maintenance model, any additional ML. Core demo reliability is
worth more than an extra feature.

---

## Known limitations — state these honestly, never hide them

1. **All model metrics are on SYNTHETIC data.** They measure fit to our own generator, not real-world
   accuracy. This caveat is written into the evaluation report, training scripts, README and UI.
2. **Anomaly precision is 58%** — roughly 4 in 10 ML alerts are false positives. Deliberate: recall
   (82%) was prioritised because a missed unauthorized operator costs far more than a dismissed alert.
3. **SQLite, not PostgreSQL** — Docker was down and Postgres was not installed. Schema is portable;
   one env var switches it.
4. **Single-process simulator** — two API workers would double-tick. Needs a lock for production.
5. **No refresh tokens** — 8h access token only.
6. **No frontend tests.**

---

## Working style that produced this

- Verify by execution, never assume. Three environment landmines and a 0%-detection ML bug were all
  found by running things and measuring, not by reading code.
- Update `PROJECT_STATE.md` at the end of every substantial unit of work. It is the handoff contract.
- When a design decision is non-obvious, record **why** in *Important Design Decisions* — there are
  22 of them and they are the project's strongest asset under questioning.
