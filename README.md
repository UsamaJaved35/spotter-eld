# Dispatch — ELD Trip Planner

Plan a property-carrying truck trip against the federal hours-of-service rules,
then draw the daily ELD log sheets the trip produces.

Give it a current location, a pickup, a dropoff and the hours already used
against the 70-hour/8-day cycle. It returns the route with every legally
required stop, a duty timeline explaining *why* each stop exists, and one
filled-in FMCSA driver's daily log per calendar day.

**Live:** _add your deployed URL here_
**Walkthrough:** _add your Loom link here_

---

## What it implements

The planner is a simulation of the four duty clocks in 49 CFR 395, not a
fixed schedule. Each rule below is enforced and unit-tested.

| Rule | Regulation |
|---|---|
| 11-hour driving limit per shift | § 395.3(a)(3) |
| 14-hour driving window, reset only by 10 consecutive hours off | § 395.3(a)(2) |
| 30-minute break after **8 cumulative** driving hours, satisfiable on duty, off duty or in the sleeper berth | § 395.3(a)(3)(ii) |
| 70 on-duty hours in any 8 days | § 395.3(b) |
| 34-hour restart | § 395.3(c) |
| Record of duty status: 24-hour grid, four rows, per-row totals summing to 24, city + state in Remarks at every duty change | § 395.8 |

Plus the brief's own assumptions: fuelling at least every 1,000 miles, and one
hour on duty each for pickup and dropoff.

### Two assumptions the brief left open

Both are stated in the app's own "Rules and assumptions applied" panel rather
than buried in code:

1. **Fuel-stop duration.** The brief specifies frequency but not duration.
   Assumed 30 minutes on duty — which, per the guide, also satisfies the
   30-minute break when consecutive.
2. **The rolling cycle.** You are given a single "hours used" total, not a
   per-day history, so nothing can legitimately roll off the back of the 8-day
   window. Used hours are treated as a starting balance that only accumulates,
   cleared only by a 34-hour restart. That is the conservative reading;
   inventing a prior-day distribution would be less defensible.

---

## Architecture

```
backend/     Django 5.2 + DRF          → Vercel project #1 (root dir: backend/)
frontend/    React 19 + Vite + TS      → Vercel project #2 (root dir: frontend/)
```

The frontend rewrites `/api/*` to the backend deployment, so visitors hit **one
URL**, requests are same-origin, and no API key ever reaches the browser.

### The parts worth reading

| File | What it does |
|---|---|
| `backend/trips/services/hos.py` | The HOS state machine. A binding-constraint loop (`min` of the five clocks) rather than a chain of `if`s, so a limit cannot be silently crossed. |
| `backend/trips/services/logsheets.py` | Splits the duty log at midnight, pads each day off duty, forces the four totals to exactly 24.00. |
| `backend/trips/services/geometry.py` | Interpolates position from elapsed *driving time* using per-step cumulative arrays, so a stop forced at "6.5 hours in" lands where it really occurs. |
| `backend/trips/services/routing.py` | One interface, two providers, automatic fallback. |
| `frontend/src/components/LogSheet.tsx` | The FMCSA form in SVG. The duty line is a single continuous path, so its joins *are* the vertical connectors — and it animates as one pen stroke. |

### Routing providers

Geocoding and routing resolve **independently**, because the better provider
differs by role. Each falls through to the other on failure, so a quota running
out degrades the app instead of breaking it.

| Role | Preferred | Why |
|---|---|---|
| Geocoding, autocomplete, reverse | **OpenRouteService** (falls back to Nominatim) | Throughput, not name quality. § 395.8 needs a city and state at every duty change, and a long trip has 15–20 stops to name; ORS resolves them concurrently where Nominatim's policy caps you at 1 req/s (0.7 s vs 6.3 s for six lookups; 4.8 s vs 8.6 s for a whole plan). Nominatim also asks that you not point autocomplete traffic at it. On name *quality* the two are close to a wash — they agreed on 8 of 10 rural corridor points, and both fall back to a county where no town exists. |
| Routing | **OSRM** (falls back to OpenRouteService) | ORS's `driving-hgv` profile is badly conservative. Measured Dallas → Oklahoma City: **35.5 mph** average, against OSRM's **55.1** and ORS's own `driving-car` at **60.5**. About 55 mph is the realistic planning figure for a property-carrying CMV. |

