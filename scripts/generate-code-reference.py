#!/usr/bin/env python3
"""Build docs/FULL_CODE_REFERENCE.txt: a plain-text reference of the whole project.

Hand-written explanations live in the NARRATIVE_* constants below. The function
inventory, the test inventory, the Keycloak realm summary and the full-source
appendix are generated from the real files, so they cannot drift from the code.

Run from the project root:  python3 scripts/generate-code-reference.py
"""
from __future__ import annotations

import ast
import json
import re
import subprocess
import textwrap
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "docs" / "FULL_CODE_REFERENCE.txt"
W = 100  # wrap width


def tracked_files() -> list[str]:
    out = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True, check=True)
    return sorted(out.stdout.splitlines())


def read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8", errors="replace")


def nlines(rel: str) -> int:
    return len(read(rel).splitlines())


def h1(title: str) -> str:
    bar = "=" * W
    return f"\n\n{bar}\n{title}\n{bar}\n"


def h2(title: str) -> str:
    return f"\n{title}\n{'-' * len(title)}\n"


def wrap(text: str, indent: str = "") -> str:
    paras = [p.strip() for p in text.strip().split("\n\n")]
    return "\n\n".join(
        textwrap.fill(" ".join(p.split()), width=W, initial_indent=indent, subsequent_indent=indent)
        for p in paras
    )


# --------------------------------------------------------------------------------------
# Hand-written narrative
# --------------------------------------------------------------------------------------

NARRATIVE_OVERVIEW = """
manage-system is an inventory management web application. Users sign in through Keycloak
(OpenID Connect), manage products, record stock movements (entries and exits), and managers
can read reports, an audit trail, and administer user accounts. The same business logic is
available in two ways: server-rendered web pages (Flask + Jinja2 + HTMX) and a JSON REST API
protected by JWT bearer tokens with an OpenAPI/Swagger description.

Around the application there is a complete quality and operations pipeline: automated tests
(unit, API contract, data/migration, end-to-end browser, load), three CI systems (GitHub
Actions, Jenkins, SonarCloud analysis), a staging stack with a security scan, and an
observability stack (Prometheus, Grafana, Loki, Tempo, Alloy, Alertmanager).

TECHNOLOGY STACK
  Language / framework   Python 3.12, Flask, Flask-Smorest (blueprints + OpenAPI), Marshmallow
  Database               PostgreSQL 16 via SQLAlchemy 2 / Flask-SQLAlchemy, Flask-Migrate (Alembic)
  Authentication         Keycloak 24 (realm "inventory-realm"), Authlib (browser login), PyJWT (API)
  Front end              Jinja2 templates, HTMX for partial page updates, no separate SPA
  Telemetry              OpenTelemetry (traces), prometheus_client (metrics), JSON logs
  Tests                  pytest, pytest-cov, Schemathesis, Playwright, k6
  Containers             Docker, Docker Compose
  CI / quality           GitHub Actions, Jenkins, SonarCloud, pip-audit, OWASP ZAP
"""

NARRATIVE_ARCH = r"""
                         +---------------------------+
   Browser  ------------>|  Flask app  (app/main.py) |<------------ API clients (Bearer JWT)
   (HTML pages, HTMX)    |  port 5000                |
                         |  UI routes + /api/* APIs  |
                         +-----+-----------+---------+
                               |           |
                  SQLAlchemy   |           | OIDC login, JWKS, admin API
                               v           v
                        +-----------+   +--------------------+
                        | Postgres  |   | Keycloak 24        |
                        | port 5432 |   | port 8080          |
                        +-----------+   | realm inventory-   |
                                        | realm              |
                                        +--------------------+

   Telemetry from Flask:   /metrics (Prometheus scrape)  +  OTLP traces -> Alloy -> Tempo;  stdout logs -> Alloy -> Loki
   Dashboards and alerts:  Prometheus -> Alertmanager;  Grafana reads Prometheus, Loki, Tempo
"""

NARRATIVE_FLOWS = """
FLOW 1 - Browser login (OpenID Connect authorization code flow)
  1. The user opens any protected page. The login_required decorator finds no "user" in the Flask
     session and redirects to /auth/login-page, which shows a button.
  2. The button goes to /auth/login. Authlib builds the callback URL (/auth/callback) and
     redirects the browser to Keycloak's authorization endpoint.
  3. The user types credentials at Keycloak. Keycloak redirects back to /auth/callback with a code.
  4. callback() exchanges the code for tokens (authorize_access_token), reads the ID-token user
     info, decodes the access token WITHOUT verifying the signature (it came straight from
     Keycloak over the back channel and is only used to read role names) and keeps only the realm
     roles that contain ":" (for example product:manage). These are stored in the session as
     user_scopes. The user is redirected to "/".
  5. From now on, require_ui_scope("x:y") checks user_scopes before sensitive pages. A missing
     scope produces a flash message and a redirect to the home page.
  6. /auth/logout clears the session and redirects to Keycloak's logout endpoint, which then
     returns the browser to the app.

FLOW 2 - API call with a JWT
  1. The client obtains a token from Keycloak (password grant, or through the admin UI).
  2. It sends "Authorization: Bearer <token>". require_jwt downloads Keycloak's public keys once
     (JWKS), caches them in a module variable, finds the key by the token's "kid" header, and
     verifies the RS256 signature and expiry.
  3. require_scope("product:view") then checks that the role exists in realm_access.roles.
     Missing header/invalid token -> 401, expired -> 401, wrong role -> 403.
  4. In tests (app.config["TESTING"] = True) both decorators are bypassed and a fake claim set
     with every role is injected, so API tests do not need Keycloak.

FLOW 3 - Creating a product
  UI: POST /products reads the HTML form, requires name, SKU and price, rejects a duplicate SKU,
      converts numbers, inserts a Product, commits, bumps the products_created_total counter and
      refreshes the products_total gauge, and flashes a success message.
  API: POST /api/products validates the JSON with the same rules and returns 201 with the new
      product, or 400 for a missing field or duplicate SKU.
  Either way the SQLAlchemy "after_insert" listener writes an AuditLog row (see Flow 5).

FLOW 4 - Recording a stock movement
  The movement type must be "entry" or "exit" and the quantity a positive integer. An exit is
  rejected when it would take the quantity below zero. Otherwise the product quantity changes,
  a StockMovement row records previous and new quantity, user and notes, and the transaction is
  committed. stock_movements_total{type,product} is incremented. Changing a product's quantity
  through the product edit form or PUT /api/products/<id> creates a movement automatically
  (register_qty_change_movement).

FLOW 5 - Audit trail
  audit/listeners.py registers SQLAlchemy listeners on Product and StockMovement for
  after_insert, after_update and after_delete. Each listener builds an AuditLog row containing
  the table, record id, action (INSERT/UPDATE/DELETE), old and new values as JSON, the acting user
  (from the session or request context) and a timestamp. Rows for other tables are ignored, and
  an update that changed nothing is skipped. The managers' /audit page and /api/audit read them.

FLOW 6 - User administration
  Only users with user:manage reach /users and /api/users. The app never stores users itself:
  keycloak_admin.py logs in to Keycloak as the master-realm admin (password grant against
  admin-cli), then calls Keycloak's admin REST API to list, create, read users, list realm roles
  and replace a user's application roles. After a role change it logs the user out of all
  sessions so the new permissions apply at the next login.

ROLES AND PERMISSIONS (realm roles that the application understands)
  group:employee, group:manager         broad groups
  product:view, product:manage          read / write products
  stock:view,   stock:manage            read / write stock movements
  report:view                           reports page and /api/reports
  audit:view                            audit page and /api/audit
  user:manage                           user administration
  alice_worker (employee) can see products and stock. kratos_boss (manager) additionally sees
  reports, audit and users.
"""

