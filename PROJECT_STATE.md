# Smart Rental Tracking System — Project State

> **SINGLE SOURCE OF TRUTH** for collaboration between Claude Code and Codex.
> Every substantial unit of work MUST end with an update to this file.
>
> **Status:** `PHASES 1-8 COMPLETE AND VERIFIED. Backend + ML + simulator + full frontend working end-to-end.`
> **Last updated:** 2026-09-02 by Claude Code (Opus 5) — session 2
> **Tests:** 77 passing, 0 skipped (24 tenant-isolation, 28 domain, 10 ML, 15 onboarding)
> **Demo readiness:** `python backend/verify_demo.py` → **28/28 scene checks pass**
> **Verified in a real browser:** login → control tower → fleet → forecasting → check-in/out round trip → client onboarding → client dashboard

---

## WHAT CHANGED IN SESSION 2 (2026-09-02)

Driven by hackathon judge feedback: *"the UI is confusing for a first-time user"*,
*"demand forecasting doesn't look like it's working"*, and *"three or four polished
outcomes beat six half-baked ones."*

### 1. Two real bugs, both of which made working systems look broken

| Bug | Symptom the judge saw | Root cause | Fix |
|---|---|---|---|
| **Forecast chart froze mid-animation** | Predicted demand of 3.3 rendered as a bar SHORTER than an availability of 1. The table and the chart disagreed, which reads as "the model is broken". | A Recharts `<Bar>` with `<Cell>` children restarts its enter animation on every re-render. These screens poll every 5s, so the bars were permanently caught at ~21% of their true height (measured in the DOM). | `isAnimationActive={false}` on **every** chart. Never re-enable it on a polled chart. |
| **Train/serve skew flooded the action queue** | 39 "critical alerts", 29 of 34 machines flagged. An action queue nobody could use. | The training generator invented its own normal day — 380 min runtime vs 150 idle (72% utilization). The simulator produces a shift-aware Markov duty cycle that accrues idle overnight: ~36% utilization, 3.5x the idle. **The model had never seen the world it was deployed into.** | The generator now runs the SAME state machine as the simulator, with the same probabilities and shift window. See *Design Decision #23*. |

### 2. Demand forecasting: rebuilt, not patched

The model was fine. What was missing was that a "forecast" of one number, seven
days out, is not recognisable as a forecast.

- **Recursive multi-step forecasting.** 14 days instead of 1. Each day's
  prediction feeds the next day's lag features, which is how you run a
  multi-step forecast off a lag-feature regressor — and why accuracy honestly
  degrades with horizon.
- **Projected availability.** Stock is no longer held flat across the horizon.
  Rentals come off hire on known dates, so each day carries the count that will
  actually be on site. This produces the system's most useful sentence: *"you
  have 3 today, two come off hire Thursday, and demand rises to 3.3 on Friday."*
- **`GET /api/forecast/timeline`** returns history and forecast as ONE series
  sharing the point at today, so the chart draws a continuous line across the
  boundary rather than two disconnected ones.
- **Recommendations now name a date.** They fire on the EARLIEST day a
  (site, type) goes short, not the last day of the horizon. "You run short on
  Thursday" is actionable; "you might run short in two weeks" is not.

### 3. Anomaly detection: the metric got worse and the model got better

| | Before | After |
|---|---|---|
| Held-out recall | 81.6% | **77.0%** |
| False-positive rate | 3.0% | 3.0% |
| Live fleet flagged | **29 of 34** | **1-3 of 34** |

The old 81.6% was measured against an unrealistically tidy "normal". Anything
that deviated stood out, including everything the live system does all day. The
new number is lower and the model is usable. Changes:

- **`hours_elapsed_today`** and **`shift_utilization`** added as features.
  40 minutes of runtime at 07:00 is a machine that has just started; the same
  40 minutes at 19:00 is a machine that never worked. Without the elapsed
  context the model cannot tell those apart. `shift_utilization` divides by
  shift minutes rather than clock minutes, so a healthy machine reads ~0.6 at
  ANY hour — this alone took "dead asset" recall from 31% to 47%.
- **`MIN_SCORING_HOURS = 8`.** Machines are not scored until their day is old
  enough to judge. Both training and inference enforce the same floor.
- **Per-failure-mode recall is published**, not just one aggregate. It shows
  exactly what the model is good at (lost asset 100%, overuse 100%, hard
  failure 96%) and what it is not — which is the measured justification for the
  hybrid design rather than an assertion.
- **`unassigned_asset` split out of `lost_asset`.** The combined mode always
  paired "no site" with "no telemetry for hours", so the model learned them as
  one signal — and EQX1007, which reports telemetry perfectly well, was missed
  by 0.0088. See *Design Decision #26*.
- **Alert-storm guard.** A sweep that flags more than 40% of the fleet is
  discarded and logged loudly. A fleet-wide flag rate 13x the calibrated
  false-positive rate is distribution drift, not thirty simultaneous faults.
  Rules keep firing throughout.
- **Explanations are de-duplicated.** `utilization` and `shift_utilization`
  describe the same finding; only the stronger is shown.

### 4. The seeded fleet now shares one clock

`runtime_minutes_today + idle_minutes_today` ranged from 70 to 780 minutes
across the seeded fleet — fifty machines each living in a different hour of the
same day. Nothing surfaced it until the model gained `hours_elapsed_today`.
`SEED_DAY_MINUTES = 18 * 60` now fixes every deployed machine at 18:00, and
idle is DERIVED as `SEED_DAY_MINUTES - runtime`, never passed in.

### 5. UI overhaul

- **Real equipment photography.** Five machine classes plus a hero shot,
  downloaded into `frontend/public/equipment/` (never hotlinked — a demo that
  loses its images to venue WiFi is worse than one that never had them).
  Sources and licences: `frontend/public/equipment/CREDITS.md`.
- **Caterpillar brand system.** CAT yellow `#FFCD11` on warm charcoal, a
  condensed-uppercase label voice, and a hazard-stripe rail reserved for the
  primary panel and critical alerts. `<CatBadge>` probes for
  `/brand/cat-logo.svg` then `.png` and falls back to a built wordmark — drop
  the official asset in and it appears everywhere, zero code change.
- **KPI row: 8 tiles → 4.** The eight-across row truncated every label past the
  fourth ("IN WAREHO…", "CRITICAL A…", "AVG UTILIZ…"). Secondary figures moved
  into a `breakdown` under each headline.
- **Sidebar grouped** into Monitor / Operate / Plan. Nine equally-weighted links
  told a first-time viewer nothing about where to start.
- **Map scroll trap fixed.** Scrolling the control tower used to zoom the map
  instead of the page. `scrollWheelZoom` is off on embedded maps, on for the
  full-page one.
- **Action queue summarised** by type above the cards, so a queue does not read
  as one undifferentiated wall of red.
- **Deep links**: equipment class → filtered fleet, queue chip → filtered
  alerts, shortfall row → that site's timeline.

### 6. NEW FEATURE — client onboarding

`POST /api/clients` creates a tenant, its portal login, its sites and its
opening equipment allocation **in one transaction**. See
`backend/app/services/onboarding_service.py` for why it is one call and not
five, and *Design Decision #24*.

The demo moment: register a client, watch depot stock drop, sign out, sign back
in as the new account, and it sees exactly its own machines and nothing else.
Tenant isolation demonstrated live rather than asserted.

---

## Quick orientation for the next agent

