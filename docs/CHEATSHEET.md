# manage-system — Commands cheatsheet

Copy-paste reference for demos (professor), local dev, tests, k6, OWASP, observability, and Jenkins.

All commands assume you are in the repo root:

```bash
cd /path/to/manage-system
```

---

## 1. Prerequisites / env

```bash
cp .env.example .env
# Edit passwords if needed. Key fields:
#   POSTGRES_PASSWORD, KEYCLOAK_USER, KEYCLOAK_PASSWORD
```

| Variable | Purpose |
|----------|---------|
| `POSTGRES_*` / `DATABASE_URL` | Postgres for Flask |
| `KEYCLOAK_USER` / `KEYCLOAK_PASSWORD` | Keycloak **master** admin (also used by `/users` Admin API) |
| `KEYCLOAK_TOKEN_CLIENT_ID` | Usually `flask-backend` (public client, password grant) |

---

## 2. Start / stop stacks

### Full stack (app + Keycloak + observability)

```bash
docker compose up -d --build
docker compose exec web flask db upgrade
```

**Always run migrations** after a fresh volume / first boot, or `/` returns 500 (`relation "products" does not exist`).

```bash
# Stop (keep volumes)
docker compose down

# Stop and wipe DB / Grafana data
docker compose down -v --remove-orphans
```

### CI / E2E minimal stack

```bash
docker compose -f docker-compose.ci.yml up -d --build --wait --wait-timeout 600
docker compose -f docker-compose.ci.yml exec -T web flask db upgrade
COMPOSE_FILE=docker-compose.ci.yml bash scripts/prepare-keycloak-e2e.sh
```

```bash
docker compose -f docker-compose.ci.yml down -v
```

### Service URLs

| Service | URL |
|---------|-----|
| Flask app | http://localhost:5000 |
| Login page | http://localhost:5000/auth/login-page |
| Swagger | http://localhost:5000/docs |
| Keycloak | http://localhost:8080 |
| Grafana | http://localhost:3000 |
| Prometheus | http://localhost:9090 |
| Alertmanager | http://localhost:9093 |
| Loki | http://localhost:3100 |
| Tempo | http://localhost:3200 |
| Alloy | http://localhost:12345 |
| Jenkins (optional) | http://localhost:8090 |

### Port conflicts (Jenkins / leftover CI projects)

```bash
bash scripts/ci-free-host-ports.sh
```

---

## 3. Demo users & scopes

After `prepare-keycloak-e2e.sh` (or fresh realm import + that script):

| User | Password | Composite | Typical scopes |
|------|----------|-----------|----------------|
| `alice_worker` | `password123` | `group:employee` | `product:view`, `stock:view`, `stock:manage` |
| `kratos_boss` | `password123` | `group:manager` | employee + `product:manage`, `user:manage`, `audit:view`, `report:view` |

| Scope | Allows |
|-------|--------|
| `product:view` | List / get products |
| `product:manage` | Create / update / delete products |
| `stock:view` | History / alerts |
| `stock:manage` | Stock movements |
| `report:view` | Reports API + UI |
| `audit:view` | Audit API + UI |
| `user:manage` | Users admin UI/API (`/users`) |

UI login: http://localhost:5000/auth/login-page → Keycloak.

---

## 4. JWT + curl (professor demo)

### Get an access token

```bash
TOKEN=$(curl -sS -X POST \
  'http://localhost:8080/realms/inventory-realm/protocol/openid-connect/token' \
  -d 'client_id=flask-backend' \
  -d 'grant_type=password' \
  -d 'username=kratos_boss' \
  -d 'password=password123' \
  -d 'scope=openid' \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")

echo "$TOKEN"
```

Employee token (view-only products):

```bash
TOKEN=$(curl -sS -X POST \
  'http://localhost:8080/realms/inventory-realm/protocol/openid-connect/token' \
  -d 'client_id=flask-backend' \
  -d 'grant_type=password' \
  -d 'username=alice_worker' \
  -d 'password=password123' \
  -d 'scope=openid' \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")
```

### Decode JWT claims (no verify)

```bash
python3 - <<'PY'
import os, base64, json, time
tok = os.environ["TOKEN"]
payload = tok.split(".")[1] + "=" * (-len(tok.split(".")[1]) % 4)
claims = json.loads(base64.urlsafe_b64decode(payload))
print("user:", claims.get("preferred_username"))
print("exp:", claims.get("exp"), "expired:", claims.get("exp", 0) < time.time())
print("roles:", claims.get("realm_access", {}).get("roles"))
PY
```

