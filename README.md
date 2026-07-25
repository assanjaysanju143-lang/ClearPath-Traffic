# ClearPath — Traffic-Aware Route Distribution for Bengaluru

[![Tests](https://github.com/YOUR_USERNAME/clearpath/actions/workflows/tests.yml/badge.svg)](https://github.com/YOUR_USERNAME/clearpath/actions/workflows/tests.yml)
<!-- Replace YOUR_USERNAME above once pushed — this badge is live the moment the repo is public and the workflow has run once. -->

Bengaluru's road network doesn't lack alternate routes — it lacks a way to *use* them.
Every driver's map app independently recommends the same "best" road, so the best road
fills up and stops being the best road. ClearPath is a routing system built around one
idea: **treat congestion as a shared resource to balance, not just a number to report.**

When a new driver asks for directions, ClearPath doesn't just rank routes by traffic —
it looks at how many other active drivers are already on each option and spreads new
requests across alternatives, the same way you'd split a box of chocolates between two
people instead of handing them all to whoever asks first. A live YOLO26 vehicle detector
feeds real camera-based congestion readings back into that same ranking, so the system
responds to what a camera actually sees at a junction, not only to third-party map data.

## Why this exists

Commuters in Bengaluru lose significant time daily to congestion that alternate routes
could partially absorb, if the load on those routes were coordinated rather than left to
each app guessing independently. That's the gap this project targets: not "find *a*
route" (solved), but "keep any one route from being recommended into gridlock" (mostly
unsolved for individual drivers, and an active research area — Waze and Google both
publicly frame parts of their routing around it, and it's studied in transportation
engineering as *dynamic traffic assignment*). ClearPath is a small, working instance of
that idea, scoped to a single city so it can be fully implemented rather than sketched.

## Architecture

```
┌─────────────────┐        ┌──────────────────────┐        ┌────────────────────┐
│  React frontend │  HTTP  │   FastAPI backend    │  HTTP  │  YOLO26 ML service  │
│  (Vite, Leaflet)│───────▶│   (port 8000)         │◀───────│  (port 8001)        │
│                 │        │                       │        │                     │
│  Navigation UI  │        │  /api/routes          │        │  detects vehicles   │
│  Vehicle detect │        │  /api/traffic/*       │        │  in an image/frame  │
│  Live map        │        │  /api/incidents       │        │  and reports        │
└─────────────────┘        │                       │───────▶│  density back via   │
                            │  services/            │  push  │  /api/traffic/report│
                            │   analyzer   – scoring │        └────────────────────┘
                            │   distributor– load    │
                            │                balance │
                            │   geocoder   – places  │
                            │   live_feed  – camera  │
                            │               reports  │
                            │   tomtom     – live API│
                            │               + mock   │
                            │               fallback │
                            └───────────┬───────────┘
                                        │
                                ┌───────▼────────┐
                                │   TomTom API    │
                                │ (routing, flow,  │
                                │  incidents)      │
                                └─────────────────┘
```

**The closed loop that makes this more than a map wrapper:** the ML service and the
routing engine are two separate processes, but a detection tagged with a location name
(e.g. "Outer Ring Road") is pushed to the backend's live feed and immediately re-ranks
any cached route whose turn-by-turn steps mention that location — verified end-to-end:
posting a HIGH-density camera reading for a road mentioned in the current best route
demotes it below alternatives within the same request cycle, no restart required.

## What's actually implemented (not just planned)

- **Short-term congestion forecasting** — the live camera feed used to only keep
  the latest reading per location. It now keeps a rolling 30-minute history
  (`services/live_feed.py`), and `services/forecaster.py` fits a simple linear
  trend over it — no ML model, just least-squares — to say whether a junction
  is getting better or worse, and roughly how many minutes until it crosses
  into HIGH congestion. Deliberately guards against two ways this could
  mislead: fewer than 3 readings, or readings clustered within under a
  minute of each other, both return "insufficient_data" rather than a
  confident-sounding guess extrapolated from noise (a real bug I found and
  fixed while testing this — 3 readings taken 1 second apart produced a
  wildly overconfident slope until I added a minimum time-span check).
- **Learned route-weighting (multi-armed bandit)** — the distributor originally
  scored routes with a hand-picked constant (0.7 congestion / 0.3 load). That
  constant is now chosen by an epsilon-greedy bandit (`services/bandit.py`)
  over four candidate weightings, updated with a real reward every time a
  GPS-tracked trip finishes (comparing predicted ETA to actual travel time).
  Verified in isolation with a 500-trip simulation: the bandit converged to
  preferring the genuinely best-calibrated arm 86% of the time.
- **Natural-language route requests** — `/api/routes/smart` accepts free text
  ("fastest way to Whitefield from Koramangala avoiding Sarjapur Road") and
  parses it into origin/destination/avoid-preferences. Uses Claude if
  `ANTHROPIC_API_KEY` is set, otherwise a dependency-free regex parser
  (`services/nlu.py`) handles common phrasings. Routes matching an "avoid"
  term are demoted below all non-avoided alternatives rather than hidden
  outright — a driver can still see and choose one if every alternative is
  worse.
- **Traffic-aware routing** — `/api/routes` returns alternatives ranked by
  `trafficDelayInSeconds / travelTimeInSeconds`, sourced from TomTom's routing API with
  a deterministic mock fallback (built-in Bengaluru locality table + hashed jitter) so
  the whole stack runs and demos without any API key.
- **Load-balancing distributor** — `services/distributor.py` scores each route by
  `0.7 × congestion + 0.3 × current active-driver load` and assigns new drivers to the
  least-loaded reasonable option, with a human-readable explanation returned alongside
  the assignment. Tested with 5 concurrent simulated drivers: the distributor visibly
  spread them 4/2/0 rather than sending everyone down the least-congested road.
- **Live camera feed → routing loop** — `services/live_feed.py` holds recent YOLO26
  readings (2-minute TTL) and `analyzer.apply_live_camera_data()` blends them into
  route scoring, 60% camera / 40% map data, whenever a route's steps match a reported
  location.
- **Turn-by-turn navigation** — GPS tracking, speed, distance travelled, auto-advancing
  steps, and voice guidance via the Web Speech API, with route release on arrival so
  the driver's slot frees up for others.
- **Vehicle detection** — a from-scratch YOLO26 wrapper (`traffic-ml/detector.py`)
  counts vehicles by class, computes a weighted density score (buses/trucks count more
  than bikes), and returns an annotated frame — usable via image upload or a live 2s-
  interval webcam loop.
- **Live incidents** — accidents, road works, and closures rendered on the map and in
  a dedicated panel, polled every 60 seconds.

## Design system

The UI went through a full pass to read as a standard, professional product
rather than a stylized demo — the kind of look you'd expect from Google Maps
or Uber, not an AI-generated dark/neon default:

- **Light, neutral surfaces** (`#f6f7f9` page, white cards) with a proper
  elevation system (`--shadow-card` / `--shadow-elevated`) instead of relying
  on borders alone to separate layers.
- **Brand color kept separate from status meaning** — `--primary` (a
  standard blue, `#2563eb`) drives every button, active tab, and focus ring;
  green/amber/red are reserved *only* for actual traffic congestion level
  (LOW/MODERATE/HIGH). Earlier versions conflated these — the same green
  meant both "primary action" and "low traffic," which is the kind of thing
  that reads as unpolished once you notice it.
- **Inter** throughout — the de facto standard typeface for professional
  SaaS products, replacing a more stylized display/body pairing.
- **Verified programmatically, not just by eye** — after the palette
  rewrite, computed styles were checked directly in a real headless browser
  (`getComputedStyle` on the primary button, status badges, and shadows) to
  confirm the actual rendered colors matched the design tokens, not just
  that the CSS source had been edited.
- Visible keyboard focus (`:focus-visible`) and `prefers-reduced-motion`
  support are both handled globally, not per-component.

## Tech stack

| Layer | Choice | Why |
|---|---|---|
| Frontend | React + Vite, Leaflet | fast dev loop, no map-vendor lock-in |
| Backend | FastAPI | async I/O for concurrent route requests, automatic OpenAPI docs at `/docs` |
| ML | YOLO26 (Ultralytics, Jan 2026), OpenCV | current Ultralytics flagship — anchor-free, NMS-free head, strong CPU latency; swappable to YOLO11/YOLOv8 via one constructor arg |
| Traffic data | TomTom Routing/Traffic/Search APIs | free tier, India-biased geocoding, with a mock layer for offline dev |

## Testing

**Backend** — 58 unit tests, no external dependencies (no network calls, no
real API keys needed), runs in well under a second:
```bash
cd traffic-backend
pytest
```
Covers the load-balancing distributor (isolated from the bandit's own
randomness via monkeypatching), the bandit's convergence behavior (a 500-trial
simulation asserting it actually learns to prefer the best-performing
weighting), the NLU parser's phrasing edge cases, the congestion forecaster
(including a regression test for a real overconfidence bug found during
manual testing), the live camera feed's TTL/history behavior, and the
avoid-preference/live-camera blending logic in the route scorer.