MODULE_PURPOSE = {
    "app/main.py": """
Application entry point and the whole server-rendered UI. It creates the Flask app, wires the
ProxyFix middleware (so URLs are correct behind a reverse proxy or tunnel), CORS, the secret key
and database URL from environment variables, the OpenAPI settings, the OAuth client, SQLAlchemy,
Flask-Migrate, telemetry and metrics, registers every API blueprint, and defines the HTML routes
(dashboard, products, stock, reports, audit, users, health). The helper functions are named after
the page they serve; each one reads query parameters or a form, queries SQLAlchemy and renders a
Jinja2 template (or an HTMX partial when the HX-Request header is present).""",
    "app/database.py": "Creates the single shared Flask-SQLAlchemy object (db). Every model and the app import it.",
    "app/telemetry.py": """
Observability plumbing. Defines the Prometheus counters and gauges used by the business code,
a JSON log formatter that adds trace and request ids, per-request hooks that time requests and set
a correlation id, OpenTelemetry tracing set-up (enabled only when OTEL_ENABLED=true), and the
/metrics endpoint with request count, latency and database-pool gauges.""",
    "app/auth/middleware.py": """
Authentication and authorization decorators. require_jwt / require_scope protect the JSON API
(Bearer JWT verified with Keycloak's public keys). login_required / require_ui_scope protect the
web pages using the Flask session. All four are bypassed when app.config["TESTING"] is true.""",
    "app/auth/views.py": "OAuth wiring and the /auth routes: login page, login redirect, callback, logout.",
    "app/auth/keycloak_admin.py": """
Thin client for Keycloak's Admin REST API and token endpoint: URL/realm/env helpers, admin token,
list/get/create users, realm roles, replace a user's roles, issue a user token for the demo
panel, and a summary formatter. Errors are raised as KeycloakAdminError carrying an HTTP status.""",
    "app/products/models.py": "Product table: id, name, SKU (unique), description, category, price, quantity, minimum stock, status.",
    "app/products/views.py": "JSON API for products under /api/products: list (search, category, sort, paging), create, read, update, delete.",
    "app/stock/models.py": "StockMovement table: product, user, type (entry/exit), previous and new quantity, notes, date.",
    "app/stock/services.py": "Helpers that create StockMovement rows (register_stock_movement, register_qty_change_movement). They add to the session but never commit.",
    "app/stock/views.py": "JSON API under /api/stock: record a movement, query history with filters, and list low-stock alerts.",
    "app/audit/models.py": "AuditLog table: table name, record id, action, old and new JSON values, user, timestamp.",
    "app/audit/listeners.py": "SQLAlchemy event listeners that write AuditLog rows whenever a Product or StockMovement is inserted, updated or deleted.",
    "app/audit/views.py": "JSON API under /api/audit: list with filters and paging, plus lookups by product id and by movement id.",
    "app/reports/views.py": "JSON API under /api/reports: GET /critical-stock (products at or below minimum stock), GET /top-products (highest quantities) and GET /recent-movements (latest stock movements). Protected by the report:view scope.",
    "app/users/views.py": "JSON API under /api/users for Keycloak user administration: list, create, read, replace roles, issue token.",
    "app/__init__.py": "Empty package marker.",
    "app/audit/__init__.py": "Empty package marker.",
    "app/reports/__init__.py": "Empty package marker.",
    "app/users/__init__.py": "Empty package marker.",
}

TEMPLATE_PURPOSE = {
    "app/templates/base.html": "Master layout: head, navigation sidebar (items hidden by role), flash messages, HTMX script. Every page extends it.",
    "app/templates/login.html": "Login page with the 'Continuar con Keycloak' button.",
    "app/templates/index.html": "Dashboard: totals, low/critical stock counts, last five movements.",
    "app/templates/products/index.html": "Products page shell with search box and sortable table container.",
    "app/templates/products/partials/table.html": "Product table plus pagination; replaced in place by HTMX on search/sort/delete.",
    "app/templates/products/form.html": "Create / edit product form (product=None means create).",
    "app/templates/stock/history.html": "Stock movement history page with filters.",
    "app/templates/stock/partials/history_table.html": "History table fragment returned for HTMX requests.",
    "app/templates/stock/update.html": "Form to record an entry or exit.",
    "app/templates/stock/partials/product_info.html": "Fragment showing the selected product's current stock inside the movement form.",
    "app/templates/reports/index.html": "Reports page: critical products, top products, recent movements.",
    "app/templates/audit/index.html": "Audit log page with table/action/record filters.",
    "app/templates/audit/partials/audit_table.html": "Audit table fragment for HTMX.",
    "app/templates/users/index.html": "User list and, right after creation, the issued JWT.",
    "app/templates/users/form.html": "Create-user form with role checkboxes.",
    "app/templates/users/detail.html": "One user: roles editor and the 'issue JWT' form.",
}