```bash
# 1. Train models (once, ~30s)
python ml/generate_training_data.py && python ml/train_anomaly_model.py && python ml/train_demand_model.py

# 2. Seed + run backend
cd backend && python -m app.seed && python -m uvicorn app.main:app --reload --port 8000

# 3. Run frontend
cd frontend && npm install && npm run dev     # http://localhost:5173

# 4. Verify
cd backend && python -m pytest tests/ -q      # expect: 77 passed
cd backend && python verify_demo.py           # expect: ALL 28 CHECKS PASSED (needs the server running)
```

**Read before editing:** `backend/app/core/deps.py` is the security boundary.
*Important Design Decisions* below explains every non-obvious choice.

### Key files

| Purpose | Path |
|---|---|
| **Security boundary** ⭐ | `backend/app/core/deps.py` |
| 8 alert rules | `backend/app/services/rules_engine.py` |
| Anomaly ML + explainability ⭐ | `backend/app/ml/anomaly.py` |
| Demand forecasting (recursive, projected supply) ⭐ | `backend/app/ml/forecast.py` |
| **Shared feature engineering — training AND serving** ⭐ | `backend/app/ml/features.py` |
| **Training data generator — mirrors the simulator** ⭐ | `ml/generate_training_data.py` |
| Telemetry simulator | `backend/app/simulator/engine.py` |
| Alert dedup logic | `backend/app/services/alert_service.py` |
| **Client onboarding service** ⭐ | `backend/app/services/onboarding_service.py` |
| Onboarding schemas / tests | `backend/app/schemas/onboarding.py`, `backend/tests/test_onboarding.py` |
| DB models (12 tables) | `backend/app/models/` |
| Demo data generation | `backend/app/seed.py` |
| Security tests ⭐ | `backend/tests/test_tenant_isolation.py` |
| Demo verification | `backend/verify_demo.py` |
| Control tower UI | `frontend/src/pages/company/ControlTower.tsx` |
| Forecasting UI | `frontend/src/pages/company/Forecasting.tsx` |
| **Charts — the animation fix lives here** ⭐ | `frontend/src/components/Charts.tsx` |
| Onboarding wizard UI | `frontend/src/components/OnboardClientWizard.tsx` |
| CAT brand mark + logo slot | `frontend/src/components/Brand.tsx` |
| Equipment photo helper | `frontend/src/lib/equipment.ts` |
| Design tokens | `frontend/tailwind.config.js`, `frontend/src/index.css` |
| Model metrics (auditable) | `ml/artifacts/evaluation_report.json` |

> **Stopping the backend on Windows — landmine #4.** Two traps stacked on top
> of each other:
>
> 1. The process appears as `python3.12.exe`, so bash `pkill -f uvicorn` does
>    **not** match it.
> 2. **`uvicorn --reload` spawns its actual server as a `multiprocessing` CHILD.
>    Killing the PID that owns port 8000 kills only the RELOADER.** The child
>    survives, keeps the inherited listening socket, and carries on serving —
>    while `netstat` shows the port owned by a PID that no longer exists and
>    `Get-Process` finds nothing. It looks like a ghost. Four of these
>    accumulated across one session of restarts, all still answering
>    `/api/health` with a healthy simulator.
>
> Kill by COMMAND LINE, not by port:
> ```powershell
> Get-CimInstance Win32_Process |
  Where-Object { $_.CommandLine -like '*uvicorn app.main:app*' -or $_.CommandLine -like '*--multiprocessing-fork*' } |
  ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
> ```
> Then confirm with `netstat -ano | Select-String "LISTENING" | Select-String ":8000"` —
> it must return nothing. A stale entry pointing at a dead PID clears on its own;
> an entry pointing at a LIVE PID means a worker is still up.
>
> The frontend is a normal `node` process and stops cleanly by port.

---

## Environment Audit (verified 2026-09-01 by execution, not assumed)

