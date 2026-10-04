# Merova Fit — Full-Stack (Phase 1–6 foundation)

Two-sided fitness coaching platform (coach + clients), the first app from Merova.
React + TypeScript + Tailwind frontend · FastAPI + MongoDB backend · JWT auth · WebSocket chat · Razorpay · Twilio WhatsApp · Resend email.

## Quick start

### 1) Backend
```bash
cd backend
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env                                 # fill values (see below)
# MongoDB: local `mongod`, or free MongoDB Atlas URL in MONGO_URL
python seed.py                                       # creates coach login + 8 shop products
uvicorn app.main:app --reload --port 8000
```
API docs: http://localhost:8000/docs

### 2) Frontend
```bash
cd frontend
npm install
cp .env.example .env        # set VITE_API_URL (default localhost:8000)
npm run dev                 # http://localhost:5173
```

## Logins
- Coach: COACH_EMAIL / COACH_PASSWORD from backend .env (created by seed.py)
- Client: sign up in the app → onboarding quiz → dashboard

## What is real (wired end-to-end)
- Auth: register/login (bcrypt+JWT), email OTP (Resend), Google Sign-In (tokeninfo verify)
- Quiz → sets daily_kcal on the user
- Training: per-day exercise logs (MongoDB), completion state
- Nutrition: meal logs, water tracker, calorie math from DB
- Weight logging + history
- Shop: products from DB, checkout → Razorpay order (server-side, secret never leaves backend), signature verification, order history
- Chat: real-time WebSocket client↔coach with persistence
- Bookings: create/cancel + WhatsApp confirmation (Twilio)
- Coach: roster, revenue (paid orders), broadcast WhatsApp, assign plan endpoint

## Keys — IMPORTANT
- All secrets live in `backend/.env` only. `.env.example` has placeholders.
- Razorpay: key_id is public; key_secret backend-only. Without keys → mock mode (dev-friendly).
- Twilio/Resend absent → actions mock-log to server console instead of failing.
- If you ever pasted real secrets in a chat/repo, ROTATE them in the provider dashboard.

## Production hardening (implemented)
- Structured logging + request IDs + timing on every request (`app/logging_conf.py`, `app/middleware.py`)
- Global error handling: friendly 422s, safe 500s (no stack leaks), clean 400s on malformed ids
- Security headers, gzip, CORS locked to FRONTEND_ORIGIN when `ENV=production`
- Rate limiting on login / register / OTP (in-memory sliding window, Redis-swappable — `app/ratelimit.py`)
- OTP: cryptographic RNG, constant-time compare, 5-attempt cap, Mongo TTL auto-expiry
- Razorpay webhook (`POST /shop/webhook`) — authoritative server-to-server payment confirmation
- Notifications service (`/notifications`) — created on bookings, orders, broadcasts, plan assignment
- File storage (`/files`) — validated image uploads (type + magic bytes + size cap), private serving (owner/coach)
- Pagination on orders, bookings, chat history; qty caps on checkout; startup refuses default JWT secret in production

## Backend v2 — production expansion (implemented)

A large expansion that rounds the API out to a full production surface while keeping the existing v1 architecture (FastAPI + async MongoDB, thin routers over reusable services, Pydantic validation, mock-fallback integrations). New pure business logic lives in `app/domain/` and is unit-tested; cross-collection operations live in `app/services/`.

### Run it
```bash
# Docker (recommended) — api + mongo + redis, one command:
cp backend/.env.example backend/.env      # set JWT_SECRET
docker compose up --build
docker compose run --rm api python seed.py   # seed coach, products, plans, promos, catalog
# → API on http://localhost:8000  ·  Swagger UI on /docs  ·  ReDoc on /redoc

# Manual:
cd backend && pip install -r requirements-dev.txt
cp .env.example .env && python seed.py
uvicorn app.main:app --reload --port 8000
pytest                                    # run the test suite
```

