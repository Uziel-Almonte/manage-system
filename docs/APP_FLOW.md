# Application Flow — Complete Walkthrough

This document traces **every piece of information** through the system: where it's created, where it travels, what stores it, and what reads it back. Use it as a map of the whole app, from a browser click down to the database row and back out through logs/metrics/traces.

---

## 1. High-level architecture

```
┌─────────────┐      OAuth2/OIDC       ┌──────────────┐
│   Browser   │◄──────────────────────►│   Keycloak   │
│ (HTML/HTMX) │                        │ (auth server)│
└──────┬──────┘                        └──────┬───────┘
       │ HTTP (session cookie)                │ stores users/roles
       ▼                                       ▼
┌─────────────────────────────┐        ┌──────────────┐
│           Flask app          │        │  Postgres    │
│  (app.main + blueprints)     │◄──────►│ (2 schemas:  │
│  - UI routes (main.py)       │  SQL   │  app tables +│
│  - JSON API (blueprints)     │        │  keycloak)   │
└──────┬───────────────┬───────┘        └──────────────┘
       │ logs/metrics  │ traces
       ▼               ▼
┌────────────┐   ┌────────────┐   ┌───────────┐
│   Alloy    │──►│ Loki/Tempo │──►│  Grafana   │
│ (collector)│   │ Prometheus │   │ (dashboards)│
└────────────┘   └────────────┘   └───────────┘
```

**Containers** (`docker-compose.yml`): `web` (Flask), `db` (Postgres), `keycloak`, plus observability (`prometheus`, `grafana`, `tempo`, `loki`, `alloy`, `alertmanager`, `node-exporter`, `postgres_exporter`) and optional profiles (`e2e`, `security`, `jenkins`).

---

## 2. Login flow (OAuth2 / OIDC via Keycloak)

**Files:** `app/auth/views.py`, `app/auth/middleware.py`, `app/telemetry.py`

1. Browser hits `GET /auth/login-page` → renders `templates/login.html` (static page, "Continuar con Keycloak" button).
2. User clicks → `GET /auth/login` → `oauth.keycloak.authorize_redirect()` sends the browser to Keycloak's `/realms/inventory-realm/protocol/openid-connect/auth` (the **browser-facing** URL, `KEYCLOAK_AUTHORIZE_URL`, kept on `localhost:8080` since the browser can't resolve the Docker service name `keycloak_auth`).
3. Keycloak shows its own login form (backed by its own Postgres tables inside the same `db` container, a separate schema/DB managed by Keycloak itself). User submits `username`/`password`.
4. Keycloak redirects back to `GET /auth/callback?code=...` on Flask.
5. Flask (`oauth.keycloak.authorize_access_token()`) exchanges the code for tokens by calling Keycloak **server-to-server** at `KEYCLOAK_TOKEN_URL` (`http://keycloak_auth:8080/...`, the internal Docker DNS name — this call never touches the browser).
6. The response is a JSON object with `access_token` (JWT), `id_token`, `refresh_token`, `userinfo` (parsed from the ID token by Authlib).
7. Flask decodes the **unverified** `access_token` payload (no signature check needed here — it was fetched over a server-to-server trusted channel) and pulls `realm_access.roles`. Keycloak puts your custom permissions there (`product:view`, `stock:manage`, etc.) — **not** in the OAuth `scope` string, which is only ever `openid profile email`.
8. Flask stores in the **Flask session cookie** (signed, not encrypted, via `app.secret_key`):
   - `session['user']` = the OIDC userinfo dict (`preferred_username`, `email`, `name`, `sub`, ...)
   - `session['user_scopes']` = the filtered list of `:`-containing realm roles
   - The **full OAuth token is intentionally NOT stored** (it's several KB — access + refresh + id token — and would blow past the browser's ~4KB cookie limit, silently truncating the session).
9. Redirect to `/` (dashboard).

**Logout** (`GET /auth/logout`): clears the Flask session, then redirects the browser straight to Keycloak's `/protocol/openid-connect/logout?client_id=...&post_logout_redirect_uri=...` so Keycloak's own SSO session is also killed, landing back on `index`.

### Where roles/permissions actually live
- **Source of truth:** Keycloak realm `inventory-realm`, roles like `product:view`, `product:manage`, `stock:view`, `stock:manage`, `report:view`, `audit:view`, `user:manage`, plus composite groups `group:employee` / `group:manager` (defined in `keycloak/realm-export.json`).
- **On login:** copied into `session['user_scopes']` for UI gating.
- **On every API call:** re-extracted fresh from the JWT sent in the `Authorization: Bearer` header (never trusts the session for the JSON API — see §4).

---

## 3. Every UI page — request → template → data source

