# Context Transfer — Smart Rental Tracking System

**Paste this whole file as your first message in a new chat.**

---

## Who you are and what this is

You are continuing work on a **complete and working** hackathon project: the
**Smart Rental Tracking System**, a fleet intelligence platform for construction
and mining equipment rentals, built for a Caterpillar hackathon.

- **Repository:** `C:\Users\venka\CAT_HACK`
- **GitHub:** https://github.com/Venkata-Sujay/CAT-HACK
- **Platform:** Windows 11, PowerShell + Git Bash both available
- **Status:** Phases 1–8 complete and verified. Do **not** rebuild anything.

**Read `PROJECT_STATE.md` in the repo root first**, and specifically the section
**"WHAT CHANGED IN SESSION 2"** at the top. That session fixed two bugs that are
easy to reintroduce by accident, and the reasoning is recorded there.

---

## What was built

A platform that turns rental telemetry into operational decisions:
`ONBOARD → TELEMETRY → PLATFORM → INTELLIGENCE → ACTION`

Two dashboards in one app, split by login role:
- **Company control tower** — the whole fleet across all clients: live map,
  action queue, forecasting, inventory, check-in/check-out console, and
  new-client onboarding
- **Client dashboard** — only that tenant's machines, operators, alerts and
  recommendations

### Verified numbers (do not inflate these)

| Metric | Value |
|---|---|
| Backend | 37 REST endpoints, 12 DB tables |
| Frontend | 14 screens |
| Tests | **77 passing, 0 skipped** (24 tenant-isolation, 28 domain, 10 ML, 15 onboarding) |
| Demo readiness | **28/28 checks** via `backend/verify_demo.py` |
| Anomaly model | IsolationForest — **77.0% recall @ 3.0% false-positive**; precision 56.8% |
| Forecast model | HistGradientBoosting — **beats a 7-day rolling baseline by 27.2% MAE** (0.454 vs 0.623) |
| Demo data | 50 assets, 5 types, 4 sites, 3 client tenants, 18 operators, 34 live rentals |

---

## Tech stack

**Frontend:** React 19 · TypeScript · **Vite 7 (pinned)** · Tailwind CSS ·
TanStack Query (5s polling) · React Router 7 · Recharts · Leaflet + OpenStreetMap

**Backend:** Python 3.12 · FastAPI · Uvicorn · Pydantic v2 · SQLAlchemy 2.x ·
**SQLite** (PostgreSQL-ready via `DATABASE_URL`) · JWT HS256 + bcrypt

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
python -m pytest tests/ -q     # expect: 77 passed
python verify_demo.py          # expect: ALL 28 CHECKS PASSED (server must be running)
```

**Logins** (password `demo1234` for all; the login screen has one-click buttons):

| Role | Email |
|---|---|
| Company admin | `admin@rental.local` |
| Client — Acme Construction | `client1@demo.local` |
| Client — Northstar Mining | `client2@demo.local` |
| Client — Vertex Infrastructure | `client3@demo.local` |

**Stopping the backend on Windows** — two traps stacked together:

1. The process shows as `python3.12.exe`, so bash `pkill -f uvicorn` does not
   match it.
2. **`uvicorn --reload` runs the real server as a `multiprocessing` CHILD.**
   Killing whatever owns port 8000 kills only the reloader; the child keeps the
   inherited socket and carries on serving, while `netstat` shows the port owned
   by a PID that no longer exists. Four of these piled up in one session, all
   still answering `/api/health`.

Kill by command line, not by port:
```powershell
Get-CimInstance Win32_Process |
  Where-Object { $_.CommandLine -like '*uvicorn app.main:app*' -or $_.CommandLine -like '*--multiprocessing-fork*' } |
  ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
