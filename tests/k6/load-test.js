import http from 'k6/http';
import { check, sleep } from 'k6';
import { textSummary } from 'https://jslib.k6.io/k6-summary/0.0.2/index.js';
import encoding from 'k6/encoding';

const BASE_URL = __ENV.BASE_URL || 'http://localhost:5000';

// --- Config de Keycloak (todo vía variables de entorno, nada hardcodeado) ---
const KEYCLOAK_URL = __ENV.KEYCLOAK_URL || 'http://localhost:8080';
const REALM = "inventory-realm"       
const CLIENT_ID = "flask-backend" 
const CLIENT_SECRET = "mltoW2hIYbx5HrJhuXC9Gq4RcjoaE2Hg" 
const KC_USERNAME = "kratos_boss"   
const KC_PASSWORD = "test"  

// Load test: carga "normal esperada" sostenida — 50 usuarios concurrentes
export const options = {
  scenarios: {
    products_load: {
      executor: 'ramping-vus',
      startVUs: 0,
      stages: [
        { duration: '30s', target: 50 },  // ramp-up gradual a 50 VUs
        { duration: '1m', target: 50 },   // sostiene 50 VUs
        { duration: '15s', target: 0 },   // ramp-down
      ],
      gracefulRampDown: '5s',
    },
  },
  thresholds: {
    http_req_duration: ['p(95)<500'], // 95% de las respuestas bajo 500ms
    http_req_failed: ['rate<0.01'],   // menos de 1% de errores
  },
};

// setup() corre UNA sola vez, antes de que arranquen los VUs.
// Aquí pedimos el token a Keycloak y lo compartimos con todas las iteraciones.
export function setup() {
  if (!KEYCLOAK_URL || !REALM || !CLIENT_ID || !KC_USERNAME || !KC_PASSWORD) {
    throw new Error(
      'Faltan variables de entorno de Keycloak. Necesitas: KEYCLOAK_URL, REALM, CLIENT_ID, KC_USERNAME, KC_PASSWORD (y CLIENT_SECRET si el client es confidential).'
    );
  }

  const tokenUrl = `${KEYCLOAK_URL}/realms/${REALM}/protocol/openid-connect/token`;

  const payload = {
    grant_type: 'password',
    client_id: CLIENT_ID,
    username: KC_USERNAME,
    password: KC_PASSWORD,
  };

  // Solo se agrega si el client es "confidential" (tiene secret)
  if (CLIENT_SECRET) {
    payload.client_secret = CLIENT_SECRET;
  }

  const res = http.post(tokenUrl, payload, {
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
  });

  check(res, {
    'login a Keycloak exitoso (200)': (r) => r.status === 200,
  });

  if (res.status !== 200) {
    throw new Error(`No se pudo obtener el token de Keycloak. Status: ${res.status}, body: ${res.body}`);
  }

  const body = res.json();
  const accessToken = body.access_token;

  if (!accessToken) {
    throw new Error(`La respuesta de Keycloak no trajo access_token: ${JSON.stringify(body)}`);
  }

  const payloadBase64 = accessToken.split('.')[1];
  const payloadJson = encoding.b64decode(payloadBase64.replace(/-/g, '+').replace(/_/g, '/'), 'std', 's');
  console.log(`Token payload: ${payloadJson}`);

  return { token: accessToken };
}

// default() corre por cada VU/iteración. Recibe lo que devolvió setup().
export default function (data) {
  const res = http.get(`${BASE_URL}/api/products`, {
    headers: {
      Authorization: `Bearer ${data.token}`,
    },
  });

  check(res, {
    'status is 200': (r) => r.status === 200,
    'response has body': (r) => r.body && r.body.length > 0,
  });

  // Log temporal para debug: solo si falla
  if (res.status !== 200) {
    console.log(`Status: ${res.status} | Body: ${res.body}`);
  }

  sleep(1);
}

export function handleSummary(data) {
  const timestamp = new Date().toISOString().replace(/[:.]/g, '-');
  return {
    stdout: textSummary(data, { indent: ' ', enableColors: true }),
    [`reports/load-test-${timestamp}-summary.json`]: JSON.stringify(data, null, 2),
    [`reports/load-test-${timestamp}-summary.txt`]: textSummary(data, { indent: ' ', enableColors: false }),
  };
}