# Installation

You need Docker with Compose, and a copy of this repository. The application, database, and Keycloak start together.

## 1. Configure environment

```bash
cp .env.example .env
```

Edit `.env` and set:

- `POSTGRES_PASSWORD` and the same password inside `DATABASE_URL`
- `KEYCLOAK_USER` and `KEYCLOAK_PASSWORD` (Keycloak admin)
- `FLASK_SECRET_KEY` (signs the session cookie)
- `GRAFANA_ADMIN_USER` and `GRAFANA_ADMIN_PASSWORD`

Use the same password in `POSTGRES_PASSWORD` and `DATABASE_URL`. The hostname in `DATABASE_URL` stays `db`, which is the Compose service name.

## 2. Start the stack

```bash
docker compose up -d --build
docker compose exec web flask db upgrade
```

The web image runs the Flask development server and mounts the working tree, so code edits are picked up by restarting the `web` service.

On a Podman host, point Alloy at the Podman API socket before starting:

```bash
export DOCKER_SOCK="${XDG_RUNTIME_DIR}/podman/podman.sock"
```

## 3. Open the application

| Service | URL |
|---------|-----|
| Application | http://localhost:5000 |
| API docs | http://localhost:5000/docs |
| Keycloak | http://localhost:8080 |
| Grafana | http://localhost:3000 |
| Prometheus | http://localhost:9090 |

Sign in from the application login page. The realm import creates:

| User | Password | Role |
|------|----------|------|
| `alice_worker` | `password123` | employee |
| `kratos_boss` | `password123` | manager |

If a test run reset those passwords, they are `password123`. A fresh import uses the passwords stored in `keycloak/realm-export.json` until `scripts/prepare-keycloak-e2e.sh` sets them.

## 4. Staging

Staging runs the built image with Gunicorn, health checks, and a separate Keycloak database. It uses the same host ports as the local stack, so stop the local stack first.

```bash
docker compose down
bash scripts/run-staging-qa.sh
```

That script creates `.env` from the example when it is missing, starts `docker-compose.staging.yml`, prepares the two test users, runs the Playwright suite, and writes an OWASP ZAP baseline report under `security-reports/`.

To start staging without the test run:

```bash
docker compose -f docker-compose.staging.yml -p manage-system-staging up -d --build
```

## 5. Tests

Fast tests (unit, API, data) need only Postgres:

```bash
docker compose -f docker-compose.ci.yml up -d db
export DATABASE_URL=postgresql://postgres:ci_password@localhost:5432/inventory_db
export FLASK_APP=app.main
export PYTHONPATH=.
pip install -r requirements.txt
flask db upgrade
pytest tests/ -m "not e2e" -v
```

The full matrix, including HTML and JUnit reports under `reports/`, is:

```bash
bash scripts/run-full-test-suite.sh
```

## 6. Stop

```bash
docker compose down
docker compose -f docker-compose.staging.yml -p manage-system-staging down
```

Add `-v` when you also want to delete database volumes.