```
Confirm with `netstat -ano | Select-String "LISTENING" | Select-String ":8000"` —
it must come back empty.

**After editing `tailwind.config.js`, restart the Vite dev server.** Vite caches
the resolved Tailwind config; a hot reload silently emits an EMPTY stylesheet
and the whole app renders unstyled. This costs ten confusing minutes if you have
not seen it before.

---

## The intelligence layer — 2 ML models + 2 rule engines

**Never describe this as "4 ML models."** It is a deliberate hybrid:

| # | Component | ML? | What |
|---|---|---|---|
| 1 | Anomaly detection | ✅ trained | IsolationForest, unsupervised, 14 features, 250 trees, contamination 0.03 |
| 2 | Demand forecasting | ✅ trained | HistGradientBoostingRegressor, 13 features, time-aware split, recursive multi-step |
| 3 | Rule engine | ❌ | 8 deterministic rules |
| 4 | Recommendation engine | ❌ | Business logic over forecast + inventory + utilization |

**The reasoning is defensible and now MEASURED.** Deterministic facts
(unauthorized operator, overdue, low fuel) must never be probabilistic. That was
an assertion until session 2 quantified it: an unauthorized operator is a single
boolean flip, and IsolationForest detected it **0 times out of 96**, because a
row extreme on one of fourteen features barely moves its average path length.
Rules own certainties; ML earns only the fuzzy multi-feature cases — where it
scores 96–100%.

**Explainability is enforced.** A raw model score is never shown to a user. Each
feature is compared to the training distribution's median/IQR and the top
deviations render as sentences, de-duplicated so two features describing the
same finding do not both appear. A test fails the build if any alert lacks
reasons + a recommended action.

---

## ⚠️ Ten rules — breaking any of these breaks something

1. **Never reintroduce `passlib`.** passlib 1.7.4 reads
   `bcrypt.__about__.__version__`, removed in bcrypt ≥4.1. It prints a trapped
   traceback on every hash. We call `bcrypt` directly.

2. **Keep `from app.core.runtime import apply_all` FIRST** in `main.py` and
   every `ml/*.py`, before joblib/sklearn. joblib/loky shells out to `wmic`
   (absent on this machine) and dumps an unsuppressable traceback;
   `runtime.py` pre-seeds loky's core cache so the probe never runs.

3. **Do not upgrade to Vite 8.** Its rolldown native binding fails to install
   here (npm/cli#4828) and produces a build that cannot run. Pinned to Vite 7 +
   `@vitejs/plugin-react@4`.

4. **Do not hardcode the ML threshold.** It is computed at training time from
   the actual score distribution and stored in the artifact; inference reads it
   back. A hardcoded `-0.15` previously caused a silent **0% detection rate**.

5. **Do not raise the simulator anomaly probabilities.** Demo mode compresses
   time ~90×, so the brief's suggested 2–5% produced 52 open alerts in 22
   minutes. Current values are calibrated from measurement.

6. **`EQX1007` and `EQX1012` are load-bearing for the demo.** EQX1007 is the
   problem statement's own row (kept parked via `SIM_PARKED_ASSET_CODES`);
   EQX1012 carries the scripted operator mismatch (kept alive via
   `SIM_STICKY_OPERATOR_ASSET_CODES`). Do not "fix" either into normal
   behaviour.

7. **Do not weaken tenant isolation.** `backend/app/core/deps.py` is the
   security boundary. New endpoints must use `scope_*()` for lists and
   `get_*_or_404()` for single fetches, and re-verify **every** referenced FK on
   writes. Add an isolation test. Frontend guards are not security.

8. **Keep the training generator in step with the simulator.** ⭐ *Session 2.*
   The constants at the top of `ml/generate_training_data.py` mirror
   `backend/app/config.py` and `backend/app/ml/anomaly.py`. They diverged once
   and the model flagged **29 of 34 machines** because it had never seen the
   world it was deployed into. Retrain after any simulator change, then check
   the **live** flag rate — held-out recall can look fine while the deployed
   system floods.

9. **Do not re-enable chart animation.** ⭐ *Session 2.*
   `isAnimationActive={false}` in `frontend/src/components/Charts.tsx` is a
   correctness fix. Recharts restarts a bar's enter animation on every new data
   array, these screens poll every 5s, and a `<Bar>` with `<Cell>` children
   freezes partway — measured at 21% of true height, which rendered a forecast
   of 3.3 shorter than an availability of 1.

10. **`idle_minutes_today` is DERIVED in the seed, never passed in.** ⭐
    *Session 2.* `SEED_DAY_MINUTES - runtime`. The fleet used to span 70–780
    minutes of elapsed day, i.e. fifty machines in fifty different hours of the
    same day.

**After any change to the simulator, rule engine, seed or ML, run
`python backend/verify_demo.py`.** It has already caught three scene-breaking
regressions that unit tests did not.

---

## Key files

| Purpose | Path |
|---|---|
| **Architecture + handoff (read first)** | `PROJECT_STATE.md` |
| **Security boundary** ⭐ | `backend/app/core/deps.py` |
| 8 alert rules | `backend/app/services/rules_engine.py` |
| Anomaly ML + explainability ⭐ | `backend/app/ml/anomaly.py` |
| Demand forecasting ⭐ | `backend/app/ml/forecast.py` |
| **Shared feature engineering** ⭐ | `backend/app/ml/features.py` |
| **Training data generator (mirrors the simulator)** ⭐ | `ml/generate_training_data.py` |
| Telemetry simulator | `backend/app/simulator/engine.py` |
| **Client onboarding** ⭐ | `backend/app/services/onboarding_service.py` |
| DB models (12 tables) | `backend/app/models/` |
| Demo data generation | `backend/app/seed.py` |
| Security tests ⭐ | `backend/tests/test_tenant_isolation.py` |
| Demo verification | `backend/verify_demo.py` |
| Control tower UI | `frontend/src/pages/company/ControlTower.tsx` |
| Forecasting UI | `frontend/src/pages/company/Forecasting.tsx` |
| **Charts (animation fix)** ⭐ | `frontend/src/components/Charts.tsx` |
| Onboarding wizard UI | `frontend/src/components/OnboardClientWizard.tsx` |
| CAT brand mark + logo slot | `frontend/src/components/Brand.tsx` |
| Model metrics (auditable) | `ml/artifacts/evaluation_report.json` |

---

## What remains (nothing blocks the demo)

| # | Task |
|---|---|
| 1 | **Rehearse the 9 demo scenes out loud with a timer** — highest value; the data is verified, the human run-through is not |
| 2 | **Drop the official CAT logo into `frontend/public/brand/`** as `cat-logo.svg` or `cat-logo.png` — zero code change, a built wordmark stands in until then |
| 3 | Frontend smoke tests (backend has 77, frontend has none) |
| 4 | Alembic squashed initial migration |
| 5 | `docker-compose.yml` for the PostgreSQL path |
| 6 | Bundle code-splitting |
| 7 | Real QR camera scanner (backend endpoint already supports it) |

**Explicitly deferred:** predictive maintenance model, any additional ML. Core
demo reliability is worth more than an extra feature.

---

## Known limitations — state these honestly, never hide them

1. **All model metrics are on SYNTHETIC data.** They measure fit to our own
   generator, not real-world accuracy. This caveat is written into the
   evaluation report, training scripts, README and UI.
2. **Anomaly precision is 57%** — roughly four in ten ML alerts are false
   positives. Deliberate: recall was prioritised because a missed unauthorized
   operator costs far more than a dismissed alert.
3. **`dead_asset` and `fuel_anomaly` recall are 67% and 46%.** Published per
   mode rather than hidden inside an aggregate. Single-feature deviations score
   at chance and are the rule engine's job.
4. **SQLite, not PostgreSQL** — Docker was down and Postgres was not installed.
   Schema is portable; one env var switches it.
5. **Single-process simulator** — two API workers would double-tick.
6. **No refresh tokens** — 8h access token only.
7. **No frontend tests.** Note that the one visual bug that reached a judge was
   invisible to every backend test, because the API was returning correct
   numbers throughout.
8. **Onboarding puts all allocated equipment at the client's first site**, and
   creates one login per client.

---

## Working style that produced this

- **Verify by execution, never assume.** Every significant bug in this project
  was found by running something and measuring: three environment landmines, a
  0%-detection ML bug, a frozen chart animation measured in the DOM, and a
  train/serve distribution gap measured feature by feature against the live
  fleet. None were visible by reading code.
- **When a metric gets worse but the system gets better, say so and explain
  why.** Anomaly recall went 81.6% → 77.0% and the live false-alarm rate went
  from 29-of-34 to 1-of-34. The old number was measured against a world that
  did not exist.
- Update `PROJECT_STATE.md` at the end of every substantial unit of work. It is
  the handoff contract.
- When a design decision is non-obvious, record **why** in *Important Design
  Decisions* — there are 30 of them and they are the project's strongest asset
  under questioning.