All UI routes live in **`app/main.py`** and are gated by `@login_required` (must have a Flask session) and, per-page, `@require_ui_scope('xxx:yyy')` (must have that role in `session['user_scopes']`, otherwise flash + redirect to `/`).

| Route | Method | Scope required | Reads from | Renders |
|---|---|---|---|---|
| `/` | GET | (logged in only) | `Product`, `StockMovement` counts/aggregates | `index.html` |
| `/products` | GET | (logged in only) | `Product` (paginated/searched/sorted) | `products/index.html` (or `partials/table.html` for HTMX) |
| `/products/new` | GET | `product:manage` | — | `products/form.html` |
| `/products` | POST | `product:manage` | writes `Product` | redirect → `/products` |
| `/products/<id>/edit` | GET | `product:manage` | `Product` | `products/form.html` |
| `/products/<id>` | PUT/POST | `product:manage` | updates `Product`, may write `StockMovement` if qty changed | redirect |
| `/products/<id>/delete` | POST | `product:manage` | deletes `Product` (cascades to its `StockMovement` rows) | redirect / HTMX partial |
| `/stock` | GET | (logged in only) | `StockMovement` (filtered by type/date/product) | `stock/history.html` |
| `/stock/update` | GET/POST | `stock:manage` | reads `Product`, writes `StockMovement` + updates `Product.qty` | `stock/update.html` |
| `/reports` | GET | `report:view` | `Product` (critical/top) + `StockMovement` (recent) | `reports/index.html` |
| `/audit` | GET | `audit:view` | `AuditLog` (filtered/paginated) | `audit/index.html` |
| `/users` | GET | `user:manage` | Keycloak Admin API (`list_users`, `get_user_realm_roles`) — **not** the local DB | `users/index.html` |
| `/users/new`, `/users` POST | GET/POST | `user:manage` | creates user in Keycloak + issues a JWT to display | `users/form.html` / `users/index.html` |
| `/users/<id>` | GET | `user:manage` | Keycloak Admin API | `users/detail.html` |
| `/users/<id>/roles` | POST | `user:manage` | updates Keycloak realm role mappings | redirect |
| `/users/<id>/token` | POST | `user:manage` | password-grant against Keycloak to mint a demo JWT | `users/detail.html` |
| `/health` | GET | JWT (`@require_jwt`) | `SELECT 1` on Postgres | JSON |
| `/metrics` | GET | — | in-process Prometheus registry | Prometheus text format |

Nav links in `templates/base.html` are conditionally shown using the same `session['user_scopes']` list — so a user without `audit:view` never even sees the "Auditoría" link (defense in depth on top of the server-side `require_ui_scope` check).

**HTMX partials:** several pages (`/products`, `/stock`, `/audit`, `/stock/update`) detect the `HX-Request` header and return just an HTML fragment (`partials/*.html`) instead of a full page, so pagination/search/filtering updates part of the DOM without a full reload.

---

## 4. JSON API — the other way in

All under `flask_smorest.Api` (Swagger UI at `/docs`), each blueprint mounted with its own `url_prefix`:

| Blueprint | Prefix | File |
|---|---|---|
| `products_bp` | `/api/products` | `app/products/views.py` |
| `stock_bp` | `/api/stock` | `app/stock/views.py` |
| `reports_bp` | `/api/reports` | `app/reports/views.py` |
| `audit_bp` | `/api/audit` | `app/audit/views.py` |
| `users_bp` | `/api/users` | `app/users/views.py` |
| `auth_bp` | `/auth` | `app/auth/views.py` |

**Every API route** is wrapped in `@require_scope('xxx:yyy')` (`app/auth/middleware.py`), which itself wraps `@require_jwt`:

1. `require_jwt` reads `Authorization: Bearer <token>`.
2. Fetches Keycloak's public signing keys from `KEYCLOAK_JWKS_URL` (`http://keycloak_auth:8080/.../certs`), cached in a module-level `_public_keys` dict.
3. Verifies the JWT signature (RS256) using the key matching the token's `kid`.
4. On success, attaches the full decoded payload to `request.user_claims`.
5. `require_scope` then checks `request.user_claims['realm_access']['roles']` contains the required scope string; otherwise `403`.

This means **the JSON API trusts the JWT independently of any Flask session** — you can call it with `curl` + a bearer token with no cookies at all (this is what `docs/CHEATSHEET.md` demonstrates).

Request bodies are validated with **Marshmallow schemas** (`ProductSchema`, `StockMovementSchema`) via `flask_smorest`'s `@blueprint.arguments(...)` decorator before the view function even runs.

---

## 5. Data model — where things are created, and their relationships

