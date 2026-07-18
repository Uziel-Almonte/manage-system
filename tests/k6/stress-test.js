import http from 'k6/http';
import { check, sleep } from 'k6';
import { textSummary } from 'https://jslib.k6.io/k6-summary/0.0.2/index.js';

const BASE_URL = __ENV.BASE_URL || 'http://localhost:5000';

// Stress test: empuja la carga por encima de lo normal para encontrar
// el punto de quiebre (breaking point) del endpoint de escritura.
export const options = {
  scenarios: {
    stock_movement_stress: {
      executor: 'ramping-vus',
      startVUs: 0,
      stages: [
        { duration: '30s', target: 20 },   // carga normal
        { duration: '30s', target: 50 },   // carga alta
        { duration: '30s', target: 100 },  // carga de stress
        { duration: '30s', target: 150 },  // por encima de lo esperado
        { duration: '20s', target: 0 },    // recovery
      ],
      gracefulRampDown: '10s',
    },
  },
  thresholds: {
    http_req_duration: ['p(95)<1000'],
    http_req_failed: ['rate<0.05'], // más tolerante que el load test, es stress
  },
};

// Payload según el schema StockMovement del OpenAPI:
// { product_id (int, requerido), type (string, requerido), qty_change (int, requerido),
//   notes (string, opcional), user (string, opcional) }
//
// IMPORTANTE: ajusta PRODUCT_IDS a IDs que realmente existan en tu base de datos de
// pruebas (si no existen, el endpoint responderá 422 y el test solo medirá el error path).
// Ajusta también los valores válidos de "type" a los que use tu API (aquí se asume IN/OUT).
const PRODUCT_IDS = (__ENV.PRODUCT_IDS || '1,2,3,4,5').split(',').map(Number);
const MOVEMENT_TYPES = ['IN', 'OUT'];

function buildPayload() {
  return JSON.stringify({
    product_id: PRODUCT_IDS[Math.floor(Math.random() * PRODUCT_IDS.length)],
    type: MOVEMENT_TYPES[Math.floor(Math.random() * MOVEMENT_TYPES.length)],
    qty_change: Math.floor(Math.random() * 10) + 1,
    notes: 'k6 stress test',
    user: 'k6-load-tester',
  });
}

export default function () {
  const params = {
    headers: { 'Content-Type': 'application/json' },
  };

  const res = http.post(`${BASE_URL}/api/stock/movement`, buildPayload(), params);

  check(res, {
    'status is 200 or 201': (r) => r.status === 200 || r.status === 201,
    'not unprocessable (422)': (r) => r.status !== 422,
    'no server error (5xx)': (r) => r.status < 500,
  });

  sleep(0.5);
}

export function handleSummary(data) {
  const timestamp = new Date().toISOString().replace(/[:.]/g, '-');
  return {
    stdout: textSummary(data, { indent: ' ', enableColors: true }),
    [`reports/stress-test-${timestamp}-summary.json`]: JSON.stringify(data, null, 2),
    [`reports/stress-test-${timestamp}-summary.txt`]: textSummary(data, { indent: ' ', enableColors: false }),
  };
}