NARRATIVE_CI = """
GITHUB ACTIONS - .github/workflows/ci.yml  (workflow name "CI")
  Triggers: every push and every pull request to main or dev. A concurrency group cancels an older
  run of the same branch when a new one starts. Shared environment: Python 3.12, a CI Postgres
  user/password/database, DATABASE_URL, FLASK_APP and PYTHONPATH.
  Jobs (a job lists "needs" when it waits for others):
    build              checkout, set up Python with pip cache, install requirements, verify that
                       "from app.main import app" imports.
    unit-tests         (needs build) pytest on tests/test_products.py and tests/test_stock.py,
                       uploads a report artifact.
    api-tests          (needs build) Schemathesis contract tests (tests/test_contract.py), artifact.
    integration-tests  (needs build) starts a Postgres service container, runs "flask db upgrade",
                       then pytest on tests/data (migrations and the duplicate-SKU rule), artifact.
    coverage           (needs unit, api, integration) Postgres service, migrations, whole non-E2E suite
                       with --cov, uploads coverage.xml as an artifact.
    e2e                (needs unit, api) brings up the CI compose stack (Postgres, Keycloak, Flask),
                       waits for Keycloak and Flask, applies migrations, resets the Keycloak test
                       user passwords, installs Playwright and runs the 4 browser tests, uploads the
                       report, dumps logs on failure and always stops the stack.
    security           (needs build) pip-audit against requirements.txt, uploads the audit.
    docker-build       (needs unit, api, integration) builds the application image.

GITHUB ACTIONS - .github/workflows/sonarcloud.yml  (workflow name "SonarCloud")
  Manual only (workflow_dispatch). Starts a Postgres service, installs dependencies, runs
  migrations, runs the non-E2E tests with "--cov=. --cov-report=xml" (the "." makes file paths
  in coverage.xml start with "app/", which is what SonarCloud needs to match files), then runs
  the SonarSource scan action pinned to a commit (v8.5.0) with SONAR_TOKEN from repository
  secrets. Project key, organization and exclusions come from sonar-project.properties.
  NOTE: SonarCloud's free plan only shows the main branch, and Automatic Analysis must be OFF
  in the SonarCloud project, otherwise the scan fails with "running CI analysis while Automatic
  Analysis is enabled".

SONAR CONFIGURATION - sonar-project.properties
  organization uziel-almonte, project key Uziel-Almonte_manage-system, sources = app, tests = tests,
  Python 3.12, coverage from coverage.xml. Excluded from analysis: __pycache__, E2E tests, Alembic
  migrations and the Keycloak realm export (it contains development signing keys). Excluded from
  coverage only: scripts/, generate_openapi_spec.py, tests/ and migrations/.

JENKINS - Jenkinsfile (declarative pipeline, any agent)
  Options: no concurrent builds, 60-minute timeout. Environment: image name manage-system with the
  build number as tag, a per-build compose project name, CI database URL, paths to the docker and
  docker-compose binaries inside the Jenkins container, and HOST_MOUNT (the host path to mount
  into sibling containers, because Jenkins itself runs in Docker).
  Stages, in order:
    1. Checkout                     checkout scm.
    2. Build                        docker build of the image, then a smoke import of app.main.
    3. Prepare CI                   scripts/ci-free-host-ports.sh frees ports 5000/8080/5432.
    4. Tests (parallel)             Unit tests; API / contract tests; Data / migration tests (starts
                                    a CI Postgres, runs "flask db upgrade" and tests/data, always
                                    tears the project down).
    5. Coverage                     CI Postgres, migrations, whole non-E2E suite with coverage XML.
    6. Security                     pip-audit inside the built image.
    7. E2E                          CI compose stack, waits, migrations, Keycloak user preparation,
                                    Playwright tests.
    8. Full stack + k6 smoke        creates .env from .env.example if missing, brings up the full
                                    docker-compose.yml stack, waits for services, migrates, prepares
                                    Keycloak users, runs scripts/verify-stack.sh and a k6 smoke test.
    9. Docker image                 tags the build as manage-system:ci.
  Post (always): tears down every compose project it created so nothing is left behind.
  Jenkins itself is defined by jenkins/Dockerfile (Jenkins LTS + Docker CLI + Compose + plugins),
  jenkins/plugins.txt, jenkins/casc.yaml (Configuration as Code: users and the job "manage-system")
  and jenkins/jenkins-entrypoint.sh. It is started with "docker compose --profile jenkins up -d
  --build jenkins" on http://localhost:8090.
"""