| Tool | Status | Version |
|---|---|---|
| Node | OK | v20.17.0 (below Vite's preferred 20.19+; warns, works) |
| npm | OK | 10.8.2 |
| Python | OK | 3.12.10 |
| git | OK | 2.46.1.windows.1 |
| Docker CLI | Installed | 27.2.0 |
| **Docker daemon** | **NOT RUNNING** | `dockerDesktopLinuxEngine` pipe not found |
| **PostgreSQL / psql** | **NOT INSTALLED** | `psql: command not found` |
| sqlite3 (stdlib) | OK | 3.49.1 |
| pip network access | OK | reaches PyPI |

**Installed and used:** fastapi 0.136.3, uvicorn 0.48.0, pydantic 2.12.5, pydantic-settings 2.1.0,
SQLAlchemy 2.0.52, alembic 1.19.1, pytest 9.1.1, pandas 2.2.2, numpy 2.0.2, scikit-learn 1.5.2,
joblib 1.4.2, bcrypt 4.3.0, python-jose 3.3.0, httpx 0.28.1.
xgboost 3.2.0 is present but **not used** (Design Decision #6).

### Three environment landmines — all verified, all worked around

1. **`passlib` + `bcrypt 4.3.0` is broken.** passlib reads `bcrypt.__about__.__version__`, removed in
   bcrypt ≥4.1. It returns a correct hash but prints a trapped `AttributeError` traceback on **every**
   hash. → **We call `bcrypt` directly.** passlib is not in `requirements.txt`. Do not reintroduce it.

2. **joblib/loky shells out to `wmic`**, absent on this Windows build. It raises, warns, and calls
   `traceback.print_exc()` straight to stderr — which no `warnings` filter can suppress.
   → `backend/app/core/runtime.py` pre-seeds loky's `physical_cores_cache` so the probe never runs.
   It is imported **first** in `main.py` and in every `ml/*.py`. **Keep that import first**, before
   joblib/sklearn.

3. **Vite 8 / rolldown native binding fails to install** (npm optional-dependency bug npm/cli#4828).
   A fresh `npm install` produced a build that could not run at all. → **Vite is pinned to `^7`**
   (rollup-based, pure JS, no native binary) with `@vitejs/plugin-react@^4`, which is also the
   combination compatible with Node 20.17. Do not upgrade to Vite 8 on this machine.

---

## Current Architecture

```
+----------------------------------------------------------------------+
|  BROWSER                                                             |
|  React 19 + TypeScript + Vite 7 SPA                                  |
|  TanStack Query (5s polling = "realtime") | React Router (guards)    |
|  Tailwind | Recharts | Leaflet/OSM                                   |
+-------------------------------+--------------------------------------+
                                | REST /api/*  (JWT Bearer)
+-------------------------------v--------------------------------------+
|  FastAPI BACKEND                                                     |
|                                                                      |
|  routes/  ->  core/deps (auth + TenantContext)  ->  services/        |
|                          ^                                           |
|         EVERY query passes through tenant scoping. No exceptions.    |
|                                                                      |
|  +-------------+  +--------------+  +----------------------------+   |
|  | Rule Engine |  | ML Inference |  | Telemetry Simulator        |   |
|  | 8 determin- |  | IsolationFor.|  | asyncio task, off-loop     |   |
|  | istic rules |  | + HistGBR    |  | tick=10s -> +15 sim min    |   |
|  +------+------+  +------+-------+  +-------------+--------------+   |
|         +---------+------+                        |                  |
|         HYBRID ALERT ENGINE (dedup'd) <-----------+                  |
+-------------------------------+--------------------------------------+
                                | SQLAlchemy 2.x ORM
+-------------------------------v--------------------------------------+
|  DATABASE - SQLite by default, PostgreSQL via DATABASE_URL           |
|  Portable schema: no JSONB/ARRAY/UUID, enums stored as String        |
+----------------------------------------------------------------------+

ml/artifacts/*.joblib   <- trained offline by scripts, loaded at API startup
```

**Cadences.** Rules run on **every** tick (cheap comparisons; must fire the instant a condition
appears). The ML sweep runs every **6 ticks** (~1 min) — scoring 34 assets through IsolationForest
every 10 seconds would burn CPU re-deriving an answer that barely moves. Forecast + recommendations
refresh every **30 ticks** (~5 min); they describe next week.

---

## Tech Stack

### Frontend
React 19 · TypeScript · **Vite 7 (pinned — landmine #3)** · Tailwind CSS · TanStack Query ·
React Router 7 · Recharts 3 · Leaflet 5 + react-leaflet + OpenStreetMap

**Leaflet/OSM specifically because it needs no API key** — a key wall or quota error would take the
map out of the demo. OSM tiles are bright, so they are CSS-filtered to dark in `index.css` rather
than swapped for a dark tile provider that would require an account.

**shadcn/ui was planned but not used.** The real component needs turned out to be a small set of
~30-line primitives (status chips, fuel bars, KPI tiles, a drawer) in `frontend/src/components/ui.tsx`.
A generator plus Radix was not worth the dependency surface for that. Revisit if a complex
combobox/command-palette is ever needed.

### Backend
FastAPI · Pydantic v2 · SQLAlchemy 2.x · **bcrypt directly (NOT passlib)** · python-jose (JWT HS256)

### Database — SQLite by default, PostgreSQL-ready
Approved deviation from the brief. Docker is down and Postgres is not installed; a demo that cannot
boot is worth zero. Schema uses only portable types. `DATABASE_URL` swaps the engine, no code change.

### Realtime
**Polling, not WebSockets.** `refetchInterval: 5000` on live views, 30s on slow ones. Reconnects for
free, survives a backend restart mid-demo, no socket lifecycle to get wrong.

---

## Database Schema

12 tables. All FKs indexed. `assets.current_client_id` is **the tenant key**.

```
clients --+-- users            (client_id NULL => company role)
          +-- employees
          +-- sites            (client_id NULL => company warehouse)
          +-- assets           (current_client_id  <- THE TENANT KEY)
          +-- rentals
          +-- alerts
          +-- recommendations

assets ---+-- telemetry_logs
          +-- asset_events     (immutable audit trail)
          +-- asset_assignments
          +-- rentals
          +-- alerts

sites  ---+-- forecasts
          +-- recommendations
```

Full column lists live in `backend/app/models/`. Three details are load-bearing rather than incidental:

### `assets` — two operator columns
```
assigned_employee_id   = who is AUTHORISED to operate   (set by the client)
current_operator_id    = who telemetry REPORTS is operating (simulated RFID / cab login)
```
**The disagreement between them IS the UNAUTHORIZED_OPERATOR signal.** `Asset.operator_match` returns
True when no operator is reported — a parked machine with nobody in the cab is not a violation.

### `alerts.dedupe_key` — prevents a simulator-driven flood
An alert is identified by `{asset_id}:{type}`. While OPEN or ACKNOWLEDGED the key is set and unique,
so re-firing **updates** the row instead of inserting. On RESOLVED the key is set to **NULL**, freeing
the pair to alert again legitimately later.

This exploits a portable SQL behaviour: **a UNIQUE index permits multiple NULLs in both SQLite and
PostgreSQL.** That gives a partial unique index with no dialect-specific DDL. Without it a 10-second
tick inserts thousands of duplicate LOW_FUEL rows within minutes and the action queue is unusable.

### `alerts.reasons` (JSON) + `recommended_action`
First-class columns, not an afterthought. An alert that cannot explain itself is not actionable, and
`test_every_alert_is_explainable` enforces that **every** alert carries both.

---

## API Endpoints

**All 35 implemented, registered and exercised.** `[C]` client-scoped · `[A]` admin-only · `[CA]` both

| Method | Path | Role | Purpose |
|---|---|---|---|
| POST | `/api/auth/login` | public | JSON login → JWT |
| POST | `/api/auth/token` | public | OAuth2 form login (Swagger "Authorize") |
| GET | `/api/auth/me` | any | current user + role + client |
| GET | `/api/assets` | [CA] | list; filters status/product_type/site_id/q |
| GET | `/api/assets/{id}` | [CA] | detail + embedded alerts |
| GET | `/api/assets/{id}/telemetry` | [CA] | time series, `?hours=24` |
| GET | `/api/assets/{id}/events` | [CA] | audit trail |
| POST | `/api/assets/{id}/assign-employee` | [CA] | assign operator |
| DELETE | `/api/assets/{id}/assign-employee` | [CA] | unassign |
| POST | `/api/assets` | [A] | add asset (auto EQX code + QR token) |
| PATCH | `/api/assets/{id}/maintenance` | [A] | `?active=`; ending restores health to GOOD |
| GET | `/api/sites` | [CA] | sites + deployed/active/idle/anomaly counts |
| POST | `/api/sites` | [A] | add site |
| GET | `/api/sites/{id}/assets` | [CA] | assets at a site |
| GET | `/api/clients` | [A] | tenants + rollups |
| **POST** | **`/api/clients`** | **[A]** | **onboard a client: tenant + login + sites + opening fleet, one transaction** |
| **GET** | **`/api/clients/availability`** | **[A]** | **depot stock per equipment type — the wizard's allocation ceiling** |
| GET | `/api/employees` | [CA] | operators (+ current assignment) |
| POST | `/api/employees` | [CA] | register operator |
| PATCH | `/api/employees/{id}` | [CA] | edit / deactivate |
| GET | `/api/rentals` | [CA] | list, `?status=` |
| GET | `/api/rentals/overdue` | [CA] | overdue only |
| POST | `/api/rentals/checkout` | [A] | asset+client+site+employee+due date |
| POST | `/api/rentals/checkin` | [A] | close rental, condition, → warehouse |
| GET | `/api/rentals/lookup/{code}` | [A] | **asset_code OR qr_token** → asset + rental + operators |
| POST | `/api/telemetry` | [A] | external tick ingest |
| GET | `/api/alerts` | [CA] | filters severity/type/status; severity-ordered in SQL |
| PATCH | `/api/alerts/{id}/acknowledge` | [CA] | ack |
| PATCH | `/api/alerts/{id}/resolve` | [CA] | resolve |
| GET | `/api/forecast` | [CA] | `?site_id=&product_type=&horizon=` window, or `&day=` for one horizon day |
| **GET** | **`/api/forecast/timeline`** | **[CA]** | **history + forecast as ONE continuous series for a site+type** |
| POST | `/api/forecast/regenerate` | [A] | re-run model + recommendation rules |
| GET | `/api/recommendations` | [CA] | scoped |
| POST | `/api/recommendations/{id}/request` | [C] | "Request More Assets" |
| PATCH | `/api/recommendations/{id}/dismiss` | [CA] | dismiss |
| GET | `/api/dashboard/client` | [C] | one aggregate: KPIs+assets+alerts+charts+recs |
| GET | `/api/dashboard/company` | [A] | one aggregate: KPIs+sites+queue+charts+forecast |
| GET | `/api/simulator/status` | [A] | tick count, sim clock |
| POST | `/api/simulator/start\|stop\|tick` | [A] | **`/tick` advances one interval on cue** |
| GET | `/api/health` | public | DB + both model-loaded flags + simulator state |

**Why one aggregate endpoint per dashboard:** the UI polls every 5s. Seven parallel requests per poll
would hammer the API for nothing, and a single response guarantees every tile reflects the same instant.

---

## Frontend Routes / Screens

All 14 screens built. Login → role-based redirect. Guards in `src/App.tsx`.

### CLIENT (`/client/*`)
| Route | Screen |
|---|---|
| `/client` | **Overview** — 6 KPIs, top recommendation, my-assets table, alerts panel, 2 charts |
| `/client/assets` | **My Assets** — filterable table → asset drawer |
| `/client/employees` | **Operators** — list, add, activate/deactivate |
| `/client/alerts` | **Alerts** — severity-grouped |
| `/client/recommendations` | **Recommendations** — open + actioned, `[Request more assets]` |

### COMPANY (`/company/*`)
| Route | Screen |
|---|---|
| `/company` | **Control Tower** — 8 KPIs · map + action queue · 3 charts · simulator controls |
| `/company/map` | **Map & Sites** — full map, site list, `[Add site]` |
| `/company/fleet` | **Fleet** — all assets, all filters, deep-linkable `?site=<id>` |
| `/company/inventory` | **Inventory** — stock by type with totals row, `[Add asset]` |
| `/company/rentals` | **Rentals** — Active / Overdue / Returned / All tabs |
| `/company/checkinout` | **Check-In / Out** — scan console, auto-switches in/out |
| `/company/clients` | **Clients** — tenant cards + table, `[+ Register client]` → onboarding wizard |
| `/company/alerts` | **Action queue** — severity-grouped, filterable |
| `/company/forecasting` | **Forecasting** — headline finding, history→forecast timeline, gap chart, first-day-short table, pre-positioning recs |

**Shared:** `AssetDetailDrawer` — right slide-over, tabs Overview / Telemetry / Alerts / History.
A drawer rather than a route so clicking through an action queue never loses table scroll or filters.

**Deep links.** Equipment class → `/company/fleet?type=<PRODUCT_TYPE>` ·
action-queue chip → `/company/alerts?type=<ALERT_TYPE>` · map marker →
`/company/fleet?site=<id>` · shortfall row → that site+type on the timeline.
Filters read from the URL on mount and write back on change, so any view is
shareable.

**New components (session 2)**

| Component | Purpose |
|---|---|
| `components/Brand.tsx` | `<CatBadge>` (probes for the official logo, falls back to a built wordmark) and `<CatCorner>` |
| `components/FleetStrip.tsx` | Five photo cards, one per machine class, with a deployed/depot/workshop bar. Also `<EquipmentBanner>` |
| `components/OnboardClientWizard.tsx` | Three-step new-client registration, capped by real depot stock |
| `lib/equipment.ts` | `equipmentImage(type, "card" \| "thumb")` and the type blurbs |

---

## ML Models and Features

### Model 1 — Anomaly Detection (IsolationForest)

**Verified: 77.0% detection at 3.0% false-positive rate. Precision 56.8%, F1 0.654.**

Recall is published **per failure mode**, because one aggregate number hides the
only thing worth knowing — which failures the model actually catches:

| Failure mode | Recall | What it is |
|---|---|---|
| `lost_asset` | **100%** | no site AND no telemetry for hours |
| `overuse` | **100%** | running through the night, barely stopping |
| `hard_failure` | **96%** | degraded engine/tire with collapsed output |
| `dead_asset` | **67%** | on hire, producing nothing |
| `unassigned_asset` | **53%** | on hire, no site, still reporting — the EQX1007 pattern |
| `fuel_anomaly` | **46%** | nearly empty against very little work done |

**These numbers replaced an earlier 81.6%, and the drop is the point.** The old
figure was measured against a training distribution that did not resemble the
running system (see *Session 2* above). It scored well on a world that did not
exist, and flagged 29 of 34 live machines. The current model scores 1-3.

**Why single-feature anomalies score at chance.** IsolationForest measures how
easily a point is separated by random axis-aligned splits. A row that is extreme
on ONE of fourteen features barely moves its average path length — the deviation
is diluted by the thirteen ordinary ones. Measured directly: an unauthorized
operator, which is a single boolean flip, was detected **0 times out of 96**.

That is not a defect to hide. It is the measured justification for the hybrid
design: single-signal conditions belong to the rule engine, which catches them
with certainty; the model earns the combinations no threshold describes.

**Why unsupervised:** we have no labelled misuse data. Labelling our own synthetic anomalies and then
"detecting" them would be circular reasoning dressed as ML. The model is trained on the **normal
subset only** (11,414 rows); the 586 injected anomalies are withheld purely to verify separation.

**14 features**, defined once in `backend/app/ml/features.py` and imported by **both** training and
inference. Separate definitions would drift and the model would silently score garbage.

Two were added in session 2 and both exist to give the model TIME CONTEXT:

- **`hours_elapsed_today`** = `(runtime + idle) / 60`. Forty minutes of runtime at
  07:00 is a machine that has just started; the same forty minutes at 19:00 is a
  machine that never worked. Derived from existing counters, so it needs no new
  data source on either side.
- **`shift_utilization`** = `runtime / shift_minutes_elapsed`, capped at 1.0.
  Plain `utilization` divides by the whole elapsed day including the night, so a
  healthy machine reads 0.16 at 08:00 and 0.44 at 20:00 — and a genuinely dead
  machine at 08:00 lands inside that range. Dividing by shift minutes only makes
  a healthy machine read ~0.6 at ANY hour. Turning a conditional into a flat one
  took `dead_asset` recall from 31% to 47%.

**Assets are not scored before `MIN_SCORING_HOURS` (8h) of their day has
elapsed.** Before then a stopped machine and a dead machine are indistinguishable
and scoring anyway flags the fleet. The training generator applies the identical
floor; changing one without the other reintroduces the skew.

**The threshold is CALIBRATED, not hardcoded.** `IsolationForest.decision_function` is offset by its
`contamination` parameter, so the natural boundary is 0.0 — not a hand-picked negative number. An
earlier hardcoded `-0.15` produced a **0% detection rate** because no score ever reached it. Training
now computes the threshold and severity bands from the actual score distribution and writes them into
the artifact; inference reads them back. Retraining recalibrates automatically.

**Explainability.** Each feature is compared to the training distribution's **median and IQR** —
robust statistics, because telemetry is skewed and a few 20-hour days would drag a mean far enough to
make ordinary assets look anomalous. Top deviations render as sentences:

```
EQX1007: underutilization detected                              [MEDIUM] [AI]
  · No site is assigned to this machine
  · Idle time today is 414% above the normal range for this fleet
  · Utilization is 100% below the normal range for this fleet
  ACTION: Investigate why the machine is not producing, reassign it, or return it.
```

**A raw model score is never rendered.** Enforced by `test_explanations_are_natural_language`.

### Model 2 — Demand Forecasting (HistGradientBoostingRegressor)

**Verified: beats the 7-day rolling-mean baseline by 27.2% MAE** (0.4537 vs 0.6233; RMSE 0.656 vs 0.901).

**The forecast is RECURSIVE, not single-shot.** The model's strongest features
are lags (`prev_day_demand`, `rolling_7d_mean`, `rolling_30d_mean`). To predict
day D+3 you need day D+2, which you do not have — so each prediction is appended
to the working series and feeds the next day's features. This is the standard way
to run a multi-step forecast off a lag-feature regressor, and it is why accuracy
honestly degrades with horizon: errors compound.

**Availability is PROJECTED, not frozen.** A site's stock is not constant.
Rentals come off hire on known dates and those machines go back to the depot, so
each forecast day carries the count that will actually be on site that day.
Holding it flat would hide the single most useful thing the system says: *"you
have 3 today, two come off hire Thursday, and demand rises to 3.3 on Friday."*

Top drivers by permutation importance: `rolling_30d_mean` (+0.35), `day_of_week` (+0.30),
`prev_week_demand` (+0.10) — exactly the level and weekly-cycle structure injected into the generator,
which is a good sanity check that it learned real signal rather than noise.

**Time-aware split**: trained on the earliest 80% of the timeline, tested on the most recent 20%.
Shuffling a time series leaks the future and inflates metrics into meaninglessness.

**The baseline is published, not hidden.** If the model ever loses to a rolling average, the training
script says so in plain language rather than quietly shipping.

**Graceful degradation:** with no artifact, `generate_forecasts` falls back to the rolling-mean
baseline and reports `source: "baseline-rolling-7d"`. The forecasting screen still works.

### Model 3 — Recommendation Engine (rules, deliberately not ML)

Composes forecast + inventory + utilization. A learned recommender on synthetic data would be
unexplainable and untrustworthy; these rules state exactly why they fired.

- `PREPOSITION_ASSET` — forecast shortfall at a site + spare warehouse stock of that type
- `REQUEST_MORE_ASSETS` — client fleet utilization above 85% for a product type
- `RETURN_UNDERUTILIZED` — rented machine below 10% utilization over a meaningful window

### Training pipeline
```
ml/generate_training_data.py  -> ml/data/*.csv          (12,000 anomaly rows, 3,945 demand rows)
ml/train_anomaly_model.py     -> anomaly_model.joblib   (2.9 MB) + metadata
ml/train_demand_model.py      -> demand_model.joblib    (519 KB) + metadata
ml/evaluate_models.py         -> evaluation_report.json
```
Every artifact carries `trained_at`, `feature_list`, `training_rows`, `metrics`, `model_version`.

> **HONESTY REQUIREMENT.** All metrics are computed on SYNTHETIC data. They measure fit to our own
> generator, **not** real-world accuracy. The caveat is embedded in the evaluation report, the training
> scripts, the README and the forecasting screen. **Do not present these numbers as evidence of
> production accuracy.** Stating it plainly reads as rigour; overselling it is the fastest way to lose
> a technical reviewer.

---

## Simulator

`asyncio` background task started in the FastAPI lifespan. The tick body runs via `asyncio.to_thread`
so synchronous SQLAlchemy work never blocks the event loop serving requests.

```
DEMO_TICK_SECONDS=10          # real seconds between ticks
SIMULATED_MINUTES_PER_TICK=15 # simulated asset-time per tick
SIMULATION_SEED=42            # deterministic -> reproducible demo
SIMULATOR_AUTOSTART=true
SIM_PARKED_ASSET_CODES=EQX1007
SIM_STICKY_OPERATOR_ASSET_CODES=EQX1012
```

Per-tick state machine: shift-aware (06:00–20:00 simulated), plausible RUNNING↔IDLE transitions,
fuel only falls except on an explicit refuel event, engine temp tracks load, position drifts ~10–50 m.

### Anomaly rates were RECALIBRATED from observed behaviour

The brief suggested 2–5% tire degradation per tick. **That produced a fleet-wide epidemic.** After
22 real minutes (134 ticks) the fleet had **52 open tire/engine alerts and 57 criticals** — an action
queue nobody could use.

The cause is time compression, and it matters before touching these numbers: **demo mode compresses
time ~90×.** 22 real minutes = **34 simulated hours**. At p=0.03 only 13% of assets survive 134 ticks
undegraded. Health is deliberately monotonic, so degradation accumulates and never washes out.

| Probability | Was | Now | Reason |
|---|---|---|---|
| `SIM_TIRE_DEGRADE_PROB` | 0.03 | **0.0015** | ~4 new events per 150-tick demo |
| `SIM_ENGINE_DEGRADE_PROB` | 0.02 | **0.0010** | ~2.5 new events |
| `SIM_OPERATOR_MISMATCH_PROB` | 0.025 | **0.005** | higher because it AUTO-RESOLVES — self-limiting |
| `SIM_UNEXPECTED_INACTIVITY_PROB` | 0.01 | **0.004** | |

**Verified after a 4-minute run: 48/50 assets GOOD on both tire and engine, 12 open alerts total.**

**Parked assets.** `SIM_PARKED_ASSET_CODES` lists machines the simulator keeps idle. `EQX1007` is
there because it is the scripted Demo Scene 2 anomaly — without it the simulator would start running
it within a minute or two, its UNDERUTILIZED alert would auto-resolve, and the scene would silently
vanish partway through a presentation. It also models a real situation: equipment rented, forgotten,
and accruing cost while producing nothing.

**Sticky operators.** `SIM_STICKY_OPERATOR_ASSET_CODES` lists machines where the simulator keeps
reporting whoever telemetry last saw in the cab, instead of re-rolling each tick. `EQX1012` is there
for Demo Scene 4: it is seeded with a deliberate mismatch, and without stickiness the simulator
reassigned the correct operator within a tick or two, auto-resolving the CRITICAL alert before it
could be shown. (A `verify_demo.py` run caught exactly this.)

This models reality — the same unauthorized person keeps operating the machine until somebody
intervenes — and the scene's payoff still works: assigning the operator who is ACTUALLY in the cab
makes `assigned == reported` and the alert resolves for good, with both actions written to the audit
trail. **Verified end to end.**

**Why UNAUTHORIZED_OPERATOR does not auto-resolve when a machine stops:** it records a security
*event*, not a live gauge. An unauthorized-access finding should not silently disappear because the
person climbed out of the cab. It clears when the assignment is corrected, or when a human resolves it.

---

## Authentication and Security

JWT HS256, 8h token, bcrypt cost 12 (**direct bcrypt, never passlib**).

### Tenant isolation — enforced in the query layer

`backend/app/core/deps.py` is the boundary. Everything goes through it.

```python
class TenantContext:
    user: User
    client_id: int | None   # None => company role, sees everything
    is_admin: bool

def scope_assets(stmt, ctx):
    return stmt if ctx.is_admin else stmt.where(Asset.current_client_id == ctx.client_id)
```

1. **`client_id` comes from the JWT and nowhere else.** A client sending `?client_id=2` has it
   **ignored**, not honoured. Verified by `test_client_id_query_param_cannot_widen_scope`.
2. Scope is derived from the **database user row**, not the token claim, so a tenancy change takes
   effect immediately rather than at token expiry.
3. Every list query goes through `scope_*()`; every single fetch through `get_*_or_404()`, which
   applies the tenant filter **inside** the lookup.
4. **Cross-tenant reads return 404, not 403.** A 403 confirms the resource exists, leaking fleet size
   and valid IDs to enumeration. 403 is reserved for *route-level* permission (a client calling an
   admin route), where the route's existence is not a secret.
5. Write endpoints re-verify ownership of **every** referenced FK. Checking only the primary object
   leaves the reverse direction open — see `test_assigning_other_tenants_employee_to_own_asset_returns_404`,
   which is precisely the case a naive implementation misses.

**Frontend route guards are a UX convenience, NOT the security boundary.** Hiding a nav link protects
nothing; the API is the boundary.

### Test coverage (24 isolation tests, all passing)
Cross-tenant asset / telemetry / events / assign → **404** · employee, alert and rental list scoping ·
`client_id` param injection ignored · client→admin route → **403** · missing / malformed / tampered /
expired token → **401** · login response never contains `password_hash` · admin sees all 50 assets.

---

## Completed

### Phase 1 — Foundation + tenant security ✅
`config.py` (every threshold env-overridable) · `database.py` (SQLite `foreign_keys=ON` + WAL) ·
12 SQLAlchemy models · `core/security.py` (direct bcrypt + JWT) · `core/deps.py` (TenantContext,
scope helpers, scoped 404 fetchers) · `core/runtime.py` (loky probe fix).
**Gate met: 24/24 isolation tests pass.**

### Phase 2 — Domain API + seed ✅
35 endpoints across 11 routers · N+1-free asset serialisation (~6 queries regardless of fleet size) ·
checkout/checkin with audit trail · QR-or-code lookup · deterministic seed
(50 assets / 5 types / 4 sites / 3 clients / 18 operators / 131 historical + 34 active rentals /
3,264 telemetry rows). The seed also generates alerts, ML anomalies, forecasts and recommendations,
so the demo is complete the moment it finishes.

### Phase 3 — Rule engine + alerts ✅
8 self-clearing rules · dedup via NULL-able unique key · severity ordering in SQL ·
maintenance assets excluded from health alerts (they are in the workshop *because* they are degraded).

### Phase 4 — Simulator ✅
Seeded, shift-aware, monotonic health, refuel events, parked assets, manual tick endpoint,
recalibrated anomaly rates, ML and forecast on slower cadences.

### Phase 5 — ML ✅
Data generation · IsolationForest (77.0%/3.0% after the session-2 retrain) · HistGBR (+27.2% vs baseline) · evaluation report ·
median/IQR explainability · graceful degradation when artifacts are missing · shared feature module.

### Phase 6-7 — Frontend ✅
Design system + 14 screens + shared components · typed API client · TanStack Query polling ·
Leaflet map with live data in the markers · Recharts throughout · loading/empty/error states
everywhere. **Verified in a real browser end-to-end.**

### Phase 8 — Judge feedback pass ✅ (session 2)
Two bugs that made working systems look broken (frozen forecast bars, train/serve
skew) · demand forecasting rebuilt as a recursive 14-day timeline with projected
availability · anomaly model retrained against the simulator's real distribution,
with per-mode recall published · Caterpillar brand system and real equipment
photography across every screen · KPI rows cut from 8 tiles to 4 · sidebar
grouped · map scroll trap fixed · client onboarding built end to end with 15 new
tests. **77 tests, 28/28 demo checks, verified in a browser.**

## In Progress

Nothing. The system is in a working, demonstrable state.

## Remaining

Ordered by value. Nothing here blocks the demo.

| # | Task | Notes |
|---|---|---|
| 1 | **Rehearse the demo out loud, with a timer** | `verify_demo.py` proves the DATA and API support every scene (28/28). What remains is the human run-through: narration, pacing, screen order. There are now **9 scenes** — client onboarding is the new one, and it is the strongest, because it demonstrates tenant isolation live instead of asserting it. |
| 1b | **Drop the official CAT logo into `frontend/public/brand/`** | `cat-logo.svg` or `cat-logo.png`. Zero code change; the built fallback wordmark is showing until you do. See that folder's README. |
| 2 | Frontend smoke tests (Vitest/Playwright) | Backend has 77 tests; frontend has none. The forecast-chart animation bug is exactly the class a render test would have caught. |
| 3 | Alembic squashed initial migration | Scaffolding exists; the schema is now stable enough to freeze. |
| 4 | `docker-compose.yml` for the Postgres path | Only useful once the Docker daemon runs. |
| 5 | Bundle code-splitting | 941 kB / 275 kB gzipped. Fine for a demo, not production. |
| 6 | Real QR camera scanner | Nice-to-have; the simulated path already exercises the same endpoint. |
| 7 | Predictive maintenance model | Explicitly deferred — do not start before 1-3. |

## Known Bugs / Technical Debt

Accepted, deliberate trade-offs — recorded up front so nobody "discovers" them later.

1. **SQLite, not PostgreSQL, by default.** Environment-forced. Portable schema + `DATABASE_URL` swap.
2. **Alembic scaffolded but not the reset path.** `create_all` + seed during iteration. Task #3.
3. **No refresh tokens.** 8h access token. Right scope for a hackathon, wrong for production.
4. **Polling, not WebSockets.** 5s latency is invisible; robustness is worth more.
5. **Enums stored as `String`.** Portability over DB-level constraint; Python `Enum` validates on entry.
6. **Synthetic training data.** Metrics measure fit to our own generator. State it, never oversell it.
7. **Single-process simulator.** Two API workers would double-tick. Needs a lock for real deployment.
8. **Frontend bundle is 941 kB** (275 kB gzipped) — Leaflet + Recharts, not code-split.
9. **No frontend tests.** Task #2. Note that the one visual bug that reached a
   judge — the frozen forecast bars — was invisible to every backend test and to
   `verify_demo.py`, because the API was returning correct numbers the whole
   time. It was found by measuring rendered bar heights in the DOM.
9b. **Anomaly precision is 57%.** Roughly four in ten ML alerts are false
   positives, deliberately: recall was prioritised because a missed unauthorized
   operator costs far more than a dismissed alert. State this plainly.
9c. **Onboarding puts all allocated equipment at the client's FIRST site.**
   Spreading an opening allocation across sites is a dispatch decision, and
   dispatch already has a screen; guessing here would produce moves to undo.
9d. **Onboarding creates one login per client.** Multiple users per tenant is a
   schema-supported but unimplemented case.
10. **Node 20.17 is below Vite's preferred 20.19+.** Prints a warning at startup; works fine.
11. **`HTTP_422_UNPROCESSABLE_ENTITY` deprecation warnings** from a newer Starlette. Cosmetic.

## Important Design Decisions

1. **SQLite default, Postgres-compatible** — a demo that cannot boot scores zero. One env var to swap.
2. **`bcrypt` directly, not `passlib`** — verified broken pairing; avoids a traceback on every login.
3. **`create_all` + seed as the reset path** — iteration speed during a hackathon.
4. **Cross-tenant → 404, not 403** — prevents resource-existence disclosure and ID enumeration.
5. **Hybrid intelligence** — deterministic facts (unauthorized operator, overdue, low fuel) must never
   be probabilistic. ML earns only the fuzzy pattern cases.
6. **HistGBR over XGBoost** — already installed, no new artifact format, and it beats the baseline by
   27.2%. xgboost stays available if a future need justifies it.
7. **Alert `dedupe_key` NULL-on-resolve** — a portable partial unique index. Without it the simulator
   floods the table within a minute.
8. **Health degrades monotonically** — recovery only via maintenance or check-in inspection. A tire
   flickering GOOD↔CRITICAL every 10 seconds would make every alert meaningless.
9. **Polling over WebSockets** — robustness beats elegance on stage.
10. **Seeded RNG** — the demo must be identical on the third rehearsal.
11. **`EQX1007` is the scripted anomaly** — it is the row from the original problem statement
    (Excavator, NULL site, 0 engine hours, 12 idle hours). The demo villain is their own sample data.
12. **Anomaly threshold calibrated at training time and stored in the artifact** — a hardcoded value
    silently produced 0% detection. Never hardcode a model threshold again.
13. **Anomaly rates recalibrated for 90× time compression** — see the Simulator section. The brief's
    suggested rates produced a fleet-wide epidemic in 22 minutes.
14. **`EQX1007` parked in the simulator** — keeps Demo Scene 2 alive for an arbitrarily long demo.
15. **One aggregate endpoint per dashboard** — 5s polling makes per-widget requests wasteful, and one
    response guarantees a consistent screen.
16. **Login takes a plain `str`, not `EmailStr`** — format-validating a login identifier leaks
    information (422 "malformed" vs 401 "wrong credentials"), and `EmailStr` rejects the reserved
    `.local` TLD used by the documented demo accounts.
17. **Vite pinned to 7** — Vite 8's rolldown native binding fails to install here (npm/cli#4828).
18. **shadcn/ui dropped** — the real needs were ~30-line primitives; the generator + Radix surface was
    not worth it. Revisit for complex widgets.
19. **Feature engineering shared between training and serving** — separate definitions drift, and a
    drifted model scores garbage silently.
20. **`EQX1012` has a sticky operator mismatch** — the simulator would otherwise re-roll the operator
    back to matching within a tick or two and auto-resolve Demo Scene 4's CRITICAL alert before it
    could be shown. Found by `verify_demo.py`, not by guessing.
21. **`UNAUTHORIZED_OPERATOR` does not auto-resolve when a machine stops** — it records a security
    event, not a live gauge. It clears when the assignment is corrected or a human resolves it.
22. **Maintenance assets are excluded from health alerts** — a machine in the workshop having a
    critical engine is *why* it is there; alerting on it puts permanent un-actionable rows in the queue.

23. **The training generator runs the simulator's own state machine** — same
    duty-cycle probabilities, same 06:00-20:00 shift, same fuel burn and refuel
    behaviour, same "current run" semantics for `continuous_runtime_minutes`.
    The previous generator invented a tidier world (72% utilization vs the
    simulator's 36%), so the model had never seen what it was deployed into and
    flagged 29 of 34 machines. Design Decision #19 said feature ENGINEERING must
    be shared between training and serving; this extends the same rule to the
    DATA. If you change `SIM_START_WORK_PROB`, `SIM_STOP_WORK_PROB`, the shift
    window or the refuel settings in `config.py`, update the constants at the
    top of `ml/generate_training_data.py` and **retrain**.

24. **Client onboarding is ONE transaction, not five API calls** — a customer
    arriving is one business event. Five calls make a half-created tenant a
    normal outcome: a login with no equipment, or sites against a client whose
    user creation then failed. Every one of those has to be unpicked by hand.
    Allocation goes through `rental_service.checkout` rather than setting asset
    columns directly, so onboarding inherits the audited path — AssetEvent
    written, one-open-rental-per-asset enforced, maintenance machines refused,
    daily counters reset. And you cannot allocate stock the depot does not hold:
    the request fails with a 409 naming the shortfall rather than quietly
    handing over fewer machines than were asked for.

25. **`isAnimationActive={false}` on every chart** — Recharts restarts a bar's
    enter animation whenever it receives a new data array. These screens poll
    every 5s. On a `<Bar>` with `<Cell>` children the cells remount mid-flight
    and the bar freezes at whatever fraction of its height it reached: measured
    at ~21%, which rendered a forecast of 3.3 shorter than an availability of 1.
    The table said one thing and the chart said the opposite. **Never re-enable
    animation on a polled chart.**

26. **`unassigned_asset` is a separate failure mode from `lost_asset`** — the
    combined mode always paired "no site" with "no telemetry for hours", so the
    model learned them as a single signal. The problem statement's own row —
    EQX1007, on hire, no site, zero runtime — reports telemetry perfectly well
    every tick, matched only half the learned pattern, and scored +0.0088
    against a 0.0 threshold. Missed by a hair, for a reason that had nothing to
    do with the machine. A machine can be unaccounted for while still talking to
    you, and that is the more expensive failure: it accrues rent, produces
    nothing, and nobody is looking.

27. **The seeded fleet shares one clock (`SEED_DAY_MINUTES`)** — `runtime + idle`
    used to range from 70 to 780 minutes across the seeded fleet, i.e. fifty
    machines each living in a different hour of the same day. Nothing surfaced
    it until the model gained `hours_elapsed_today`. `idle_minutes_today` is now
    DERIVED as `SEED_DAY_MINUTES - runtime` and never passed in, so consistency
    holds by construction. A demo dataset has to be internally consistent for
    the same reason production data does: models read relationships, not
    individual numbers.

28. **A sweep that flags >40% of the fleet is discarded** (`ALERT_STORM_FRACTION`).
    The model is calibrated to a 3% false-positive rate. If one sweep says a
    third of every machine on hire is behaving abnormally, the likelier
    explanation by far is that the fleet moved somewhere the model was not
    trained — a shift boundary, a counter rollover, a parameter change — not
    that thirty machines broke in the same ten seconds. The sweep is dropped and
    the reason logged loudly. Rules are unaffected and keep firing, which is the
    point of splitting them: the deterministic layer never goes quiet because
    the probabilistic one lost its footing.

29. **Equipment photography is downloaded, not hotlinked** — a demo that loses
    its images because the venue WiFi dropped is worse than one that never had
    them. `frontend/public/equipment/` holds an 800x500 card and a 240x150
    thumbnail per class; the thumbnail exists because serving the large file
    into a 20px table cell fifty times is megabytes for nothing. Licences and
    Commons source URLs are in `CREDITS.md` / `CREDITS.json` beside them.

30. **The Caterpillar logo is NOT committed to this repo** — `<CatBadge>` probes
    for `/brand/cat-logo.svg`, then `.png`, and falls back to a built wordmark.
    The layout is identical either way, so dropping the official asset in is a
    zero-code change. See `frontend/public/brand/README.md`.

## How to Run

**Verified working.** Two terminals, no Docker.

```bash
# ML artifacts (once, ~30s total)
python ml/generate_training_data.py
python ml/train_anomaly_model.py
python ml/train_demand_model.py
python ml/evaluate_models.py        # optional: prints the metrics report
```

```bash
# Backend (seed, then serve; the simulator autostarts)
cd backend
pip install -r requirements.txt
python -m app.seed
python -m uvicorn app.main:app --reload --port 8000
```

```bash
# Frontend
cd frontend
npm install
npm run dev            # http://localhost:5173
```

```bash
# Tests
cd backend && python -m pytest tests/ -q     # 77 passed
```

- API docs: <http://localhost:8000/docs>
- Health: <http://localhost:8000/api/health> — reports DB, both model-loaded flags, simulator state

`python -m app.seed --keep` only seeds an empty database. The backend fails **gracefully** with a
"run `ml/train_*.py`" message if artifacts are missing, degrading to rules-only intelligence.

## Equipment Imagery

Real machine photographs live in `frontend/public/equipment/`, downloaded rather
than hotlinked (Design Decision #29). Each class has an 800x500 `card` and a
240x150 `thumb`; `hero.jpg` is 1920x1080 for the login page.

| File | Subject | Licence |
|---|---|---|
| `excavator.jpg` | Caterpillar 330 excavator | CC BY-SA 4.0 |
| `bulldozer.jpg` | Caterpillar D6K2 XL bulldozer | CC BY-SA 4.0 |
| `crane.jpg` | Yellow crawler crane | Public domain |
| `grader.jpg` | Caterpillar 24H motor grader | CC BY-SA 4.0 |
| `wheel_loader.jpg` | Caterpillar 950K wheel loader | CC BY-SA 4.0 |
| `hero.jpg` | Caterpillar 352F quarry excavator | CC BY-SA 4.0 |

Sources are Wikimedia Commons; `CREDITS.json` beside them holds the machine
readable record including each file's Commons page URL. To swap or add an image,
drop a file in with the matching slug from `frontend/src/lib/equipment.ts` — the
`SLUG` map there is the only place filenames are named.

**The Caterpillar logo is deliberately absent from the repo.** See
`frontend/public/brand/README.md`: save the official asset as `cat-logo.svg` or
`cat-logo.png` in that folder and it appears in the sidebar, on the login screen
and in the page corner with no code change. Until then a built wordmark stands in.

## Demo Credentials

DEVELOPMENT-ONLY passwords for the seeded dataset. The login screen has one-click buttons for all four.

| Role | Email | Password |
|---|---|---|
| COMPANY_ADMIN | `admin@rental.local` | `demo1234` |
| CLIENT — Acme Construction | `client1@demo.local` | `demo1234` |
| CLIENT — Northstar Mining | `client2@demo.local` | `demo1234` |
| CLIENT — Vertex Infrastructure | `client3@demo.local` | `demo1234` |

## Demo Scenario

All eight scenes are seeded deterministically and were verified in a browser.

| # | Scene | Where | What to show |
|---|---|---|---|
| 1 | **Company login** | `/company` | 50 assets, 34 rented, ~20 active, 3 sites + depot on the map, populated action queue |
| 2 | **The anomaly** | Fleet → `EQX1007` | Excavator, **"No site"** in red, unassigned, 0.0h runtime, 12h+ idle. Open the drawer: plain-English reasons, not a score. This is the problem statement's own row. |
| 3 | **Tenant isolation** | Login as Acme | The same EQX1007 alert appears. Northstar's assets are **absent**. The sidebar names the tenant. Hitting another client's asset ID directly returns 404. |
| 4 | **Employee assignment** | Asset drawer → Operator panel | Assigned vs telemetry-reported operator shown side by side. Assign the correct operator → `UNAUTHORIZED_OPERATOR` resolves and an audit event is written. |
| 5 | **Live telemetry** | Any screen | "Live telemetry" pulse + tick counter in the top bar. Runtime/fuel/utilization move. `[Tick once]` advances on cue. |
| 6 | **Deadlines** | `/company/rentals` | `EQX1021` overdue by ~3 days (red), `EQX1030` due in ~31h (amber). |
| 7 | **Forecast** | `/company/forecasting` | SITE-001 Wheel Loader: 3.3 predicted vs 1 available → **shortfall 2.3**. Red bars mark shortfalls. Model version is shown. |
| 8 | **Recommendation** | Same page + `/client/recommendations` | Company: "Pre-position 1 Wheel Loader to SITE-003" with the numbers behind it, **and the date it goes short**. Client: `[Request more assets]` → creates the record. |
| 9 | **Onboard a client** ⭐ | `/company/clients` → `[+ Register client]` | Three steps: company + login, site, equipment. The equipment step is capped by REAL depot stock — try to take 25 excavators and it refuses. Submit: tenant created, site on the map with the next SITE-00N code, machines checked out with an audit trail, depot count drops on screen. **Then sign out and sign in as the account you just made** — it sees exactly its own machines and nothing else. Tenant isolation demonstrated, not asserted. |

**Closes the loop: ONBOARD → SPOT → EXPLAIN → ACT → PREDICT → RECOMMEND**

**Scene 9 is the strongest closer.** It is the only moment where the audience
watches a tenant boundary get created and then immediately tested, and it
answers the "so how does a real customer actually start?" question that every
other scene leaves open.

**Demo tips**
- `[Tick once]` on the control tower advances the simulation on cue — do not wait for the timer.
- `[Pause telemetry]` freezes everything if you need to talk over a screen.
- Re-run `python -m app.seed` for a pristine state; the seeded RNG makes it identical every time.

## Next Agent Instructions

> **CURRENT STATE: the system is COMPLETE and WORKING. Backend, ML, simulator and all 14 frontend
> screens are built, tested and verified in a browser. 77 tests pass, 28/28 demo checks pass.
> Do not rebuild anything.**
>
> Session 2 (2026-09-02) reworked the UI, fixed two bugs that made working systems
> look broken, rebuilt demand forecasting as a recursive multi-day timeline, and
> added client onboarding. **Read "WHAT CHANGED IN SESSION 2" at the top of this
> file before touching the ML or the charts** — both contain fixes that are easy
> to undo by accident.

**If you are Codex picking this up:**

1. **Verify before you change.** Run the four Quick-orientation commands at the top. If `pytest`
   reports 77 passed and the browser shows the control tower, the system is healthy — any breakage you
   see after that is yours.

2. **Read the three environment landmines** in the Environment Audit. They cost real debugging time
   and are all already worked around:
   - Do **not** reintroduce `passlib` — use `bcrypt` directly.
   - Keep `from app.core.runtime import apply_all` **first** in `main.py` and every `ml/*.py`.
   - Do **not** upgrade to Vite 8 on this machine.

3. **Do not weaken the security layer.** `backend/app/core/deps.py` is the boundary. Any new endpoint
   must use `scope_*()` for lists and `get_*_or_404()` for single fetches, and must re-verify **every**
   referenced FK on writes. Add an isolation test for it. Frontend guards are not security.

4. **Do not hardcode a model threshold.** The anomaly threshold and severity bands are computed at
   training time and stored in the artifact (`ml/train_anomaly_model.py` → metadata →
   `app/ml/anomaly.py`). A hardcoded value previously caused a silent 0% detection rate.

4b. **Keep the training generator in step with the simulator.** The constants at
   the top of `ml/generate_training_data.py` (`P_START_IN_SHIFT`, `P_STOP_IN_SHIFT`,
   `SHIFT_START_HOUR`, `SHIFT_END_HOUR`, `REFUEL_TRIGGER`, `REFUEL_PROB`,
   `MIN_SCORING_HOURS`) mirror `backend/app/config.py` and
   `backend/app/ml/anomaly.py`. Change one side without the other and you
   reintroduce the skew that flagged 29 of 34 machines. **Retrain after any
   simulator change**, then re-check the live flag rate — not just held-out
   recall, which can look fine while the deployed system floods.

4c. **Do not re-enable chart animation.** `isAnimationActive={false}` in
   `frontend/src/components/Charts.tsx` is a correctness fix, not a style
   choice. See Design Decision #25.

5. **Do not raise the simulator anomaly probabilities** without re-reading the time-compression note
   in the Simulator section. The brief's suggested 2–5% produces 52 open alerts in 22 minutes.

6. **Keep feature engineering in `backend/app/ml/features.py`.** Both training scripts and live
   inference import it. Defining features separately makes the model score garbage silently.

7. **`EQX1007` and `EQX1012` are load-bearing for the demo.** EQX1007 is the problem statement's own
   row, kept parked by `SIM_PARKED_ASSET_CODES`. EQX1012 carries the scripted operator mismatch, kept
   alive by `SIM_STICKY_OPERATOR_ASSET_CODES`. Do not "fix" either into normal behaviour.

   EQX1007's ML alert sits close to the decision boundary by nature — it is a
   quiet failure, not a dramatic one. It is currently comfortably inside
   (score ≈ -0.025) because `SEED_DAY_MINUTES` places the fleet at 18:00. If you
   move the seeded clock earlier, re-check that it still fires: at 16:00 it
   scored +0.0008, i.e. correct but decided in the fourth decimal place.

7b. **`idle_minutes_today` is DERIVED in the seed, never passed in.** Design
   Decision #27. If you add a `deploy(...)` call, give it `runtime_today` only.

8. **Run `python backend/verify_demo.py` after any change to the simulator, rule engine or seed.**
   It checks all eight demo scenes through the real API with real credentials, and it has already
   caught two scene-breaking regressions that unit tests did not.

### Highest-priority next task

**Rehearse the 9 scenes out loud, with a timer**, and **drop the official CAT
logo into `frontend/public/brand/`**. `python backend/verify_demo.py` already proves the
data and API support every scene (28/28 checks). What has not been done is the human run-through:
narration, pacing, and screen order. Run `verify_demo.py` immediately before presenting — it catches
scene-breaking drift in seconds.

After that, in order: frontend smoke tests → Alembic squashed migration → docker-compose Postgres path.

### If you need to change the schema

Update the model in `backend/app/models/`, re-run `python -m app.seed` (drops and recreates), update
the matching TypeScript interface in `frontend/src/lib/types.ts`, and record the reason under
*Important Design Decisions*. The frontend types are hand-maintained mirrors of the Pydantic schemas;
`http://localhost:8000/openapi.json` is the reference.