### Products API

```bash
# List (needs product:view)
curl -sS -H "Authorization: Bearer $TOKEN" \
  http://localhost:5000/api/products | python3 -m json.tool

# Get one (needs product:view)
curl -sS -H "Authorization: Bearer $TOKEN" \
  http://localhost:5000/api/products/1 | python3 -m json.tool

# Create (needs product:manage — kratos_boss OK, alice_worker → 403)
curl -sS -w '\nHTTP %{http_code}\n' -X POST \
  http://localhost:5000/api/products \
  -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{
    "name": "Demo Product",
    "sku": "DEMO-001",
    "price": 49.99,
    "description": "Created via curl + JWT",
    "category": "Test",
    "qty": 20,
    "min_stock": 5
  }'

# Update (needs product:manage)
curl -sS -X PUT http://localhost:5000/api/products/1 \
  -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{"name":"Demo Product Updated","price":59.99}'

# Delete (needs product:manage)
curl -sS -w '\nHTTP %{http_code}\n' -X DELETE \
  -H "Authorization: Bearer $TOKEN" \
  http://localhost:5000/api/products/1
```

Employee create → expected:

```json
{"message":"Missing required scope: product:manage"}
```
HTTP **403**

### Stock API

```bash
# Movement (needs stock:manage)
curl -sS -X POST http://localhost:5000/api/stock/movement \
  -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{"product_id":1,"type":"entry","qty_change":5,"notes":"curl demo","user":"demo"}'

# History / alerts (needs stock:view)
curl -sS -H "Authorization: Bearer $TOKEN" http://localhost:5000/api/stock/history
curl -sS -H "Authorization: Bearer $TOKEN" http://localhost:5000/api/stock/alerts
```

### Reports / audit / health / metrics

```bash
# Reports (needs report:view — manager)
curl -sS -H "Authorization: Bearer $TOKEN" http://localhost:5000/api/reports/critical-stock
curl -sS -H "Authorization: Bearer $TOKEN" http://localhost:5000/api/reports/top-products
curl -sS -H "Authorization: Bearer $TOKEN" http://localhost:5000/api/reports/recent-movements

# Audit (needs audit:view — manager)
curl -sS -H "Authorization: Bearer $TOKEN" http://localhost:5000/api/audit

# Health (JWT required by route)
curl -sS -H "Authorization: Bearer $TOKEN" http://localhost:5000/health

# Metrics (no JWT)
curl -sS http://localhost:5000/metrics | head
```

### Use a token from the Users UI

1. Login as `kratos_boss`
2. **Usuarios** → create user or **Gestionar** → **Generar JWT**
3. Expand **Más info — ver access_token**, copy token
4. `export TOKEN='eyJ...'` then run the curls above

---

## 5. User admin (`user:manage`)

### UI

| Path | Action |
|------|--------|
| http://localhost:5000/users | List users |
| http://localhost:5000/users/new | Create user (always mints JWT; shown under Más info) |
| http://localhost:5000/users/`<id>` | Edit roles + emit JWT with password |

### API

```bash
# List
curl -sS -H "Authorization: Bearer $TOKEN" http://localhost:5000/api/users | python3 -m json.tool

# Create (+ JWT in response)
curl -sS -X POST http://localhost:5000/api/users \
  -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{
    "username": "demo_user",
    "email": "demo@example.com",
    "firstName": "Demo",
    "lastName": "User",
    "password": "password123",
    "roles": ["group:employee"]
  }' | python3 -m json.tool

# Set roles (real-time in Keycloak; sessions logged out)
curl -sS -X PUT http://localhost:5000/api/users/<USER_ID>/roles \
  -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{"roles":["group:manager"]}'

# Issue JWT for existing user
curl -sS -X POST http://localhost:5000/api/users/<USER_ID>/token \
  -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{"password":"password123"}' | python3 -m json.tool
```

Requires Keycloak admin credentials in `.env` (`KEYCLOAK_USER` / `KEYCLOAK_PASSWORD`).

---

## 6. Tests

### Unit / API / users (image or local venv)

