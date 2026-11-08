# MathAI

MathAI is a responsive Uzbek language mathematics and geometry learning homepage built with Next.js, TypeScript, and Tailwind CSS.

## Run locally

Requirements: Node.js 20.9 or newer and npm (required by the installed Next.js 16 release).

Python 3.9 or newer is also required for SymPy calculations.

1. Create an OpenRouter API key in your OpenRouter account.
2. Copy `.env.example` to `.env.local`.
3. Set `OPENROUTER_API_KEY` to the private key and `OPENROUTER_MODEL` to an OpenRouter model ID. Choose a vision-capable model if you want image solving.
4. Optionally set `OPENROUTER_SITE_URL` to the public MathAI URL.
5. Restart the dev server after changing environment values.

Keep credentials in `.env.local` on the server. Never prefix the API key with `NEXT_PUBLIC_`, commit `.env.local`, or put the key in client code.

```bash
npm install
npm run dev
```

Install the symbolic engine once in a project-local virtual environment:

```powershell
# Windows PowerShell
py -3 -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
```

```bash
# macOS / Linux
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
```

The API automatically uses the project `.venv`. If Python is installed elsewhere, set optional `SYMPY_PYTHON` in `.env.local` to its executable path. Python's standard library powers the local SQLite account database as well as the SymPy process. The database is created automatically at `data/mathai.sqlite`; set `MATHAI_DB_PATH` to use another persistent path. Keep the database file private and back it up as part of deployment operations.