**`app/database.py`** — single shared `db = SQLAlchemy()` instance, initialized in `app/main.py`, migrated with **Flask-Migrate** (`migrations/versions/*.py`, run via `flask db upgrade`).

### `products` table (`app/products/models.py`)
- `id, name, sku (unique), description, category, price, qty, min_stock, status`
- Created by: `POST /products` (UI) or `POST /api/products` (API)
- Updated by: edit form, `PUT /api/products/<id>`, or indirectly by stock movements (qty changes)
- Deleted by: delete button / `DELETE /api/products/<id>` — cascades (`cascade='all, delete-orphan'`) to delete its `stock_movements` too

### `stock_movements` table (`app/stock/models.py`)
- `id, product_id (FK→products), user, type ('entry'|'exit'), prev_qty, new_qty, notes, date`
- Created by:
  - `app/stock/services.py::register_stock_movement()` — called from `/stock/update` (UI) and `POST /api/stock/movement`
  - `register_qty_change_movement()` — called automatically whenever a product's `qty` is edited directly through the product edit form/API (so **every quantity change, however it happens, leaves a movement record**)
- Read by: `/stock` history page, `/reports`, `/api/stock/history`, `/api/stock/alerts`, dashboard's "recent movements"

### `audit_logs` table (`app/audit/models.py`)
- `id, table_name, record_id, action (INSERT/UPDATE/DELETE), old_values (JSON), new_values (JSON), user, timestamp`
- **Never written to directly by view code.** Populated automatically by SQLAlchemy ORM event listeners (`app/audit/listeners.py`, registered once at startup via `register_audit_listeners()` in `app/main.py`):
  - `after_insert` / `after_update` on `Product` and `StockMovement` → `capture_changes()`
  - `after_delete` → `capture_deletion()`
  - The "current user" for the audit row comes from `g.user`, which `app/auth/middleware.py`'s `login_required` sets from the session, or the request telemetry hook (`app.telemetry._register_request_hooks`) sets on every request.
- Read by: `/audit` UI page and `/api/audit*` endpoints only (`audit:view` scope)

### Users / roles — **not in Postgres at all**
User accounts, passwords, and role assignments live entirely in **Keycloak's own database**. The Flask app never has a `users` table. All of `/users*` (UI) and `/api/users*` (API) are thin wrappers around the **Keycloak Admin REST API** (`app/auth/keycloak_admin.py`):
- `create_user()` → `POST {keycloak}/admin/realms/inventory-realm/users`
- `set_user_roles()` → `POST/DELETE .../role-mappings/realm`
- `fetch_user_access_token()` → password-grant against the app's own OAuth client, used to demo-issue a JWT for a user from the admin UI
- Every one of these calls first gets an **admin access token** (`get_admin_access_token()`) using the Keycloak admin credentials (`KEYCLOAK_USER`/`KEYCLOAK_PASSWORD` env vars) against `admin-cli`.

---

## 6. Stock movement flow (a concrete example, end to end)

1. Manager opens `/stock/update`, picks a product, enters `qty_change=5`, type=`entry`.
2. `stock_update_ui()` in `app/main.py`:
   - Validates product exists, type is `entry`/`exit`, qty is positive, and (for `exit`) that there's enough stock.
   - Computes `new_qty`, mutates `product.qty` in memory.
   - Creates a `StockMovement` row (not yet committed).
   - `db.session.commit()` — this single commit fires SQLAlchemy's `after_update` event on `Product` **and** `after_insert` on `StockMovement`, each independently writing an `AuditLog` row.
   - `record_stock_movement('entry', product.sku)` increments the Prometheus counter `stock_movements_total{type="entry", product="SKU"}`.
   - Flash success message, redirect to `/stock`.
3. `/stock` re-queries `StockMovement` and renders the updated history table.
4. In parallel: OpenTelemetry's Flask/SQLAlchemy instrumentation captured a trace span for the whole request (visible in Grafana/Tempo), and the structured log line (`request completed method=POST path=/stock/update status=302 ...`) is shipped by Alloy to Loki.

The exact same underlying `register_stock_movement()` helper is reused by `POST /api/stock/movement`, so both the UI and API paths produce identical audit trails and metrics.

---

## 7. Observability — where logs/metrics/traces go

**File:** `app/telemetry.py`, config under `observability/`.

