import http from 'k6/http';

const KEYCLOAK_URL = __ENV.KEYCLOAK_URL || 'http://localhost:8080';
const REALM = __ENV.REALM || 'inventory-realm';
const CLIENT_ID = __ENV.CLIENT_ID || 'flask-backend';
const CLIENT_SECRET = __ENV.CLIENT_SECRET || '';
const KC_USERNAME = __ENV.KC_USERNAME || 'kratos_boss';
const KC_PASSWORD = __ENV.KC_PASSWORD || 'password123';

export function fetchAccessToken() {
  const tokenUrl = `${KEYCLOAK_URL}/realms/${REALM}/protocol/openid-connect/token`;
  const payload = {
    grant_type: 'password',
    client_id: CLIENT_ID,
    username: KC_USERNAME,
    password: KC_PASSWORD,
  };

  if (CLIENT_SECRET) {
    payload.client_secret = CLIENT_SECRET;
  }

  const res = http.post(tokenUrl, payload, {
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
  });

  if (res.status !== 200) {
    throw new Error(`Keycloak token request failed (${res.status}): ${res.body}`);
  }

  const accessToken = res.json('access_token');
  if (!accessToken) {
    throw new Error(`Keycloak response missing access_token: ${res.body}`);
  }

  return accessToken;
}