NARRATIVE_INFRA = """
DOCKERFILE (application image)
  Starts from python:3.12-slim, sets /app as the working directory, copies requirements.txt first
  (so the dependency layer is cached), installs requirements without a pip cache, copies the rest
  of the project, exposes port 5000 and starts "flask --app app.main run --host=0.0.0.0 --port=5000".

docker-compose.yml  (local / demo stack)
  web (flask_app :5000)        the app; depends on db and keycloak.
  db (postgres_db :5432)       PostgreSQL 16 with the postgres_data volume.
  keycloak (keycloak_auth :8080)  Keycloak 24 "start-dev --import-realm"; imports
                               keycloak/realm-export.json on the first start; uses Postgres.
  e2e                          Playwright container, profile "e2e" (not started by default).
  zap                          OWASP ZAP baseline scan, profile "security".
  pip-audit                    dependency audit container, profile "security".
  prometheus :9090, postgres_exporter :9187, node-exporter :9100, tempo :3200, loki :3100,
  grafana :3000, alertmanager :9093, alloy :4317/:4318/:12345   the observability stack.
  jenkins (jenkins_ci :8090)   profile "jenkins".
  Named volumes: postgres_data, prometheus_data, tempo_data, loki_data, grafana_data, alloy_data,
  jenkins_home. "docker compose down" keeps them; "down -v" DELETES them (this is why users and
  products disappear after "down -v" or after the full test script).

docker-compose.staging.yml   Same application from the BUILT image under Gunicorn, with health
  checks and a separate Keycloak database (keycloak-db-init creates it), plus the observability
  stack and a ZAP baseline scan. Run through scripts/run-staging-qa.sh.
docker-compose.ci.yml        Small stack used by CI: db, keycloak-db-init, keycloak and web.
docker-compose.sonar.yml     Local SonarQube (community) on :9000 with its own volumes.

OBSERVABILITY CONFIGURATION (observability/)
  prometheus/prometheus.yml       scrape jobs: prometheus, tempo, loki, alloy, flask, node_exporter,
                                  postgres_exporter. rules/alerts.rules.yml defines the alerts; rules/alerts.yml
                                  only holds TargetDown (up == 0 for 1 min, team infra).
  Alert rules                     HighCPUUsage (>85%), CriticalCPUUsage (>95%), HighMemoryUsage
                                  (>90%), DBPoolNearExhaustion (>90% of pool), HighErrorRate (>5% 5xx),
                                  ElevatedErrorRate (>1%), HighLatencyP95 (>1 s), HighAuthFailureRate,
                                  SpikeInvalidTokens (>50 in 15 min), AuthFailuresFromSingleIP (>20
                                  in 10 min), TargetDown. HighErrorRate exists once only (the old duplicate
                                  in alerts.yml was removed).
  alertmanager/alertmanager.yml   routes alerts by severity and team to the receivers default,
                                  infra-team, backend-team, security-team and the *-critical ones.
  alloy/config.alloy              Grafana Alloy receives OTLP traces from Flask (ports 4317 gRPC, 4318
                                  HTTP) and forwards them to Tempo. It also tails every container's
                                  stdout through the Docker socket and pushes it to Loki, labelled
                                  with `container` (flask_app, grafana...) and `service_name`
                                  (compose service). Filter in Grafana with {container="flask_app"}.
  tempo/tempo.yaml, loki/loki.yaml   storage and server settings for traces and logs.
  grafana/provisioning            datasources (Prometheus, Loki, Tempo) and four dashboards:
                                  Application (latency, throughput, errors), Infrastructure (CPU,
                                  memory, DB pool), Business (products and stock movements) and
                                  Security (authentication failures and invalid tokens).
                                  Panels use increase()/rate() windows and `or vector(0)` so they
                                  show 0 instead of "No data" when nothing has failed. The Loki
                                  datasource links `traceId=<32 hex>` in Flask logs to Tempo.
  Metrics behaviour               products_total is refreshed at every /metrics scrape (so it is
                                  right after a restart). Every 401 from the JWT middleware raises
                                  invalid_tokens_total and auth_failures_total{source_ip}.

ENVIRONMENT VARIABLES (names only - see .env.example; real values are never committed)
  Database      POSTGRES_USER, POSTGRES_PASSWORD, POSTGRES_DB, DATABASE_URL
  Flask         FLASK_SECRET_KEY, FLASK_APP
  Keycloak      KEYCLOAK_USER / KEYCLOAK_PASSWORD (master admin), KEYCLOAK_REALM_URL,
                KEYCLOAK_CLIENT_ID, KEYCLOAK_CLIENT_SECRET, KEYCLOAK_TOKEN_CLIENT_ID,
                KEYCLOAK_AUTHORIZE_URL, KEYCLOAK_TOKEN_URL, KEYCLOAK_USERINFO_URL,
                KEYCLOAK_JWKS_URL, KEYCLOAK_ISSUER, KEYCLOAK_LOGOUT_BASE,
                KEYCLOAK_ADMIN_API_URL, KEYCLOAK_ADMIN_TOKEN_URL
  Telemetry     OTEL_ENABLED and related OTLP settings
  Grafana       GRAFANA_ADMIN_USER, GRAFANA_ADMIN_PASSWORD
  Important: Keycloak reads KEYCLOAK_ADMIN / KEYCLOAK_ADMIN_PASSWORD only the FIRST time it creates
  its database. Changing them later does nothing until the volume is deleted.
"""

NARRATIVE_TESTING = """
TEST LAYERS
  Unit / API tests (SQLite in memory, auth bypassed)
    tests/test_products.py, test_stock.py, test_users.py, test_ui_routes.py, test_api_edge_cases.py
  Keycloak client tests (HTTP mocked)             tests/test_keycloak_admin.py
  Auth and security tests (real JWT checks with a locally generated RSA key)
                                                  tests/test_auth_security.py
  API contract tests (Schemathesis reads the OpenAPI spec and fuzzes every endpoint)
                                                  tests/test_contract.py
  Data / migration tests (need real PostgreSQL)   tests/data/
  End-to-end browser tests (Playwright, need the whole stack)   tests/e2e/
  Load tests (k6)                                 tests/k6/smoke-test.js, load-test.js, stress-test.js
  Coverage: 197 non-E2E tests, 98% of app/ lines locally (95.6% on SonarCloud after exclusions).

HOW THE FIXTURES WORK (tests/conftest.py)
  The "app" fixture sets DATABASE_URL to sqlite in memory BEFORE importing app.main, turns on
  TESTING, creates all tables, yields the app inside an app context, then drops everything.
  "app_client" is Flask's test client built on it. Because TESTING is true, the auth decorators are
  bypassed; test_auth_security.py flips TESTING off to exercise the real checks.

SCRIPTS (scripts/)
  Each script's header comment is quoted in the generated section below. In short:
  run-full-test-suite.sh   whole matrix locally (build, tests, coverage, audit, E2E, full stack, k6).
                           WARNING: its cleanup runs "down -v" and deletes the demo data.
  run-staging-qa.sh        staging stack + browser tests + ZAP report.
  verify-stack.sh          health-checks every service, dashboards, datasources and a token + API call.
  prepare-keycloak-e2e.sh  sets the demo users' passwords to password123 via kcadm.
  wait-for-services.sh / wait-for-keycloak-realm.py / ci-http-check.sh / ci-verify-e2e-ready.sh /
  ci-free-host-ports.sh    readiness waits and port clean-up used by CI.
  cloudflare-tunnel.sh     free public URLs for the app, Keycloak and Grafana (trycloudflare.com).
  run-sonar-scan.sh        local SonarQube scan.   run-security-scan.sh   ZAP/security scan.
  start-observability.sh   starts only the observability containers.
  jenkins-docker.sh        helper to run Jenkins in Docker.
  generate-presentation-docs.py, generate-code-reference.py   documentation generators.
"""