That routing choice is deliberate and worth stating plainly: `driving-hgv` is the
*semantically* correct profile, since it honours bridge heights, weight limits
and truck-prohibited roads. But every hours-of-service clock is driven by
elapsed **time**, so a 40 % slow bias would inflate rest stops and the number of
log sheets — a far worse error for this app than occasionally routing down a
road a truck should avoid. Set `ORS_PROFILE=driving-hgv` to prefer truck
legality over duration accuracy.

Each leg is routed separately. That is needed to place the pickup correctly and
keeps every request under OpenRouteService's hard 6,000 km per-route cap.

The app is fully functional with **no key at all** — it just uses OSRM and
Nominatim for both roles.

---

## Running locally

Two terminals. Requires Python 3.12 and Node 20+.

```bash
# Terminal 1 — backend
cd backend
uv venv --python 3.12          # or: python3.12 -m venv .venv
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/python manage.py migrate
.venv/bin/python manage.py runserver 8000

# Terminal 2 — frontend
cd frontend
npm install
npm run dev                    # http://localhost:5173
```

Vite proxies `/api` to port 8000 in development. No `.env` is needed to start;
copy `backend/.env.example` to `backend/.env` if you want to add an
OpenRouteService key.

### Tests

```bash
cd backend && .venv/bin/python -m pytest        # 25 unit + API tests
cd frontend && node e2e/smoke.mjs               # 10 end-to-end checks, servers must be running
```

The suite includes a golden test taken from the regulation itself: FMCSA's
worked "John Doe" example (Driver's Guide pp. 18–19, Richmond VA → Newark NJ)
must produce exactly **Off 10 · SB 1.75 · Driving 7.75 · On 4.5 = 24**. There is
also an invariant check that no generated trip ever crosses a duty limit and
that every sheet totals 24.00.

---

## Deploying to Vercel

Two projects from this one repository. Do the backend first — the frontend needs
its URL.

**1. Push the repo**

```bash
git remote add origin git@github.com:<you>/spotter-eld.git
git push -u origin main
```

**2. Database.** In the Vercel dashboard → Storage → attach **Neon Postgres**
(free tier) to the backend project. Vercel sets `DATABASE_URL` automatically.
Locally the app falls back to SQLite when that variable is absent.

**3. Backend project**

- New Project → import the repo → set **Root Directory** to `backend`
- Vercel auto-detects Django from `manage.py` and runs `collectstatic` itself
- Environment variables:

  | Name | Value |
  |---|---|
  | `SECRET_KEY` | any long random string |
  | `DEBUG` | `false` |
  | `ALLOWED_HOSTS` | `.vercel.app` |
  | `ORS_API_KEY` | optional — from openrouteservice.org |
  | `ORS_PROFILE` | optional — `driving-car` (default) or `driving-hgv` |

- Deploy, then note the URL, e.g. `https://spotter-eld-api.vercel.app`

**4. Run migrations.** Vercel does not run them for you:

```bash
cd backend
vercel link          # link to the backend project
vercel env pull .env.local
.venv/bin/python manage.py migrate
```

**5. Frontend project**

- Edit `frontend/vercel.json` and replace `REPLACE-WITH-BACKEND.vercel.app`
  with the backend URL from step 3, then commit and push
- New Project → same repo → **Root Directory** `frontend` → framework Vite
- Deploy

**6. Smoke-test the live URL:** plan a trip, confirm the map draws, every sheet
reads `= 24.00`, and the PDF downloads.

---

## Notes

- Times are the driver's home-terminal time throughout, as § 395.8 requires;
  `USE_TZ` is off deliberately so a log sheet is never shifted into UTC.
- Route geometry is thinned with Ramer–Douglas–Peucker before it reaches the
  browser, taking a cross-country response to roughly 15 KB.
- Each plan is stored, so `/trip/<id>` reloads instantly without spending
  another routing request.

## Out of scope

Split sleeper-berth (7/3 and 8/2) provisions, the adverse-driving and
short-haul exceptions, the 60-hour/7-day cycle, and driver accounts.

## Checking the OpenRouteService integration

```bash
cd backend
.venv/bin/python scripts/check_ors.py
```

Prints what the app asks OpenRouteService for, what comes back, and the
measurement behind routing with OSRM instead. Never prints your API key.
