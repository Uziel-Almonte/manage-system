# Performance Tests (Day 33) — k6

k6 es un binario único (Go), no requiere JVM ni Node para ejecutarse — solo lo necesitas para escribir los scripts en JS (ES2015+, subset soportado por k6).

## 1. Instalación de k6

### Windows
```powershell
winget install k6 --source winget
```

### Docker (sin instalar nada)
```bash
docker pull grafana/k6
```

Verifica la instalación:
```bash
k6 version
```

## 2. Configuración

Ambos scripts leen la URL base desde la variable de entorno `BASE_URL` (por defecto `http://localhost:8000`, típico de una API Python con FastAPI/Flask — ajústalo si tu servidor corre en otro puerto).

Rutas usadas (según el OpenAPI del proyecto):
- `GET /api/products`
- `POST /api/stock/movement` con body `{ product_id, type, qty_change, notes, user }`

**Nota sobre auth:** estos endpoints no llevan autenticación en los tests porque el login pasa por Keycloak (`/auth/login`, `/auth/callback`), que queda fuera del alcance de un test de carga simple. Si en tu entorno estos endpoints SÍ están protegidos detrás de Keycloak, necesitarás obtener un token (client credentials grant, típicamente) antes de correr k6 y mandarlo como header `Authorization: Bearer <token>` en cada request — avísame si es el caso y lo agrego.

**Nota sobre `product_id`:** el stress test usa por defecto los IDs `1,2,3,4,5`. Si tu base de pruebas no tiene productos con esos IDs, el endpoint devolverá `422 Unprocessable Content` (definido en el OpenAPI) en vez de procesar el movimiento. Puedes sobreescribirlos con `PRODUCT_IDS=10,11,12 k6 run stress-test.js`.

## 3. Ejecutar los tests y guardar el reporte

```bash
# Load test — GET /api/products, 50 usuarios concurrentes
set BASE_URL=http://localhost:5000 && k6 run load-test.js
k6 run --vus 1 --iterations 3 load-test.js

# Stress test — POST /api/stock/movement, carga creciente hasta el punto de quiebre
BASE_URL=http://localhost:8000 PRODUCT_IDS=1,2,3 k6 run stress-test.js
```

Cada script genera automáticamente (vía `handleSummary`) dos reportes en `./reports/`:
- `*-summary.json` → métricas completas (p90/p95/p99, throughput, error rate, etc.) en JSON
- `*-summary.txt` → resumen legible en texto plano

También puedes usar el script `run-tests.sh` para correr ambos seguidos y timestamped:
```bash
./run-tests.sh
```

## 4. Qué mirar en el reporte

- `http_req_duration` (avg, p95, p99) → tiempo de respuesta
- `http_reqs` → throughput (requests/segundo, campo `rate`)
- `http_req_failed` → tasa de error (debería ser ~0%)
- `vus_max` → confirma que llegaste a los 50 VUs (load) o al pico de stress