# --------------------------------------------------------------------------------------
# Generated sections
# --------------------------------------------------------------------------------------


FUNC_NOTES = {
    "app/audit/models.py:AuditLog.to_dict": "Returns the audit row as a JSON-friendly dict (timestamp as ISO string).",
    "app/products/models.py:Product.to_dict": "Returns the product as a dict for JSON responses (price converted from Decimal to float).",
    "app/stock/models.py:StockMovement.to_dict": "Returns the movement as a dict for JSON responses (date as ISO string).",
    "app/auth/keycloak_admin.py:KeycloakAdminError.__init__": "Stores the message and the HTTP status code to answer with (default 500).",
    "app/auth/middleware.py:require_jwt.decorated": "The wrapper that runs instead of the view: bypass in TESTING, read the Bearer header, find the key by kid, verify RS256 signature and expiry, store claims in request.user_claims, answer 401/500 on failure.",
    "app/auth/middleware.py:require_scope.decorator": "Receives the view function and returns the wrapped version (decorator factory step).",
    "app/auth/middleware.py:require_scope.decorator.decorated_function": "Runs after require_jwt: reads realm_access.roles from the claims and answers 403 if the required scope is missing.",
    "app/auth/middleware.py:login_required.decorated_function": "Web-page guard: bypass in TESTING; redirect to /auth/login-page when the session has no user; otherwise set g.user and continue.",
    "app/auth/middleware.py:require_ui_scope.decorator": "Receives the view function and returns the wrapped version (decorator factory step).",
    "app/auth/middleware.py:require_ui_scope.decorator.decorated_function": "Checks session user_scopes; on a missing permission flashes an access-denied message and redirects home with status 303.",
    "app/telemetry.py:_register_request_hooks": "Registers before_request / after_request hooks: set correlation and trace ids on g, then add them to the response headers and log the request.",
    "app/telemetry.py:init_metrics._pool": "Returns the SQLAlchemy connection pool (inside an app context) for the pool gauges.",
    "scripts/wait-for-keycloak-realm.py:main": "Polls Keycloak's realm endpoint until it answers or a timeout expires; exit code 0 means ready.",
    "scripts/generate-presentation-docs.py:read_snippet": "Reads a few lines of a source file to quote in the generated presentation.",
    "scripts/generate-presentation-docs.py:setup_styles": "Defines fonts and paragraph styles for the Word documents.",
    "scripts/generate-presentation-docs.py:add_title": "Adds a title paragraph to the document.",
    "scripts/generate-presentation-docs.py:add_h": "Adds a heading.",
    "scripts/generate-presentation-docs.py:add_p": "Adds a normal paragraph.",
    "scripts/generate-presentation-docs.py:add_bullets": "Adds a bulleted list.",
    "scripts/generate-presentation-docs.py:add_code": "Adds a monospaced code block.",
    "scripts/generate-presentation-docs.py:add_page_break": "Inserts a page break.",
    "scripts/generate-presentation-docs.py:build_uziel_doc": "Builds the application-core presentation (.docx).",
    "scripts/generate-presentation-docs.py:build_erick_doc": "Builds the quality-and-observability presentation (.docx).",
    "scripts/generate-presentation-docs.py:main": "Builds both presentation documents.",
    "app/audit/models.py:AuditLog": "Database table audit_logs: one row per audited change (table_name, record_id, action INSERT/UPDATE/DELETE, old_values and new_values as JSON, user, timestamp).",
    "app/products/models.py:Product": "Database table products: name, unique SKU, description, category, price (Numeric 10,2), qty, min_stock, status ('active' by default).",
    "app/products/views.py:ProductSchema": "Marshmallow schema for POST /api/products: name (1-100 chars), sku (1-50) and price are required; description, category (max 50), qty and min_stock (default 0, range checked) and status (active or inactive, default active) are optional.",
    "app/products/views.py:ProductUpdateSchema": "Marshmallow schema for PUT /api/products/<id>: same fields, all optional (partial update).",
    "app/stock/models.py:StockMovement": "Database table stock_movements: product_id (foreign key, cascade delete), user, type, prev_qty, new_qty, notes, date. Relationship Product.movements.",
    "app/stock/views.py:get_history": "GET /api/stock/history. Optional filters product_id, type, user, date_from, date_to (YYYY-MM-DD; unparseable dates are ignored). Returns movements newest first. Needs stock:view.",
    "app/stock/views.py:get_alerts": "GET /api/stock/alerts. Finds active products whose quantity is at or below min_stock and returns a one-element list holding {alert_count, products}. Needs stock:view.",
    "app/stock/views.py:add_movement": "POST /api/stock/movement (needs stock:manage). The StockMovementSchema validates product_id, type (entry/exit) and qty_change (1 to 2,147,483,647). Unknown product -> 404; exit larger than stock or invalid type -> 400. Otherwise updates the product quantity, adds a StockMovement row, commits, updates the stock metric and returns the movement with 201.",
}


def leading_doc(rel: str, node: ast.AST, tree: ast.AST, src: str) -> str | None:
    """Documentation written just above a def as a bare string literal or comment block."""
    parent = None
    for p in ast.walk(tree):
        if node in getattr(p, "body", []):
            parent = p
            break
    if parent is not None:
        body = parent.body
        i = body.index(node)
        if i > 0:
            prev = body[i - 1]
            if (isinstance(prev, ast.Expr) and isinstance(getattr(prev, "value", None), ast.Constant)
                    and isinstance(prev.value.value, str) and node.lineno - prev.end_lineno <= 2):
                return prev.value.value
    lines = src.splitlines()
    top = node.lineno - 1 - len(node.decorator_list)
    block = []
    j = top - 1
    while j >= 0 and lines[j].lstrip().startswith("#"):
        block.append(lines[j].lstrip("# ").rstrip())
        j -= 1
    return "\n".join(reversed(block)) if block else None


