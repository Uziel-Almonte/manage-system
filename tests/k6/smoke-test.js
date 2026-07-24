import http from 'k6/http';
import { check } from 'k6';
import { fetchAccessToken } from './auth.js';

const BASE_URL = __ENV.BASE_URL || 'http://localhost:5000';

export const options = {
  vus: 1,
  iterations: 3,
  thresholds: {
    http_req_failed: ['rate<0.01'],
    checks: ['rate>0.99'],
  },
};

export function setup() {
  return { token: fetchAccessToken() };
}

export default function (data) {
  const headers = { Authorization: `Bearer ${data.token}` };

  const products = http.get(`${BASE_URL}/api/products`, { headers });
  check(products, {
    'products status 200': (r) => r.status === 200,
  });

  const metrics = http.get(`${BASE_URL}/metrics`);
  check(metrics, {
    'metrics status 200': (r) => r.status === 200,
    'metrics has flask counters': (r) => r.body && r.body.includes('flask_http'),
  });
}