```bash
docker build -t manage-system:local .
docker run --rm -e DATABASE_URL=sqlite:///:memory: manage-system:local \
  pytest tests/test_products.py tests/test_stock.py tests/test_users.py -v --tb=short

docker run --rm -e DATABASE_URL=sqlite:///:memory: manage-system:local \
  pytest tests/test_contract.py -v --tb=short
```

### Data / migrations (needs Postgres)

```bash
docker compose -f docker-compose.ci.yml up -d db
# wait until ready, then:
docker run --rm --network manage-system_default \
  -e DATABASE_URL=postgresql://postgres:ci_password@db:5432/inventory_db \
  -e FLASK_APP=app.main -e PYTHONPATH=/app \
  manage-system:local \
  bash -lc 'flask db upgrade && pytest tests/data/ -v --tb=short'
```

(Adjust network/project name if using `-p` project prefix.)

### Coverage

```bash
docker run --rm -e DATABASE_URL=sqlite:///:memory: manage-system:local \
  pytest tests/ -m 'not e2e' --cov=app --cov-report=term-missing --tb=short
```

### E2E (Playwright)

```bash
docker compose -f docker-compose.ci.yml up -d --build --wait --wait-timeout 600
docker compose -f docker-compose.ci.yml exec -T web flask db upgrade
COMPOSE_FILE=docker-compose.ci.yml bash scripts/prepare-keycloak-e2e.sh

docker run --rm --network host \
  -v "$PWD:/app" -w /app \
  -e PYTHONPATH=/app \
  -e E2E_BASE_URL=http://localhost:5000 \
  -e E2E_ALICE_USER=alice_worker -e E2E_ALICE_PASSWORD=password123 \
  -e E2E_MANAGER_USER=kratos_boss -e E2E_MANAGER_PASSWORD=password123 \
  mcr.microsoft.com/playwright/python:v1.60.0-jammy \
  bash -lc 'pip install -q -r requirements.txt && pytest tests/e2e -m e2e -v --tb=short'
```

Or compose profile (full stack):

```bash
docker compose --profile e2e run --rm e2e
```

### Full matrix

```bash
bash scripts/run-full-test-suite.sh

# Skip slow stages
RUN_E2E=false RUN_STACK=false bash scripts/run-full-test-suite.sh
```

### Security (pip-audit only)

```bash
docker run --rm manage-system:local \
  bash -lc 'pip install -q pip-audit && pip-audit -r requirements.txt'
```

---

## 7. k6

Requires full stack up, migrations, and prepared Keycloak users:

```bash
docker compose up -d --build
docker compose exec web flask db upgrade
COMPOSE_FILE=docker-compose.yml bash scripts/prepare-keycloak-e2e.sh
```

### Smoke (3 iterations)

```bash
docker run --rm --network host \
  -v "$PWD:/app" -w /app \
  -e BASE_URL=http://localhost:5000 \
  -e KEYCLOAK_URL=http://localhost:8080 \
  -e KC_USERNAME=kratos_boss \
  -e KC_PASSWORD=password123 \
  grafana/k6:0.53.0 run tests/k6/smoke-test.js
```

### Load / stress

```bash
# Native k6 (if installed)
BASE_URL=http://localhost:5000 \
KEYCLOAK_URL=http://localhost:8080 \
KC_USERNAME=kratos_boss KC_PASSWORD=password123 \
k6 run tests/k6/load-test.js

BASE_URL=http://localhost:5000 PRODUCT_IDS=1,2,3 \
k6 run tests/k6/stress-test.js

# Via Docker
docker run --rm --network host -v "$PWD:/app" -w /app \
  -e BASE_URL=http://localhost:5000 \
  -e KEYCLOAK_URL=http://localhost:8080 \
  -e KC_USERNAME=kratos_boss -e KC_PASSWORD=password123 \
  grafana/k6:0.53.0 run tests/k6/load-test.js
```

---

## 8. OWASP ZAP + pip-audit

```bash
# App should be up
docker compose up -d web db keycloak

bash scripts/run-security-scan.sh
```

Or manually:

```bash
docker compose --profile security run --rm zap
docker compose --profile security run --rm pip-audit
ls -la security-reports/
```

Reports: `security-reports/zap-baseline-report.html` (and JSON).

---

## 9. Observability

```bash
bash scripts/start-observability.sh
# or: docker compose up -d --build

docker compose exec web flask db upgrade
COMPOSE_FILE=docker-compose.yml bash scripts/prepare-keycloak-e2e.sh
bash scripts/verify-stack.sh
```