def sig_of(node: ast.AST) -> str:
    args = ast.unparse(node.args) if hasattr(node, "args") else ""
    ret = f" -> {ast.unparse(node.returns)}" if getattr(node, "returns", None) else ""
    prefix = "async def" if isinstance(node, ast.AsyncFunctionDef) else "def"
    return f"{prefix} {node.name}({args}){ret}"


def doc_block(doc: str | None, indent: str) -> str:
    if not doc:
        return f"{indent}(no docstring)\n"
    lines = [ln.rstrip() for ln in textwrap.dedent(doc).strip().splitlines()]
    return "".join(f"{indent}{ln}\n" if ln else "\n" for ln in lines)


def walk_defs(tree: ast.AST):
    """Yield (qualified_name, node, depth) for every function and class."""
    def visit(node, prefix, depth):
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                q = f"{prefix}{child.name}"
                yield q, child, depth
                yield from visit(child, q + ".", depth + 1)
            else:
                yield from visit(child, prefix, depth)
    yield from visit(tree, "", 0)


def module_docstring_and_globals(tree: ast.Module, src: str) -> list[str]:
    notes = []
    for node in tree.body:
        if isinstance(node, ast.Assign) and node.col_offset == 0:
            seg = ast.get_source_segment(src, node) or ""
            first = seg.splitlines()[0] if seg else ""
            notes.append(f"  line {node.lineno}: {first[:90]}")
    return notes


def python_inventory(files: list[str]) -> str:
    out = []
    for rel in files:
        src = read(rel)
        total = len(src.splitlines())
        try:
            tree = ast.parse(src)
        except SyntaxError as e:  # pragma: no cover
            out.append(h2(f"{rel}  (could not parse: {e})"))
            continue
        out.append(h2(f"{rel}   ({total} lines)"))
        purpose = MODULE_PURPOSE.get(rel)
        if purpose:
            out.append(wrap(purpose) + "\n")
        defs = list(walk_defs(tree))
        if not defs:
            out.append("  (no functions or classes)\n")
            continue
        out.append(f"  Functions and classes: {len(defs)}\n")
        for qname, node, depth in defs:
            ind = "  " + "    " * depth
            kind = "class" if isinstance(node, ast.ClassDef) else "function"
            end = getattr(node, "end_lineno", node.lineno)
            out.append(f"\n{ind}[{kind}] {qname}   (lines {node.lineno}-{end})\n")
            if kind == "function":
                for dec in node.decorator_list:
                    out.append(f"{ind}  @{ast.unparse(dec)}\n")
                out.append(f"{ind}  {sig_of(node)}\n")
            elif node.bases:
                out.append(f"{ind}  class {node.name}({', '.join(ast.unparse(b) for b in node.bases)})\n")
            doc = ast.get_docstring(node)
            if doc:
                out.append(doc_block(doc, ind + "  "))
            else:
                lead = leading_doc(rel, node, tree, src)
                note = FUNC_NOTES.get(f"{rel}:{qname}")
                if lead:
                    out.append(f"{ind}  (documentation written above the function in the source:)\n")
                    out.append(doc_block(lead, ind + "  "))
                if note:
                    out.append(f"{ind}  Summary: {note}\n")
                if not lead and not note:
                    out.append(f"{ind}  (no docstring or comment in the source; see its code in the appendix)\n")
    return "".join(out)


def test_inventory(files: list[str]) -> str:
    out = []
    total_tests = 0
    for rel in files:
        src = read(rel)
        tree = ast.parse(src)
        out.append(h2(f"{rel}   ({len(src.splitlines())} lines)"))
        md = ast.get_docstring(tree)
        if md:
            out.append(wrap(md, "  ") + "\n")
        count = 0
        for q, node, depth in walk_defs(tree):
            if isinstance(node, ast.ClassDef):
                out.append(f"\n  [class] {q}\n")
                continue
            is_test = node.name.startswith("test_")
            is_fixture = any("fixture" in ast.unparse(d) for d in node.decorator_list)
            if not (is_test or is_fixture):
                continue
            tag = "test" if is_test else "fixture"
            count += is_test
            decs = [ast.unparse(d) for d in node.decorator_list if not d.__class__.__name__ == "Name"]
            doc = ast.get_docstring(node)
            first = (doc or "").strip().splitlines()[0] if doc else ""
            human = node.name.replace("test_", "", 1).replace("_", " ")
            out.append(f"    [{tag}] {q}   (lines {node.lineno}-{getattr(node, 'end_lineno', node.lineno)})\n")
            for d in decs:
                if d.startswith("pytest.mark") or d.startswith("patch"):
                    out.append(f"        {'@' + d[:120]}\n")
            out.append(f"        {first if first else 'Checks: ' + human}\n")
        total_tests += count
        out.append(f"\n  Tests in this file: {count}\n")
    out.append(f"\nTOTAL test functions listed (parametrized cases count once): {total_tests}\n")
    return "".join(out)


def shell_inventory(files: list[str]) -> str:
    out = []
    for rel in files:
        src = read(rel)
        lines = src.splitlines()
        out.append(h2(f"{rel}   ({len(lines)} lines)"))
        header = []
        for ln in lines[1:40]:
            if ln.startswith("#"):
                header.append(ln.lstrip("# ").rstrip())
            elif header:
                break
        if header:
            out.append("  Purpose (from the script's own header):\n")
            out.extend(f"    {h}\n" for h in header)
        funcs = [(i + 1, m.group(1)) for i, ln in enumerate(lines)
                 if (m := re.match(r"^\s*(?:function\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*\(\)\s*\{", ln))]
        if funcs:
            out.append("  Shell functions:\n")
            out.extend(f"    line {n}: {name}()\n" for n, name in funcs)
    return "".join(out)


def migrations_inventory(files: list[str]) -> str:
    out = []
    for rel in files:
        src = read(rel)
        rev = re.search(r"^revision\s*=\s*['\"](\w+)", src, re.M)
        down = re.search(r"^down_revision\s*=\s*(.+)$", src, re.M)
        doc = ast.get_docstring(ast.parse(src)) or ""
        ops = re.findall(r"op\.(create_table|drop_table|add_column|drop_column|create_foreign_key|"
                         r"drop_constraint|create_index|drop_index|alter_column)\(\s*['\"]?([\w_]*)", src)
        out.append(h2(rel))
        out.append(f"  revision {rev.group(1) if rev else '?'}   down_revision {down.group(1).strip() if down else '?'}\n")
        if doc:
            out.append(f"  {doc.splitlines()[0]}\n")
        if ops:
            out.append("  operations: " + "; ".join(f"{a} {b}".strip() for a, b in ops) + "\n")
    return "".join(out)


