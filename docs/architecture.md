# Architecture

The system is one Flask process that renders HTML and serves a JSON API. PostgreSQL stores inventory data. Keycloak stores users and roles. Grafana reads metrics, logs, and traces produced by the application.

## System context

```mermaid
flowchart LR
  person[Staff browser]
  flask[Flask app]
  kc[Keycloak]
  db[(PostgreSQL)]
  graf[Grafana]

  person -->|HTML and HTMX| flask
  person -->|Login page| kc
  flask -->|OIDC token and Admin API| kc
  flask -->|SQL| db
  kc -->|Realm data| db
  flask -->|Metrics, logs, traces| graf
```

## Containers

`docker-compose.yml` is the local stack. `docker-compose.staging.yml` runs the same services without mounting the source tree. `docker-compose.ci.yml` is the smaller set used by automated tests: Postgres, Keycloak, and Flask.

```mermaid
flowchart TB
  subgraph edge [Host ports]
    web[web :5000]
    keycloak[keycloak :8080]
    grafana[grafana :3000]
  end

  subgraph data [Data]
    db[(db :5432)]
  end

  subgraph telemetry [Telemetry]
    alloy[alloy]
    prometheus[prometheus]
    loki[loki]
    tempo[tempo]
    alertmanager[alertmanager]
  end

  web --> db
  web --> keycloak
  keycloak --> db
  web --> alloy
  alloy --> loki
  alloy --> tempo
  prometheus --> web
  grafana --> prometheus
  grafana --> loki
  grafana --> tempo
  prometheus --> alertmanager
```

In the local and CI stacks Keycloak may share the Postgres instance with the application. Staging creates a separate `keycloak` database on that instance so realm tables are not mixed with inventory tables.

## Sign-in sequence

```mermaid
sequenceDiagram
  participant Browser
  participant Flask
  participant Keycloak

  Browser->>Flask: GET /auth/login
  Flask->>Browser: Redirect to Keycloak authorize URL
  Browser->>Keycloak: Username and password
  Keycloak->>Browser: Redirect to /auth/callback?code=
  Browser->>Flask: GET /auth/callback
  Flask->>Keycloak: Exchange code at token URL
  Keycloak-->>Flask: Access token and userinfo
  Flask->>Browser: Session cookie and redirect to /
```

The session stores the user profile and the scope list. It does not store the raw access token. API calls send `Authorization: Bearer` and are checked again on each request.

## Request path inside Flask

```mermaid
flowchart TD
  http[HTTP request]
  ui{Browser page?}
  session[login_required and require_ui_scope]
  jwt[require_jwt and require_scope]
  handler[Blueprint or page handler]
  db[(SQLAlchemy)]
  audit[Audit listeners]
  http --> ui
  ui -->|yes| session --> handler
  ui -->|no| jwt --> handler
  handler --> db
  db --> audit
```

Page routes live in `app/main.py`. JSON routes live in the blueprints under `app/products`, `app/stock`, `app/reports`, `app/audit`, `app/users`, and `app/auth`.

## Data model

```mermaid
erDiagram
  PRODUCT ||--o{ STOCK_MOVEMENT : has
  PRODUCT ||--o{ AUDIT_LOG : tracked_as
  STOCK_MOVEMENT ||--o{ AUDIT_LOG : tracked_as

  PRODUCT {
    int id
    string sku
    string name
    numeric price
    int qty
    int min_stock
    string status
  }
  STOCK_MOVEMENT {
    int id
    int product_id
    string type
    int prev_qty
    int new_qty
    string notes
  }
  AUDIT_LOG {
    int id
    string entity
    string action
    json changes
  }
```

Users and role mappings are Keycloak entities, not tables in this schema.

## Branch flow

```mermaid
flowchart LR
  feature[feature branch]
  dev[dev]
  main[main]
  feature -->|pull request| dev
  dev -->|pull request| main
```

`dev` is the integration branch named `develop` in the original six-week plan. Short-lived work uses `feature/*`.