### New capabilities
- **Sessions & tokens** — access + refresh tokens; refresh **rotation** (a used refresh token is revoked and replaced, so a stolen token dies on next use); server-side session store enables logout, "sign out everywhere", and a session list (`app/services/sessions.py`).
- **Full credential lifecycle** — `forgot-password` (tokenised email link, hashed at rest, TTL), `reset-password`, `change-password` (all revoke existing sessions), account deletion with data erasure.
- **Apple Sign-In** — verifies Apple's RS256 id_token against Apple's JWKS (issuer/aud/expiry), alongside the existing Google Sign-In.
- **Preferences** — units, theme, per-channel notification toggles, water goal (`GET/PUT /me/preferences`).
- **Persistent cart** — one server cart per user (identical across devices), add/update/remove/sync, **promo codes** + **tax** + member discount priced by the pure engine in `app/domain/pricing.py`; every mutation broadcasts a live `cart` event.
- **Subscriptions** — free/premium, monthly/annual, 7-day one-per-user trial, Razorpay-backed activation, renewal that stacks periods, cancel-at-period-end; `require_premium` gates premium features.
- **Achievements / XP** — XP is awarded automatically as users log workouts, meals, water, and weight; levels, level-progress, and a badge catalog are derived by `app/domain/xp.py`; unlocks fire a celebratory notification.
- **Goals** — daily/weekly/monthly progress computed from the same logs (never drifts), with `complete`/`undo`.
- **Progress** — body measurements + a combined `summary` (weight trend, latest vs first measurements, progress-photo count).
- **Search** — `catalog` collection with a Mongo text index across exercises/workouts/meals, prefix-match fallback for short queries.
- **Admin panel** — user search/ban/role/delete, product CRUD, platform analytics (DAU/WAU/MAU, stickiness, workout-completion rate, revenue, subscription conversion), targeted/segmented notifications, with an audit log of every admin action.
- **Push + real-time** — FCM device-token registration and push fan-out on every notification; an authenticated `/ws/events` WebSocket delivers notifications, cart sync, and goal updates to all of a user's open devices via an in-process hub (`app/realtime_hub.py`, Redis-pub/sub-swappable).
- **Pluggable storage** — `app/integrations/storage.py` serves uploads from local disk, **S3**, or **Cloudinary** by the `STORAGE_BACKEND` env var — no API change to switch.
- **Caching** — `app/cache.py` (Redis when `REDIS_URL` is set, in-memory otherwise) fronts the product catalog and is ready for more.
- **Unified transaction ledger** — orders and subscription payments both write to `transactions`; `GET /shop/transactions` returns full payment history.
- **Tests** — `pytest` suite: pure-logic units (pricing, XP, tokens, model validation) + API integration tests over an in-memory Mongo (`mongomock-motor`) covering register/login/refresh-rotation/logout, cart+promo, premium gating, and achievements.
- **Deployment** — multi-stage non-root `Dockerfile` with a container `HEALTHCHECK`, `docker-compose.yml` (api + mongo + redis with health gates and persistent volumes), `.dockerignore`, `Makefile`.

### Endpoint map (v2)
| Area | Endpoints |
|---|---|
| Auth | `POST /auth/register·login·refresh·logout·logout-all·forgot-password·reset-password·change-password·google·apple·otp/request·otp/verify` · `GET/DELETE /auth/sessions` |
| Me | `GET /me` · `PATCH /me` · `POST /me/quiz` · `GET/PUT /me/preferences` · `DELETE /me` |
| Fitness | `GET /fitness/plan·stats` · `POST /fitness/exercise-log·meal-log·water·weight` · `GET /fitness/*-log/{date}` |
| Goals | `GET /goals/daily·weekly·monthly` · `POST /goals/complete·undo` |
| Progress | `GET/POST /progress/measurements` · `GET /progress/summary` |
| Achievements | `GET /achievements` · `GET /achievements/catalog` |
| Cart | `GET/DELETE /cart` · `POST/PATCH/DELETE /cart/items` · `POST /cart/sync·promo` · `DELETE /cart/promo` |
| Shop | `GET /shop/products·orders·transactions` · `POST /shop/checkout·verify-payment·webhook` |
| Subscriptions | `GET /subscriptions/plans·status` · `POST /subscriptions/subscribe·verify-payment·cancel` |
| Search | `GET /search·/exercises·/workouts·/meals` |
| Notifications | `GET /notifications` · `POST /notifications/{id}/read·read-all` · `DELETE /notifications/{id}` · `POST/DELETE /notifications/devices` |
| Files | `POST /files/upload` · `GET /files·/{id}` · `DELETE /files/{id}` |
| Admin | `GET /admin/users·/users/{id}·/analytics` · `PATCH /admin/users/{id}` · `POST /admin/users/{id}/ban·unban` · `DELETE /admin/users/{id}` · `POST/PATCH/DELETE /admin/products` · `POST /admin/notify` |
| Chat / Bookings / Coach | (v1, unchanged) `/chat/*`, `/bookings/*`, `/coach/*` |
| Real-time | `WS /ws/events?token=…`, `WS /chat/ws?token=…` |
| Ops | `GET /health` (db, integrations, redis, storage, ws connections, version) |

### What needs *your* credentials to go fully live
Everything runs out of the box in mock mode. Add keys in `.env` to activate the real integration: **Razorpay** (payments), **Resend** (email/OTP/reset links), **Twilio** (WhatsApp), **FCM_SERVER_KEY** (mobile push), **GOOGLE_CLIENT_ID** / **APPLE_CLIENT_ID** (social sign-in), **REDIS_URL** (shared cache + multi-instance real-time), **STORAGE_BACKEND=s3|cloudinary** (+ their keys). No code changes required.