| Check | URL |
|-------|-----|
| Grafana health | http://localhost:3000/api/health |
| Prometheus | http://localhost:9090/-/healthy |
| Alertmanager | http://localhost:9093/-/healthy |
| Loki | http://localhost:3100/ready |
| Tempo | http://localhost:3200/ready |
| Alloy | http://localhost:12345/-/healthy |

Grafana dashboards (provisioned): Aplicación, Infraestructura, Negocio, Seguridad.

---

## 10. Jenkins

```bash
docker compose --profile jenkins up -d --build jenkins
```

Open http://localhost:8090 (Casc / no setup wizard).

**Pipeline job**

1. New Item → Pipeline → `manage-system`
2. Pipeline script from SCM → Git → repo URL (or local `file:///workspace` bind-mount setup)
3. Branch `dev`, Script Path `Jenkinsfile`

Stages: Build → Tests (parallel) → Coverage → Security → E2E → Full stack + k6 → Docker image.

Local helper (if present):

```bash
bash scripts/jenkins-docker.sh docker ps
```

---

## 11. Teardown / cleanup

```bash
# Full stack
docker compose down -v --remove-orphans

# CI stack
docker compose -f docker-compose.ci.yml down -v --remove-orphans

# Free host ports 5000/8080/5432 from stale CI projects
bash scripts/ci-free-host-ports.sh

# Remove local image tag
docker rmi manage-system:local 2>/dev/null || true
```

---

## 12. Cloudflare tunnel (share a live demo URL)

Exposes the app (and Keycloak, and Grafana if it's running) on free, random `*.trycloudflare.com` URLs — no account, no domain. `localhost` keeps working normally the entire time this is active.

```bash
# Stack must already be up (at minimum: web + keycloak)
docker compose up -d web keycloak          # add "grafana" too if you want it tunneled

# Start tunnels + reconfigure Keycloak's OAuth client (redirect/logout URIs)
bash scripts/cloudflare-tunnel.sh

# Reprint the URLs anytime
bash scripts/cloudflare-tunnel.sh status

# Tear down tunnels and restore localhost-only config
bash scripts/cloudflare-tunnel.sh stop
```

Share the printed **App** URL. Demo login: `kratos_boss` / `password123` (manager) or `alice_worker` / `password123` (employee). Grafana (if tunneled) requires a real login: `admin` / whatever's in `GRAFANA_ADMIN_PASSWORD` (defaults to `admin`).

Notes:
- Downloads `cloudflared` into `.tools/` on first run (gitignored)
- Generates `.env.cloudflare` (gitignored, deleted on `stop`) with the public URLs; applied via **two** `--env-file` flags — `docker compose --env-file .env --env-file .env.cloudflare ...` — so `.env.cloudflare` only overrides the handful of Keycloak/Grafana variables that need to point at the tunnel, everything else still comes from `.env`
- Keycloak's `flask-backend` client gets **both** the tunnel URL and `localhost` registered as valid redirect/logout targets at the same time — that's what keeps `localhost:5000` working while a tunnel is active
- `stop` resets Keycloak back to `localhost`-only and deletes `.env.cloudflare` — nothing is left pointing at a dead tunnel URL
- Quick tunnel URLs change every time you run `start`, so start it shortly before you actually need to share it

---

## Quick professor script (JWT → view → create product)

```bash
# 0) Stack + schema + Keycloak users
docker compose up -d --build
docker compose exec web flask db upgrade
COMPOSE_FILE=docker-compose.yml bash scripts/prepare-keycloak-e2e.sh

# 1) Token as manager
TOKEN=$(curl -sS -X POST \
  'http://localhost:8080/realms/inventory-realm/protocol/openid-connect/token' \
  -d 'client_id=flask-backend' -d 'grant_type=password' \
  -d 'username=kratos_boss' -d 'password=password123' -d 'scope=openid' \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")

# 2) View products
curl -sS -H "Authorization: Bearer $TOKEN" http://localhost:5000/api/products | python3 -m json.tool

# 3) Add product
curl -sS -X POST http://localhost:5000/api/products \
  -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d '{"name":"Professor Demo","sku":"PROF-001","price":10,"qty":5,"min_stock":1,"category":"Demo"}' \
  | python3 -m json.tool
```