**ML detector** — 11 tests against the real YOLO26 model and Ultralytics'
own bundled sample image (so no test-image assets are needed). Slower
(~1 minute, mostly model load time) since it's exercising the actual model,
not mocks:
```bash
cd traffic-ml
pytest
```

Both suites run automatically on push via GitHub Actions
(`.github/workflows/tests.yml`) — backend tests on every push, ML tests as a
manual trigger from the Actions tab (they pull in torch, which is too heavy
to run on every commit).

**Honestly not covered yet:** the frontend has no automated tests (verified
manually + via a Puppeteer screenshot smoke-test during development, not a
checked-in suite), and there's no integration test that spins up the real
FastAPI server and hits it over HTTP end-to-end — the backend tests exercise
the service layer directly, which is faster but doesn't catch routing/
dependency-injection bugs the way a real request would. (One such bug —
calling a FastAPI endpoint function directly instead of through a request,
which silently broke `POST /api/routes` — was actually found by manual
end-to-end testing, not by these unit tests, which is exactly the gap this
paragraph is describing.)

## Running it locally

**Backend** (port 8000):
```bash
cd traffic-backend
pip install -r requirements.txt
python main.py
```
Works immediately with mock data — no API key needed. To use live TomTom data, put a
real key in `traffic-backend/.env` (see `.env.example` there).