### Backup & ops notes
- MongoDB: schedule `mongodump` (or Atlas continuous backups) against `mongo_data`; uploads persist in the `uploads` volume (or S3/Cloudinary when enabled).
- Standard API response convention: success returns the resource/JSON directly; errors return `{"detail": "..."}` with the right status. Validation → 422, auth → 401, forbidden/banned → 403, premium required → 402, rate limited → 429.
- Scale-out: set `REDIS_URL` (cache + move the real-time hub to Redis pub/sub) and run multiple `uvicorn` workers / replicas behind a load balancer; rate limiting also moves to Redis via the same `RateLimiter` interface.

## Frontend v13 — production polish pass (implemented)

Applied to `backend/static/sanya-app.html` (the app served at `/`). No features or business logic changed.
- Bug fixes: duplicate `blink` keyframes broke the chat typing-dots animation (renamed hero countdown to `cdBlink`); theme toast fired on every page load (now silent at init); shop checkout button lost its flex centering when revealed; bottom-tab highlight desynced after returning from chat/cart/subpages (now re-synced in `show()`); hero countdown froze at 00:00:00 (now rolls to the next class); every chat bubble re-animated on each message (only the newest animates now)
- Navigation: tab/screen scroll resets are instant instead of a visible smooth-scroll glide from the old position
- Glass material: specular top edge + faint bottom inner shade on every frosted pane; sheet/menu/toast gained separation shadows and highlights; the sheet scrim now blurs the app behind it; dark-mode card opacity nudged up for readability; chat/profile/subpage headers now share the main topbar's frosted material
- Motion: day-score gauge sweeps smoothly via a typed `@property --p` (conic gradients can't interpolate on their own); bottom-sheet and profile-menu content settles in with a soft stagger; toast enters on the spring curve; press/hover states added to the last untreated controls (social buttons, quiz options, cart steppers)
- Accessibility & content: aria-labels on all icon-only controls (back, bookmark, qty, remove); distinct icons for the three quiz activity levels
- Verified: 31-case automated smoke test across every interactive flow (tabs, workout/meal/water logging, cart, checkout, bookings, notifications, sheets, auth, quiz, chat, theme) — all pass; JS syntax-checked; CSS brace-balanced; no duplicate keyframes/IDs/handlers

## Frontend v14 — unified hover motion system (implemented)
Every interactive element now responds to the cursor with one consistent, Apple-calibrated motion language (inspired by the restrained families in Hover.css — float, grow, shine, icon-forward, icon-rotate, underline-from-left — rewritten from scratch; the playful ones were deliberately skipped). All hover styling lives in `@media(hover:hover)` so touch devices pay zero cost, transforms/opacity/filter keep it compositor-friendly, and press states are restated last so :active always beats :hover.
- Cards (stats, products, workouts, picks, score card, quick actions, hero, reels, program/action cards) float up 2–3px with a soft shadow expansion that keeps the glass specular edges lit
- Gradient feature cards (hero, day score, intake) get a single soft glare that glides across on hover, like light moving over glass
- Imagery micro-parallax: product art, workout images, and pick thumbnails scale ~4–6% inside their lifting card
- Icons answer the cursor: chevrons lean 2px toward the action, back arrows lean back, the send plane nudges up-right, remove/dismiss crosses rotate 90° and warm to coral, list icons scale gently
- Buttons rise 1px with a gentle brighten; destructive actions (logout, danger menu row) tint coral-soft; chips/segments/slots interpolate color and border only — no movement
- Inputs' borders wake on hover before the green focus ring takes over; text links draw their underline from the left; toggles, tab bar icons, avatar, and water glasses each got their own subtle grow/lift
- Durations unified: .18s controls · .24s cards on the spring curve · .3s shadows; verified CSS brace-balanced, no keyframe/pseudo-element collisions, full 31-case smoke suite still passing

## Frontend v15 — Train tab redesign · auth morph · liquid-glass finale (implemented)
Applied to `backend/static/sanya-app.html` and the standalone `sanya-app-v10-luxe.html`. No features or business logic changed; all IDs, handlers, and backend calls are untouched.
- **Train tab redesigned as the flagship screen.** The workout header is now a layered liquid-glass feature card in the brand's deep green: ambient glow, orbit rings, a pulsing live dot, frosted meta chips (duration / moves / kcal), and a live state chip that morphs Ready → In progress → Complete ✓. The progress bar is segmented per exercise (five ticks), fills with a glowing gradient on the app's standard ease, and a soft glare sweeps the card once on screen entry.
- **Session timeline.** Exercise rows link into a rail — the connector between check circles warms to green as the previous exercise completes, so progress reads spatially as well as numerically. Checks grew to 30px with a spring pop, Start/Done became quiet glass pills, and a section count pill (`2/5`) lives in the header. Completing all five reveals a springing "Session complete" success banner (and un-toggling removes it).
- **Classes & programs.** Live classes got frosted mini-calendar date tiles that tint green when booked, a booked count in the section header (`4 · 1 booked`), pill-shaped book buttons, and a designed empty state for weeks with no classes. Program-card art heads gained a glass edge light and a frosted date chip; the Strava slab got brand-gradient depth.
- **Login ↔ Signup is now a single morph instead of a page snap.** The segmented control's thumb glides on the spring curve; signup-only fields (name, phone, password rules) unfold with a staggered height-fade-settle gesture while the login-only note folds away; headline, subtitle, and button copy crossfade through a soft blur. Collapsed fields are `visibility:hidden` so they can't be tab-focused. Implemented with a grid-rows reveal mechanism — height animates without layout thrash, all state is class-driven, and `prefers-reduced-motion` collapses everything instantly.
- **Liquid-glass finale.** Light now falls on the top face of every solid control (ink/green/coral buttons, meal log buttons, book pills); the top bar gains a separation shadow once content scrolls beneath it; exercise and meal rows joined the unified hover system (1px float + shadow breathe, check grows with the cursor).
- **Verified:** 51-case real-browser (Chromium) smoke suite covering every flow — the full auth morph in both directions, signup → OTP → quiz → app, all Train states (ready/progress/complete/un-complete, Strava, programs on both tabs, booking + count sync), meals/water/score, cart + checkout reveal, chat, notifications, menu, themes, and logout resetting auth to login mode — all passing with zero page errors; JS syntax-checked; CSS brace-balanced; no duplicate keyframes/IDs; every inline handler resolves to a defined function.

## Frontend v16 — interaction polish · success moments · flicker-free updates (implemented)
Applied to `backend/static/sanya-app.html` and the standalone `sanya-app-v10-luxe.html`. No features or business logic changed; all IDs, handlers, and backend calls are untouched.
- **Goal-completion moment, rebuilt.** The old fade-in checkmark is now a choreographed celebration: a ring draws itself on, the tick lands, eight rays and two ripples burst outward, the title and subtitle rise in staggered, and thirty ribbon/dot confetti pieces sway down with per-piece drift and rotation. It springs in on the shared curve and auto-dismisses (or on tap). Used for workout- and meal-completion goals.
- **Premium payment success.** Orders now resolve into a full-screen confirmation modeled on the reference: a radial green glow blooms behind a large drawn ring + checkmark, three ripples expand, and the paid amount springs in above "Payment successful". Both real (Razorpay-verified) and demo checkout paths route here; the amount is captured before the cart clears so it always displays correctly.
- **Notifications.** The bell icon was replaced with a cleaner rounded glyph (matched in the notification rows), and the unread badge was repositioned to sit flush on the corner. Rows are now frosted glass cards that stagger in on open (capped 50ms steps), collapse their height away smoothly on dismiss, and press like every other control.
- **Flicker eliminated across shop and cart.** Adding or removing items used to rebuild the entire product grid, picks rail, and cart on every tap — causing the visible flash and quantity flicker from the reference shots. Every mutation is now a surgical patch: product cards, cart rows, and their controls carry stable `data-*` identities, so only the touched stepper/quantity/summary updates in place (with a subtle pop), and the surrounding nodes are never re-created. Removing a cart item collapses its row; the summary and checkout total patch in place.
- **The same node-preserving technique now covers Train and Eat.** Toggling an exercise, joining a program, booking a class, or logging a meal patches just that row and the affected counters/progress rather than re-rendering the section — so images don't reload and animations don't restart. The "Session complete" banner collapses smoothly when you un-complete a workout.
- **Consistency & press coverage.** Interaction animations now run through one spring/ease token system; the last untreated interactive elements (program cards, the Strava slab, water-glass bookmarks) gained matching press states.
- **Layout fix.** The phone frame was pinned to the viewport height (`100dvh`) instead of growing with content, which had been pushing the tab bar, sheets, and full-screen overlays below the fold on narrow screens. Panes now scroll internally as intended and every overlay lands centered.
- **Verified:** 80-case real-browser (Chromium) smoke suite — every prior flow plus node-identity checks proving the shop grid, cart rows, exercise rows, program buttons, class rows, and meal rows are preserved across updates (no rebuild), the payment overlay and celebration v2 fire and dismiss correctly, and notifications stagger in and collapse out — all passing with zero page errors. Ten pixel-audits confirm the celebration ring/rays/text, payment ring/amount (light + dark), notification chips, bell badge, and shop steppers all render. JS syntax-checked; CSS brace-balanced; no duplicate keyframes/IDs; every inline handler resolves.

## Remaining phases (spec)
- Phase 7: port the approved single-file look into the React components (design reference: `design-reference/sanya-app-v7.html`)
- Scale-out: move rate limiting + WebSocket manager to Redis when running multiple workers
