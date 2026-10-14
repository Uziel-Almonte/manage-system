# manage-system

Inventory management system with Flask, PostgreSQL, Keycloak RBAC, observability (Grafana LGTM), and full CI/CD.

## Quick start

```bash
cp .env.example .env   # edit passwords if needed
docker compose up -d --build
docker compose exec web flask db upgrade
```

| Service | URL |
|---------|-----|
| Flask app | http://localhost:5000 |
| Keycloak | http://localhost:8080 |
| Grafana | http://localhost:3000 |
| Prometheus | http://localhost:9090 |
| Jenkins (optional) | http://localhost:8090 |

## Running tests

### Fast (unit + API + data, no Docker stack)

```bash
pip install -r requirements.txt
export DATABASE_URL=postgresql://postgres:ci_password@localhost:5432/inventory_db
docker compose -f docker-compose.ci.yml up -d db
flask db upgrade
pytest tests/ -m "not e2e" -v
```

### E2E (Playwright)

```bash
docker compose -f docker-compose.ci.yml up -d --build
bash scripts/wait-for-services.sh
docker compose -f docker-compose.ci.yml exec -T web flask db upgrade
bash scripts/prepare-keycloak-e2e.sh
pytest tests/e2e -m e2e -v
```

Or via Docker profile:

```bash
docker compose --profile e2e run --rm e2e
```

### Everything (full matrix)

Runs unit, API, data, coverage, pip-audit, E2E, observability health checks, and k6 smoke. JUnit XML, coverage HTML, and the k6 summary are written under `reports/` (open `reports/index.html`).

```bash
bash scripts/run-full-test-suite.sh
```

Skip slow stages:

```bash
RUN_E2E=false RUN_STACK=false bash scripts/run-full-test-suite.sh
```

### Verify observability stack only

```bash
docker compose up -d --build
docker compose exec web flask db upgrade
bash scripts/prepare-keycloak-e2e.sh
bash scripts/verify-stack.sh
```

Checks Flask, Keycloak, Prometheus, Grafana (4 dashboards), Loki, Tempo, Alertmanager, Alloy, and authenticated API access.

### k6 load / smoke

```bash
# Quick smoke (3 iterations)
docker run --rm --network host -v "$PWD:/app" -w /app \
  -e BASE_URL=http://localhost:5000 grafana/k6:0.53.0 run tests/k6/smoke-test.js

# Full load test
BASE_URL=http://localhost:5000 k6 run tests/k6/load-test.js
```

## Jenkins (Day 40)

Start Jenkins with Docker socket access (runs pipelines on the host Docker engine):

```bash
docker compose --profile jenkins up -d --build jenkins
```

Open http://localhost:8090 — no setup wizard (plugins pre-installed).

Create a **Pipeline** job:

1. **New Item** → Pipeline → name `manage-system`
2. **Pipeline** → Definition: *Pipeline script from SCM*
3. SCM: Git → your repo URL → branch `dev`
4. Script Path: `Jenkinsfile`

Or for local testing without Git remote:

1. Definition: *Pipeline script*
2. Paste the contents of `Jenkinsfile`, or use *Pipeline script from SCM* with a local path via a bare repo.

### Jenkins pipeline stages

| Stage | What it runs |
|-------|----------------|
| Build | Docker build + import check |
| Tests (parallel) | Unit, API/contract, data/migrations |
| Coverage | `pytest -m "not e2e"` with coverage |
| Security | pip-audit |
| E2E | Playwright via `docker-compose.ci.yml` |
| Full stack + k6 | All services, `verify-stack.sh`, k6 smoke |
| Docker image | Final image build |

## GitHub Actions

CI runs on push/PR to `main` and `dev` via `.github/workflows/ci.yml` (same test matrix as Jenkins, minus full observability stage).

## Keycloak

Navigate to http://localhost:8080 (admin credentials in `.env`).

Test users (realm `inventory-realm`):

| User | Password | Role |
|------|----------|------|
| `alice_worker` | `password123` | employee |
| `kratos_boss` | `password123` | manager |

OAuth client: `flask-backend` — redirect URI `http://localhost:5000/auth/callback`

## Observability

Grafana ships with four provisioned dashboards:

- **Aplicación** — latency, throughput, errors
- **Infraestructura** — CPU, memory, DB pool
- **Negocio** — products and stock movements
- **Seguridad** — auth failures, invalid tokens

Start only observability helpers:

```bash
bash scripts/start-observability.sh
```

## Staging

Same host ports as the local stack. Stop the local stack first. The staging file runs Gunicorn from the built image, checks health, and keeps Keycloak in its own database.

```bash
bash scripts/run-staging-qa.sh
```

The script starts staging, runs the Playwright suite against http://localhost:5000, and writes an OWASP ZAP baseline report to `security-reports/staging-zap-baseline.html`.

## Documentation

| Document | Contents |
|----------|----------|
| [docs/INSTALL.md](docs/INSTALL.md) | Install and start with Compose |
| [docs/requirements.md](docs/requirements.md) | Functional and non-functional requirements |
| [docs/architecture.md](docs/architecture.md) | Context, container, login, and data diagrams |
| [docs/DEMO.md](docs/DEMO.md) | Live demo script |
| [docs/BRANCHES.md](docs/BRANCHES.md) | `main`, `dev`, and `feature/*` |
| [docs/APP_FLOW.md](docs/APP_FLOW.md) | Request and data flow |
| [docs/FULL_APP_GUIDE.md](docs/FULL_APP_GUIDE.md) | File-by-file walkthrough |
| [docs/contributions.md](docs/contributions.md) | Commit, pull request, and issue counts |
| [docs/SONARCLOUD.md](docs/SONARCLOUD.md) | Optional SonarCloud hook (not part of CI) |

## Project layout

```
app/                  Flask application
tests/                unit, contract, data, e2e, k6
observability/        Prometheus, Grafana, Loki, Tempo, Alloy configs
jenkins/              Jenkins image + plugins
scripts/              test runners and stack verification
docker-compose.yml    full stack
docker-compose.staging.yml  staging stack (Gunicorn, isolated Keycloak DB)
docker-compose.ci.yml minimal stack for CI/E2E
Jenkinsfile           Jenkins pipeline
```