**ML service** (port 8001, optional — only needed for the Vehicle Detection tab):
```bash
cd traffic-ml
pip install -r requirements.txt
python run.py --server
```

**Frontend** (port 3000):
```bash
cd traffic-frontend
npm install
npm run dev
```
Vite proxies `/api` → the backend and `/ml` → the ML service, so the frontend only
ever talks to `localhost:3000`.

## Honest limitations / what's next

- Route polylines on the map are illustrative (fixed Bengaluru landmark paths), not the
  real TomTom-returned geometry yet — wiring `summary_polyline` through is the natural
  next step.
- The distributor's state is in-memory and per-process; a real deployment would move
  it to Redis so it survives restarts and works across multiple backend instances.
- The ML → routing match is a simple substring match against step text; a production
  version would tie camera locations to actual road-segment IDs.
- The bandit's reward (ETA-prediction accuracy) is a reasonable proxy for "did this
  weighting produce good assignments," but it's not a perfect measure of driver
  satisfaction — a real deployment would want direct feedback too.
- Without `ANTHROPIC_API_KEY` set, natural-language parsing falls back to a regex
  parser that handles common phrasings well but won't handle messy real-world text
  as gracefully as the LLM path would.
- No auth/rate-limiting yet — fine for a portfolio demo, not for a public deployment.

## What this demonstrates

Full-stack ownership of a real, non-trivial system: an algorithm (not just an API
wrapper), a working ML component, and — critically — the two talking to each other
instead of sitting side by side. That combination, plus a problem grounded in a real
city's traffic rather than a generic CRUD app, is the actual point of the project.
