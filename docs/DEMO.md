# Live demo script

Run this against a stack started with the installation guide. Budget about ten minutes. Use a browser window the audience can see, and keep Grafana open in a second tab.

## Before the room

1. `docker compose up -d --build` and `docker compose exec web flask db upgrade`.
2. Open http://localhost:5000/auth/login-page and confirm Keycloak answers at http://localhost:8080.
3. Sign in once as `kratos_boss` / `password123`, then sign out, so the first live login is not spent on a cold Keycloak start.

## 1. Employee session

1. Open http://localhost:5000 and choose **Continuar con Keycloak**.
2. Sign in as `alice_worker` / `password123`.
3. On the dashboard, point out product totals, critical stock, and the recent movements table.
4. Open **Productos**. Search for a SKU and sort a column. The table updates without a full page reload.
5. Open **Inventario**, then **Registrar Movimiento**. Record an entry of a few units and show the new quantity and the history row.
6. Show that **Reportes**, **Auditoria**, and **Usuarios** are absent from the sidebar.
7. Sign out.

## 2. Manager session

1. Sign in as `kratos_boss` / `password123`.
2. Open **Productos**, add a product with a new SKU, price, and minimum stock. Confirm the success message and the new row.
3. Try to add the same SKU again and show the duplicate being rejected.
4. Open **Registrar Movimiento** and record an exit. If the exit would pass the available quantity, show the validation error.
5. Open **Reportes** and **Auditoria** and show the movement from the previous step on both screens.
6. Open **Usuarios** and show that accounts come from Keycloak, including the role list.

## 3. API and operations

1. Open http://localhost:5000/docs and expand `GET /api/products`.
2. Open http://localhost:5000/health.
3. In Grafana (http://localhost:3000), open the application dashboard and the business dashboard. Refresh after the product and movement you just created so the panels have new points.
4. Optional: `bash scripts/verify-stack.sh` in a terminal to show every dependency answering.

## If something is slow

Keycloak's first start imports the realm and can take a few minutes. Wait until http://localhost:8080/realms/inventory-realm answers before inviting the room to watch the login.
