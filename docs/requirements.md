# Requirements

Inventory management system for a small operation that tracks products, stock movements, and who changed them. People sign in through Keycloak. The same deployment serves the HTML interface and the JSON API.

## Functional requirements

### Identity and access

- A person signs in with Keycloak (OpenID Connect) and lands on the dashboard.
- Signing out clears the application session and the Keycloak session.
- Permissions are scopes, not a single admin flag: `product:view`, `product:manage`, `stock:view`, `stock:manage`, `report:view`, `audit:view`, `user:manage`.
- The employee role (`group:employee`, user `alice_worker`) can view products and view or record stock movements.
- The manager role (`group:manager`, user `kratos_boss`) includes the employee scopes and can manage products, view reports, view the audit log, and manage users.
- Navigation hides links the signed-in user is not allowed to open.
- The JSON API rejects requests that lack a valid Bearer token or the required scope.

### Products

- Create, read, update, and delete products.
- Each product has a name, unique SKU, description, category, price, quantity, minimum stock, and status.
- The product list supports search, sorting, and pagination.
- Duplicate SKUs are rejected by the database.

### Stock

- Record an entry or an exit against a product.
- An exit cannot take quantity below zero.
- The product quantity updates in the same operation as the movement.
- Movement history can be filtered by date range and movement type.
- Products at or below their minimum stock appear as alerts.

### Audit and reports

- Inserts, updates, and deletes on products and stock movements are written to an audit log.
- The audit page and `GET /api/audit` require `audit:view`.
- Reports show critical stock, top products, and recent movements, and require `report:view`.

### Users

- A manager can list, create, and update Keycloak users and their realm roles from the application.
- User records live in Keycloak. The application database does not keep a users table.

### Operations

- `GET /health` reports that the application can reach the database.
- OpenAPI documentation is served at `/docs`.
- Metrics are exposed at `/metrics` when telemetry is enabled.

## Non-functional requirements

| Area | Requirement |
|------|-------------|
| Runtime | Python 3.12, Flask, Gunicorn in staging. PostgreSQL 16 is the system of record. |
| Interface | Server-rendered Jinja2 pages. HTMX updates tables and forms without a separate frontend build. |
| Security | OAuth2/OIDC via Keycloak. API authorization checks the JWT signature against the realm JWKS and then the required scope. Secrets come from the environment, not from source. |
| Data | Schema changes ship as Alembic migrations and apply in order on a fresh database. |
| Auditability | Product and stock changes produce an audit row. Request logs include trace, span, correlation id, user, and endpoint when telemetry is on. |
| Observability | Prometheus, Grafana, Loki, Tempo, Alloy, and Alertmanager start with the full stack. Dashboards cover infrastructure, application, business, and security signals. |
| Performance | k6 load test targets `GET /api/products` at 50 concurrent users. A separate stress test hits `POST /api/stock/movement`. |
| Test | Unit, contract, migration, end-to-end, dependency audit, and load checks are runnable from `scripts/run-full-test-suite.sh` and from GitHub Actions. |
| Delivery | `docker compose up -d --build` starts the local stack. `docker-compose.staging.yml` runs the same services from the built image, with Gunicorn, health checks, and a database reserved for Keycloak. |
| Availability of auth | Browser-facing Keycloak URLs stay on the host name the browser can resolve. Token and JWKS calls from Flask use the Docker network name. |