- **Metrics:** `prometheus_client` counters/gauges (`products_created_total`, `stock_movements_total`, `products_total`, `auth_failures_total`, `invalid_tokens_total`, plus generic `flask_http_request_total`/`duration`) are exposed at `GET /metrics` and scraped by **Prometheus** (`observability/prometheus/prometheus.yml`). **Grafana** dashboards (provisioned under `observability/grafana/provisioning`) visualize them. **Alertmanager** handles alert routing from Prometheus rules.
- **Traces:** `OpenTelemetry` auto-instruments Flask + SQLAlchemy; spans are batched and exported via OTLP/HTTP to **Alloy** (`OTEL_EXPORTER_OTLP_ENDPOINT=http://alloy:4318/v1/traces`), which forwards them to **Tempo**.
- **Logs:** every log line gets `traceId`, `spanId`, `correlationId` (per-request UUID, echoed back as `X-Correlation-ID` header), `user`, and `endpoint` injected by `ContextFormatter` + `_register_request_hooks`. Alloy tails the Docker container logs and ships them to **Loki**. In Grafana you can pivot from a trace → its logs → the exact request, all correlated by `traceId`/`correlationId`.
- **Postgres metrics:** `postgres_exporter` container scrapes DB-level stats (connections, query stats) for Prometheus.
- **Host metrics:** `node-exporter` for CPU/mem/disk of the host machine.

Toggle everything with `OTEL_ENABLED` (env var / `.env`); when `false`, `/metrics` isn't even registered and OTLP export is skipped, but structured logging to stdout still happens.

---

## 8. CI/CD pipeline (GitHub Actions, `.github/workflows/ci.yml`)

Triggered on push/PR to `main`/`dev`. Jobs, in dependency order:

1. **build** — installs deps, sanity-imports `app.main`.
2. **unit-tests** — `pytest tests/test_products.py tests/test_stock.py` (no DB needed, uses Flask `TESTING` mode which bypasses auth via `require_jwt`/`login_required` shortcuts).
3. **api-tests** — Schemathesis contract tests (`tests/test_contract.py`) fuzz the OpenAPI schema.
4. **integration-tests** — spins up a real Postgres service container, runs `flask db upgrade`, then `tests/data/` migration/data tests.
5. **coverage** — same Postgres service, runs the full non-E2E suite with `pytest-cov`, uploads `coverage.xml` as an artifact.
6. **e2e** — brings up the **full stack** via `docker-compose.ci.yml` (Postgres + Keycloak + Flask, all in Docker), waits for Keycloak/Flask health, applies migrations, **resets `alice_worker`/`kratos_boss` passwords to `password123`** (since the realm-imported password hashes aren't known plaintext), then runs Playwright (`pytest tests/e2e -m e2e`) which drives a real browser through login → CRUD → logout.
7. **security** — `pip-audit` against `requirements.txt` for known CVEs.
8. **docker-build** — sanity-builds the production Docker image.

There's a parallel **Jenkins** pipeline (`Jenkinsfile`, `jenkins/` folder) that does a superset of this against a `file:///workspace` bind mount, additionally running k6 load tests and OWASP ZAP baseline scans (`docker-compose.yml`'s `security`/`e2e` profiles).

---

## 9. Local dev command flow (cheat-sheet summary)

```bash
cp .env.example .env
docker compose up -d --build        # web, db, keycloak + observability stack
docker compose exec web flask db upgrade   # creates products/stock_movements/audit_logs tables
bash scripts/prepare-keycloak-e2e.sh       # sets demo users' passwords to password123
```

Then:
- Browser → `http://localhost:5000/auth/login-page` → full UI flow described in §2–3.
- `curl` with a Keycloak-issued JWT → any `/api/*` endpoint, per §4.
- `http://localhost:8080` → Keycloak admin console (realm/users/roles source of truth).
- `http://localhost:3000` → Grafana (dashboards over the telemetry in §7).

See `docs/CHEATSHEET.md` for exact copy-paste commands for every one of these flows (tokens, curl examples, k6, ZAP, Jenkins, etc.).

---

## 10. Summary diagram — one request's life

```
Browser
  │ GET /products/new  (cookie: session=...)
  ▼
Flask route (app/main.py)
  │ @login_required        → checks session['user'] exists
  │ @require_ui_scope(...) → checks session['user_scopes']
  ▼
render_template('products/form.html')
  │
  ▼
Browser submits POST /products (form data)
  ▼
create_product() in app/main.py
  │ validate → Product(...) → db.session.add() → db.session.commit()
  ├─► SQLAlchemy after_insert event → AuditLog row (app/audit/listeners.py)
  ├─► record_product_created() / sync_active_products_total() → Prometheus counters/gauge
  └─► flash() + redirect('/products')
  ▼
Postgres (products, audit_logs tables updated)
  ▼
Response 302 → browser re-fetches /products → fresh DB query → rendered table

Meanwhile, in parallel for this whole request:
  OpenTelemetry span exported → Alloy → Tempo
  Structured log line (with traceId/correlationId/user) → stdout → Alloy → Loki
  after_request hook increments flask_http_request_total{...} → scraped by Prometheus
```
