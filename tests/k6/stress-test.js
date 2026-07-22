import http from 'k6/http';
import { check, sleep } from 'k6';
import { textSummary } from 'https://jslib.k6.io/k6-summary/0.0.2/index.js';
import { fetchAccessToken } from './auth.js';

const BASE_URL = __ENV.BASE_URL || 'http://localhost:5000';
const PRODUCT_IDS = (__ENV.PRODUCT_IDS || '1,2,3,4,5').split(',').map(Number);
const MOVEMENT_TYPES = ['entry', 'exit'];

export const options = {
  scenarios: {
    stock_movement_stress: {
      executor: 'ramping-vus',
      startVUs: 0,
      stages: [
        { duration: '30s', target: 20 },
        { duration: '30s', target: 50 },
        { duration: '30s', target: 100 },
        { duration: '30s', target: 150 },
        { duration: '20s', target: 0 },
      ],
      gracefulRampDown: '10s',
    },
  },
  thresholds: {
    http_req_duration: ['p(95)<1000'],
    http_req_failed: ['rate<0.05'],
  },
};

function buildPayload() {
  return JSON.stringify({
    product_id: PRODUCT_IDS[Math.floor(Math.random() * PRODUCT_IDS.length)],
    type: MOVEMENT_TYPES[Math.floor(Math.random() * MOVEMENT_TYPES.length)],
    qty_change: Math.floor(Math.random() * 3) + 1,
    notes: 'k6 stress test',
    user: 'k6-load-tester',
  });
}

export function setup() {
  return { token: fetchAccessToken() };
}

export default function (data) {
  const res = http.post(`${BASE_URL}/api/stock/movement`, buildPayload(), {
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${data.token}`,
    },
  });

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
