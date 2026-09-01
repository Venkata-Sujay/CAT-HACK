# Smart Rental Tracking System

A smart equipment rental tracking platform for construction and mining fleets.

**TELEMETRY → PLATFORM → INTELLIGENCE → ACTION**

Track rented equipment in real time, detect misuse and under-utilization, forecast
what each site will need next, and turn all of it into a prioritized action queue.

> **For AI agents:** [`PROJECT_STATE.md`](PROJECT_STATE.md) is the single source of truth
> for architecture, status and handoff. Read it before changing anything.

---

## Quick start

Two terminals. No Docker required.

### 1. Backend + ML

```bash
cd backend
pip install -r requirements.txt
```

Train the models once (takes about 30 seconds):

```bash
python ml/generate_training_data.py && python ml/train_anomaly_model.py && python ml/train_demand_model.py
```

Seed the deterministic demo dataset:

```bash
cd backend && python -m app.seed
```

Start the API (the telemetry simulator starts with it):

```bash
cd backend && python -m uvicorn app.main:app --reload --port 8000
```

API docs: <http://localhost:8000/docs> · Health: <http://localhost:8000/api/health>

### 2. Frontend

```bash
cd frontend && npm install && npm run dev
```

Open <http://localhost:5173>.

---

## Demo credentials

Development-only passwords for the seeded dataset. The login screen has one-click
buttons for all four.

| Role | Email | Password |
|---|---|---|
| Company admin | `admin@rental.local` | `demo1234` |
| Client — Acme Construction | `client1@demo.local` | `demo1234` |
| Client — Northstar Mining | `client2@demo.local` | `demo1234` |
| Client — Vertex Infrastructure | `client3@demo.local` | `demo1234` |

---

## What is in the box

**Two dashboards, one app.** Login role decides where you land.

- **Company control tower** — fleet KPIs, Leaflet site map, prioritized action queue,
  utilization and forecast charts, check-in/check-out console, inventory, clients.
- **Client dashboard** — only that tenant's equipment, their alerts, their operators,
  their capacity recommendations.

**Seeded scale.** 50 assets (`EQX1001`–`EQX1050`) across 5 equipment types, 3 work
sites plus a depot, 3 client tenants, 18 operators, 131 historical rentals, 34 live
rentals, ~3,300 telemetry readings.

**Hybrid intelligence.**

| Layer | What it owns |
|---|---|
| 8 deterministic rules | unauthorized operator, unassigned equipment, low fuel, tire/engine condition, continuous usage, under-utilization, due-soon, overdue |
| IsolationForest | unusual *combinations* no single threshold catches |
| HistGradientBoosting | 7-day demand forecast per site × equipment type |
| Rule-based recommender | pre-positioning, capacity requests, return-under-utilized |

Deterministic facts stay deterministic. A missed unauthorized-operator alert because a
model scored it 0.51 would be indefensible, so rules own those and ML earns only the
fuzzy cases.

**Every alert explains itself.** No raw model score ever reaches the UI:

```
EQX1007: underutilization detected                              [MEDIUM] [AI]
  · No site is assigned to this machine
  · Idle time today is 414% above the normal range for this fleet
  · Utilization is 100% below the normal range for this fleet
  ACTION: Investigate why the machine is not producing, reassign it, or return it.
```

---

## Model quality

Run `python ml/evaluate_models.py` for the full report.

| Model | Result |
|---|---|
| IsolationForest (anomaly) | **77.0% recall at a 3.0% false-positive rate**; precision 57% |
| HistGradientBoosting (demand) | **beats the 7-day rolling-mean baseline by 27.2% MAE** (0.454 vs 0.623) |

Anomaly recall is reported **per failure mode**, because one aggregate hides the
only useful question — which failures does it actually catch?

| Failure mode | Recall |
|---|---|
| Lost asset (no site, no telemetry) | **100%** |
| Overuse (running through the night) | **100%** |
| Hard failure (degraded parts, collapsed output) | **96%** |
| Dead asset (on hire, producing nothing) | **67%** |
| Unassigned asset (on hire, no site, still reporting) | **53%** |
| Fuel anomaly (near-empty against little work) | **46%** |