def templates_inventory(files: list[str]) -> str:
    out = []
    for rel in files:
        src = read(rel)
        ext = re.search(r"{%\s*extends\s+['\"]([^'\"]+)", src)
        blocks = re.findall(r"{%\s*block\s+(\w+)", src)
        out.append(h2(f"{rel}   ({len(src.splitlines())} lines)"))
        out.append(f"  {TEMPLATE_PURPOSE.get(rel, '')}\n")
        if ext:
            out.append(f"  extends: {ext.group(1)}\n")
        if blocks:
            out.append(f"  blocks: {', '.join(blocks)}\n")
        ctx = sorted(set(re.findall(r"{{\s*([a-zA-Z_][\w]*)", src)) - {"url_for", "loop", "super"})
        if ctx:
            out.append(f"  variables used: {', '.join(ctx[:20])}\n")
        hx = sorted(set(re.findall(r"hx-(?:get|post|put|delete|target|swap|trigger)", src)))
        if hx:
            out.append(f"  HTMX attributes: {', '.join(hx)}\n")
    return "".join(out)


def realm_summary() -> str:
    realms = json.loads(read("keycloak/realm-export.json"))
    if isinstance(realms, dict):
        realms = [realms]
    out = [f"  File: keycloak/realm-export.json ({nlines('keycloak/realm-export.json')} lines, NOT reproduced "
           "in the appendix\n  because it contains development signing keys). Keycloak imports it on first "
           "start. It holds\n  two realms: master (Keycloak's own admin realm) and inventory-realm (this app).\n"]
    for data in realms:
        out.append(f"\n  Realm: {data.get('realm')}   enabled: {data.get('enabled')}   "
                   f"sslRequired: {data.get('sslRequired')}\n")
        out.append("  Clients:\n")
        for c in data.get("clients", []):
            out.append(f"    - {c['clientId']:<24} public={c.get('publicClient')}  "
                       f"standardFlow={c.get('standardFlowEnabled')}  "
                       f"directGrants={c.get('directAccessGrantsEnabled')}\n")
        roles = [r["name"] for r in data.get("roles", {}).get("realm", [])]
        out.append("  Realm roles: " + ", ".join(roles) + "\n")
        out.append("  Users in the export:\n")
        for u in data.get("users", []):
            out.append(f"    - {u['username']:<14} roles: {', '.join(u.get('realmRoles', []))}\n")
    return "".join(out)


APPENDIX_EXT = {".py", ".sh", ".yml", ".yaml", ".js", ".html", ".alloy", ".ini", ".properties", ".txt"}
APPENDIX_NAMES = {"Dockerfile", "Jenkinsfile", ".env.example", ".gitignore", "TODO"}
APPENDIX_SKIP_PREFIX = ("docs/", "reports/", "security-reports/", "htmlcov/", ".tools/", "tests/e2e/screenshots/")
APPENDIX_SKIP = {"commands.txt"}


def appendix_files(all_files: list[str]) -> list[str]:
    keep = []
    for f in all_files:
        if f.startswith(APPENDIX_SKIP_PREFIX) or f in APPENDIX_SKIP:
            continue
        p = Path(f)
        if f == "keycloak/realm-export.json":
            continue
        if p.suffix in APPENDIX_EXT or p.name in APPENDIX_NAMES or p.name.startswith("Dockerfile") \
                or f.startswith("observability/") and p.suffix == ".json" or f == "openapi_spec.json":
            keep.append(f)
    return keep


def appendix(files: list[str]) -> str:
    out = []
    for rel in files:
        text = read(rel)
        lines = text.splitlines()
        out.append(f"\n{'#' * W}\n# FILE: {rel}   ({len(lines)} lines)\n{'#' * W}\n")
        width = len(str(len(lines)))
        for i, ln in enumerate(lines, 1):
            out.append(f"{i:>{width}} | {ln}\n")
    return "".join(out)