Open [http://localhost:3000](http://localhost:3000). For a production build, run `npm run build` and then `npm start`.

## Solver behavior and limitations

The homepage preserves responsive navigation, mathematics and geometry selection, example problems, image preview, feature and pricing sections. `/api/solve` sends text and supported images to the configured OpenRouter model, then displays its response as Markdown with KaTeX math rendering. The API prompts the model to identify the problem, list given information, explain theory and formulas, show justified calculation steps, state and verify the answer, and summarize the concept. Image interpretation depends on the configured model's vision support. Rate limiting is process-local (8 requests per minute per IP) and is intended as basic development protection; multi-instance production deployments should use shared rate-limit storage.

For supported text problems, the API also runs a restricted Python expression parser backed by SymPy for algebraic simplification/factoring/expansion, equations, derivatives, integrals, limits, and matrix operations/determinants. Geometry support includes triangle area/perimeter/angles, Heron's formula and Pythagorean calculations, circle measurements, quadrilaterals, regular polygons, similarity/congruence checks, cube/cuboid/cylinder/cone/sphere/prism/pyramid measurements, and coordinate distance/midpoint/slope/line/triangle area. The independent result, formulas and calculation outline are provided to the AI as trusted context and shown in a separate results panel. Available shapes receive a labelled SVG diagram. Geometry explanations are requested in simple Uzbek. The AI final result is labelled as matched only when it can be matched against SymPy's canonical result. For image-only prompts, the route attempts SymPy verification on a clearly transcribed equation from the AI response. If SymPy is unavailable or the input cannot be safely parsed, normal AI solving continues without claiming a symbolic check.

If the API key or model is missing, the route returns a configuration error. Provider failures return an error and do not substitute a made-up answer.

## Accounts, database, and administrator setup

The app uses a local SQLite database created on first use. It stores users, scrypt password hashes, hashed opaque session tokens, password-reset hashes, user-owned solution history, saved-problem flags, AI request telemetry, and platform settings. Passwords and raw session/reset tokens are never stored. Registration always creates a `user` role; there is no public admin registration or role field. User/admin authorization is checked on the server for every protected route. Session cookies are HttpOnly, SameSite=Lax, and Secure in production. State-changing browser API requests also require a same-origin `Origin` header. This SQLite setup is intended for a single persistent application host; serverless or multi-instance production deployments should use a shared transactional database and distributed rate limiter.

Provision the first administrator from the project directory after creating `.venv`. This command prompts for the email, name, and password without echoing the password or placing it in shell history:

```powershell
.venv\Scripts\python.exe solver\auth_store.py provision-admin
```

Use a unique password with at least 14 characters. Run the same command to rotate an administrator's password. Keep the SQLite file and its backups private. Admin permissions are persisted in the database and are not controlled by frontend state.

Password reset uses Resend email delivery. Set `RESEND_API_KEY`, `AUTH_FROM_EMAIL` (a sender verified with Resend), and `APP_URL` in `.env.local`. Reset links expire after 30 minutes, are stored only as hashes, and invalidate existing sessions after use. If mail delivery is not configured, the reset endpoint returns a clear 503 setup error and does not create an unusable token. Email/API failures are logged without logging the reset token or provider credential; responses do not disclose whether an email belongs to an account.

MathAI currently provides the same free access to every visitor. Anonymous visitors can solve problems subject to the IP-based request limiter; signed-in users receive 100 text and image requests per UTC day, with a default saved-problem capacity of 1,000. Both former Free and Premium account records use the same solver access and limits. Requests are reserved atomically on the server, and failed provider attempts count toward the daily account allowance. The dashboard shows remaining requests and reset time. Extended explanations and throughput-priority routing are enabled for all users. Administrators can adjust the free daily limit and saved capacity in `/admin`.

Legacy Premium and payment records remain in the database for administrative history and compatibility, but they do not grant different solver limits or paid-only features. Users cannot change their own account role or configuration.

Admin APIs enforce the admin role on the server. The panel includes account and daily text/image usage statistics. AI telemetry records user ID when signed in, model, subject, HTTP status, latency, modality and a sanitized error code; it does not store prompt text in telemetry. Solved problem text and answer are stored in the owner's history when signed in. Uploaded image bytes are not persisted. Signed-in users share the same saved-problem capacity, configurable by an administrator.

Run automated SymPy, geometry, database, authentication-store, session, and permission-policy tests with:

```bash
npm run test
```

`npm run test:math` remains available as an alias for the existing Python symbolic, geometry, database, authentication, usage-limit and permission-policy tests.

## Click and Payme merchant setup

Click Shop API and Payme Business Merchant API modules, order/transaction ledgers and provider callback verification are retained for compatibility and administrative history. New user checkout is disabled because MathAI is currently free for everyone. Existing verified transactions remain recorded; no payment is required to use solver features.

**This workspace is not ready to accept live payments.** No Click or Payme merchant credentials or production HTTPS callback domain are configured here. Payment checkout is disabled in development even if test credentials are supplied. No mock transaction route is available to users, and automated tests use isolated fake credentials/database records only.

### Merchant onboarding and environment variables

1. Register the business with Click and Payme and complete each provider's merchant onboarding, contract, and any required fiscal/business setup.
2. In the Click Merchant cabinet, request the Shop API credentials: `CLICK_SERVICE_ID`, `CLICK_MERCHANT_ID`, `CLICK_USER_ID`, and `CLICK_SECRET_KEY`. Set both Click Prepare and Complete callback URLs to `https://YOUR_DOMAIN/api/payments/callback/click`; configure the approved return URL as `https://YOUR_DOMAIN/payments`.
3. In Payme Business, create/configure the web cashier and obtain `PAYME_MERCHANT_ID`; ask Payme technical support for the Merchant API login (`PAYME_LOGIN`) and set the issued cashier key/password as `PAYME_KEY`. Set its Merchant API callback endpoint to `https://YOUR_DOMAIN/api/payments/callback/payme` and checkout return/callback URL to `https://YOUR_DOMAIN/payments`.
4. Choose business-approved prices as whole UZS integer values and set them as `MATHAI_PREMIUM_MONTHLY_UZS` and `MATHAI_PREMIUM_YEARLY_UZS`. Set `APP_URL=https://YOUR_DOMAIN`. Keep all keys in the production secret manager or server `.env.local`; never use `NEXT_PUBLIC_` names.
5. Use provider sandboxes and mock-only tests first. After Click and Payme approve the callback URLs and successful sandbox transactions are verified, set `PAYMENT_MODE=live` in the production environment and restart the app. The server also requires `NODE_ENV=production` and an HTTPS `APP_URL` before creating checkout orders. Keep `PAYMENT_MODE` unset/disabled in local development.

The exact environment names are listed in `.env.example`. Click signature composition and callback fields follow the [official Click Shop API documentation](https://docs.click.uz/shop-api/requests) and [Click-maintained integration library](https://github.com/click-llc/click-integration-php). The Click Merchant API uses the Click-maintained library's documented `payment/status/{service_id}/{payment_id}` and `payment/reversal/{service_id}/{payment_id}` operations for admin status checks and reversals. Payme uses its [official Merchant API methods](https://developer.help.paycom.uz/metody-merchant-api/) (`CheckPerformTransaction`, `CreateTransaction`, `PerformTransaction`, `CancelTransaction`, `CheckTransaction`, and required `GetStatement`), Basic HTTP authentication, and [official checkout form fields](https://developer.help.paycom.uz/initsializatsiya-platezhey/generatsiya-knopki-oplaty-i-qr-koda). Payme cancellations/refunds are handled through its `CancelTransaction` protocol and Payme merchant cabinet where required.

The protected admin payment tab can filter provider and status, view failed transactions/revenue, check a pending Click transaction directly with Click, and request Click reversal. Admins cannot synthesize verified callbacks. Payme status checks are served from the callback transaction ledger. Configure HTTPS and provider callback IP restrictions at the production reverse proxy/firewall; Payme publishes its current Merchant API source IP list in its [connection setup docs](https://developer.help.paycom.uz/protokol-merchant-api/skhema-vzaimodeystviya/).

`npm run test` runs all existing Python tests plus provider authentication/signature tests. Payment callback settlement, provider failures, duplicate processing, invalid amounts, subscription expiration, and Click/Payme mock authentication are tested without contacting either provider or moving money.


## Phase 8 — Supervisor AI

The protected admin panel includes live SQLite and SymPy health checks, AI telemetry for the previous hour, payment anomaly indicators, and an event log. The administrator can run safe remediation for expired sessions and reset tokens, stale payment transactions/orders, subscription state mismatches, and invalid quota settings. Repairs are recorded in a bounded 30-day/500-event log. Passive solver events capture SymPy mismatches/failures and OpenRouter 5xx outages without storing prompt content or secrets.

## Phase 9 — Launch readiness

`GET /api/health` is a public, read-only readiness endpoint that checks SQLite and computes a small SymPy expression. It returns HTTP 200 only when both are ready and HTTP 503 otherwise; it includes no credentials or user data. Global responses include `nosniff`, frame denial, strict-origin referrer policy, and disabled camera/microphone/geolocation permissions.

Run the complete launch test suite with `npm test`. This includes existing symbolic, geometry, authentication, subscription, and payment tests plus `scripts/test-launch.mjs` for input sandboxing, permission constraints, provider signature/authentication checks, latency budgets, and concurrent quota/payment settlement behavior.

## Deploy to Railway (Production)

Because MathAI combines Next.js 16 with a Python 3 + SymPy symbolic verification engine (`solver/math_engine.py`) and a persistent SQLite database (`solver/auth_store.py`), deploy it using the included [`Dockerfile`](./Dockerfile) and [`railway.json`](./railway.json) on a container host with a persistent volume (such as Railway).

1. Push the repository to GitHub (`.gitignore` excludes `.env.local`, `.vercel/`, and local `data/` SQLite files).
2. Create a new project on [Railway](https://railway.app) from the GitHub repository. Railway automatically detects `railway.json` and `Dockerfile` and configures `/api/health` as the readiness check.
3. Attach a **Persistent Volume** to the service mounted at `/data` so `/data/mathai.sqlite` persists across deployments and restarts.
4. Set the required environment variables in Railway **Variables**:
   - `OPENROUTER_API_KEY`: Your OpenRouter API key
   - `OPENROUTER_MODEL`: Model identifier (e.g. `google/gemini-2.5-flash`)
   - `ADMIN_EMAIL`: `navruzqudratov45@gmail.com`
   - `MATHAI_DB_PATH`: `/data/mathai.sqlite`
   - `MATHAI_GLOBAL_DAILY_LIMIT`: `2000` (global daily request cap across all visitors)
   - `APP_URL`: Your public Railway domain or custom domain (e.g. `https://math.toshniyozov.dev`)
5. Provision the owner administrator account on the production database using the Railway shell:
   ```bash
   /app/.venv/bin/python solver/auth_store.py provision-admin
   ```