An unauthorized operator — a single boolean flip — was detected **0 times out of
96**. IsolationForest measures how easily a point is separated by random
axis-aligned splits, so a row extreme on one of fourteen features barely moves
its score. That is not a defect to hide: it is the measured reason the rule
engine owns single-signal conditions and the model owns the combinations no
threshold describes.

Validation is **time-aware** — trained on the earliest 80% of the timeline, tested on
the most recent 20%. Shuffling a time series would leak the future and inflate the
numbers into meaninglessness.

> **Metrics are computed on synthetic data.** They measure how well each model fits our
> own generator, not real-world accuracy. This is stated in the evaluation report itself
> and should be stated to anyone reviewing the project.

---

## Security

Tenant isolation is enforced in the **backend query layer**, not by hiding UI controls.

- `client_id` comes from the JWT and nowhere else. A client sending `?client_id=2`
  has it **ignored**, not honoured.
- Cross-tenant reads return **404, not 403** — a 403 confirms the resource exists and
  enables ID enumeration.
- Write endpoints re-verify ownership of *every* referenced foreign key, so Client A
  cannot attach their own operator to Client B's excavator.

```bash
cd backend && python -m pytest tests/ -q
```

52 tests: 24 tenant-isolation, 28 domain (auth, checkout, checkin, rule engine,
utilization, dashboards).

---

## Telemetry simulator

Starts automatically with the API. Each tick advances every deployed asset by 15
simulated minutes; in demo mode a tick fires every 10 real seconds.

```
DEMO_TICK_SECONDS=10          # real seconds between ticks
SIMULATED_MINUTES_PER_TICK=15 # simulated asset-time per tick
SIMULATION_SEED=42            # deterministic -> reproducible demo
```

Health degrades monotonically (`GOOD → WARNING → CRITICAL`) and recovers only through
an explicit maintenance action or a check-in inspection. Fuel only falls, except on an
explicit refuel event. Anomaly rates are calibrated so a 20-minute demo produces a
handful of new events, not a fleet-wide epidemic.

`POST /api/simulator/tick` advances the simulation by exactly one interval — useful for
advancing state on cue during a presentation rather than waiting for the timer.

---

## Configuration

Everything is env-overridable via `backend/.env` (see `backend/.env.example`).

| Variable | Default | Purpose |
|---|---|---|
| `DATABASE_URL` | `sqlite:///…/rental.db` | swap to `postgresql+psycopg://…` for Postgres |
| `SECRET_KEY` | dev placeholder | **change for any real deployment** |
| `DEMO_TICK_SECONDS` | `10` | simulator cadence |
| `SIMULATION_SEED` | `42` | reproducibility |
| `CONTINUOUS_USAGE_THRESHOLD_MINUTES` | `360` | operational review guideline |
| `LOW_FUEL_THRESHOLD` | `20.0` | percent |

Threshold note: `CONTINUOUS_USAGE` is a **configurable operational recommendation**, not
a certified machinery safety limit, and the UI says so.

---

## Project layout

```
backend/
  app/
    core/       auth, tenant scoping (deps.py = the security boundary)
    models/     12 SQLAlchemy tables
    routes/     37 REST endpoints across 11 routers
    services/   rule engine, rentals, alerts, telemetry, dashboards, recommendations
    ml/         inference + explainability (features shared with training)
    simulator/  telemetry state machine
    seed.py     deterministic demo data
  tests/        52 tests
ml/
  generate_training_data.py  train_anomaly_model.py
  train_demand_model.py      evaluate_models.py
  artifacts/                 trained models + metadata + evaluation report
frontend/
  src/lib/         api client, auth, TanStack Query hooks, formatters
  src/components/  shell, asset table, alert card, detail drawer, map, charts
  src/pages/       client/ (5 screens) + company/ (9 screens)
```

## Tech stack

React 19 · TypeScript · Vite 7 · Tailwind · TanStack Query · Recharts · Leaflet/OSM
FastAPI · Pydantic v2 · SQLAlchemy 2 · SQLite (Postgres-ready) · JWT + bcrypt
scikit-learn · pandas · numpy · joblib