def main() -> None:
    files = tracked_files()
    py_app = [f for f in files if f.startswith("app/") and f.endswith(".py")]
    py_tests = [f for f in files if f.startswith("tests/") and f.endswith(".py") and not f.endswith("__init__.py")]
    py_scripts = [f for f in files if (f.startswith("scripts/") or f == "generate_openapi_spec.py")
                  and f.endswith(".py")]
    sh_scripts = [f for f in files if f.startswith("scripts/") and f.endswith(".sh")] + \
                 [f for f in files if f == "jenkins/jenkins-entrypoint.sh"]
    migrations = [f for f in files if f.startswith("migrations/versions/") and f.endswith(".py")]
    templates = [f for f in files if f.startswith("app/templates/")]
    k6 = [f for f in files if f.startswith("tests/k6/") and f.endswith(".js")]
    app_loc = sum(nlines(f) for f in py_app)
    test_loc = sum(nlines(f) for f in py_tests)
    appx = appendix_files(files)

    out = []
    out.append("=" * W + "\n")
    out.append("MANAGE-SYSTEM - COMPLETE CODE REFERENCE\n")
    out.append(f"Generated {date.today().isoformat()} by scripts/generate-code-reference.py\n")
    out.append("=" * W + "\n")
    out.append(wrap("""
This single text file documents the whole project: every Python function and class (with its
docstring, line range, decorators and signature), the tests, the CI/CD pipelines, Docker and
observability configuration, and - in the appendix - the complete source of every code and
configuration file with line numbers. Sections 1 to 3 and 7 to 9 are written by hand; the
inventories are generated from the code. Function descriptions are quoted from the project's own
docstrings, which are written in Spanish with six headings: "Qué hace" (what it does), "Por qué
lo hace" (why), "Cómo lo hace" (how), "De dónde viene" (where the input comes from), "A dónde va"
(where the output goes) and "Librerías externas" (external libraries used).
Not reproduced: keycloak/realm-export.json (contains development keys; summarised in section 8),
the Markdown docs under docs/, generated reports and binary files.
"""))
    out.append("\n\nCONTENTS\n")
    for n, t in enumerate([
        "Overview, architecture and main flows",
        "Application code - every module, function and class",
        "Templates (HTML)",
        "Database models and migrations",
        "Tests - every test function, fixtures, E2E and load tests",
        "Scripts and helper programs",
        "CI/CD - GitHub Actions, SonarCloud, Jenkins",
        "Docker, Compose, Keycloak realm, observability, environment",
        "Testing strategy and how to run everything",
        "Appendix - full source of every file, with line numbers",
    ], 1):
        out.append(f"  {n:>2}. {t}\n")
    out.append(f"\nSize: {len(py_app)} application modules ({app_loc} lines), {len(py_tests)} test modules "
               f"({test_loc} lines), {len(appx)} files in the appendix.\n")

    out.append(h1("1. OVERVIEW, ARCHITECTURE AND MAIN FLOWS"))
    out.append(NARRATIVE_OVERVIEW)
    out.append(h2("Architecture"))
    out.append(NARRATIVE_ARCH)
    out.append(h2("Main flows, step by step"))
    out.append(NARRATIVE_FLOWS)

    out.append(h1("2. APPLICATION CODE - EVERY MODULE, FUNCTION AND CLASS"))
    out.append(python_inventory(py_app))

    out.append(h1("3. TEMPLATES (HTML)"))
    out.append(wrap("Jinja2 templates rendered by app/main.py and app/auth/views.py. Pages extend "
                    "base.html. Partials (under partials/) are returned alone for HTMX requests so only "
                    "the table or panel is replaced without reloading the page.") + "\n")
    out.append(templates_inventory(templates))

    out.append(h1("4. DATABASE MODELS AND MIGRATIONS"))
    out.append(wrap("The models are documented in section 2 (app/products/models.py, app/stock/models.py, "
                    "app/audit/models.py). Tables: products, stock_movements (foreign key to products with "
                    "cascade delete) and audit_logs. Alembic migrations, in order of creation:") + "\n")
    out.append(migrations_inventory(sorted(migrations)))
    out.append(h2("migrations/env.py, alembic.ini and script template"))
    out.append("  Standard Flask-Migrate/Alembic environment: it reads the database URL from the Flask app and\n"
               "  runs migrations online or offline. Full source is in the appendix.\n")

    out.append(h1("5. TESTS - EVERY TEST FUNCTION"))
    out.append(test_inventory(py_tests))
    out.append(h2("k6 load tests (JavaScript)"))
    for f in k6:
        out.append(f"  {f}  ({nlines(f)} lines) - see the appendix for the full script.\n")

    out.append(h1("6. SCRIPTS AND HELPER PROGRAMS"))
    out.append(h2("Shell scripts"))
    out.append(shell_inventory(sorted(sh_scripts)))
    out.append(h2("Python helper programs"))
    out.append(python_inventory(sorted(py_scripts)))

    out.append(h1("7. CI/CD - GITHUB ACTIONS, SONARCLOUD, JENKINS"))
    out.append(NARRATIVE_CI)

    out.append(h1("8. DOCKER, COMPOSE, KEYCLOAK REALM, OBSERVABILITY, ENVIRONMENT"))
    out.append(NARRATIVE_INFRA)
    out.append(h2("Keycloak realm summary (generated from keycloak/realm-export.json)"))
    out.append(realm_summary())

    out.append(h1("9. TESTING STRATEGY AND HOW TO RUN EVERYTHING"))
    out.append(NARRATIVE_TESTING)
    out.append(wrap("""
Quick commands. Coverage without a database: create a venv, install requirements.txt, then run
DATABASE_URL=sqlite:///:memory: pytest tests/ -m "not e2e" --ignore=tests/e2e --ignore=tests/data
--cov=app --cov-report=term-missing. Start the demo: docker compose up -d, then
docker compose exec web flask db upgrade. Stop it keeping data: docker compose down. See
commands.txt for the complete presentation checklist.
""") + "\n")
    out.append("""
PREPARE BEFORE PRESENTING (about 1 hour before; same steps as section 9 of commands.txt)
  Never run "docker compose down -v" or scripts/run-full-test-suite.sh beforehand: both delete the
  Keycloak users and the data.
  1. docker compose up -d ; docker compose exec web flask db upgrade ; bash scripts/verify-stack.sh
  2. If login fails: bash scripts/prepare-keycloak-e2e.sh (restores kratos_boss / alice_worker).
  3. Sign in at http://localhost:5000 as kratos_boss / password123, create a product and make a few
     stock movements, then repeat a minute later. Rate/increase panels need two Prometheus scrapes
     (about 30 s), and counters restart from zero whenever the web container restarts.
  4. Click around for a minute or two to build traffic.
  5. Security demo: 30 requests with a bad token from one IP
       for i in $(seq 1 30); do curl -s -o /dev/null -H "Authorization: Bearer bad" localhost:5000/api/products; done
     This fills the Security dashboard and fires SpikeInvalidTokens and AuthFailuresFromSingleIP
     (they route to the security receivers in Alertmanager and clear on their own).
  Tabs: App :5000, Grafana :3000 (admin/admin, folder "Observability"), Prometheus :9090
  (Status > Targets: 7 up), Alertmanager :9093, Keycloak :8080 (admin/admin).
  Logs and traces: Grafana > Explore > Loki, query {container="flask_app"}, click "View Trace".
  Empty panel? Wait about 30 s and send more traffic.
""")

    out.append(h1("10. APPENDIX - FULL SOURCE OF EVERY FILE, WITH LINE NUMBERS"))
    out.append("Files included (in this order):\n")
    out.extend(f"  - {f}  ({nlines(f)} lines)\n" for f in appx)
    out.append(appendix(appx))

    OUT.write_text("".join(out), encoding="utf-8")
    n = len(OUT.read_text().splitlines())
    print(f"wrote {OUT.relative_to(ROOT)}: {n} lines, {OUT.stat().st_size // 1024} KiB")


if __name__ == "__main__":
    main()
