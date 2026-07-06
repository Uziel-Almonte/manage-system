# Day 32 — Security Test Findings

**Scan date:** 2026-07-06  
**Target (staging/local):** `http://web:5000` (Docker internal URL; equivalent to `http://localhost:5000` on the host)  
**Tools:** OWASP ZAP baseline (`zaproxy/zap-stable` 2.17.0), `pip-audit`

## How to re-run

```bash
docker compose up -d
./scripts/run-security-scan.sh
```

Or run each scan separately:

```bash
docker compose --profile security run --rm zap
docker compose --profile security run --rm pip-audit
```

Raw reports are written to `security-reports/` (gitignored):

| File | Description |
|------|-------------|
| `zap-baseline-report.html` | Full ZAP HTML report |
| `zap-baseline-report.json` | Machine-readable ZAP findings |
| `pip-audit-report.json` | Dependency audit (JSON) |

Override the ZAP target (e.g. real staging):

```bash
SECURITY_SCAN_TARGET=https://staging.example.com docker compose --profile security run --rm zap
```

---

## Scan limitations

The ZAP **baseline** scan is passive and **unauthenticated**. It only crawls public URLs reachable without logging in (login page, redirects, OpenAPI docs, etc.). It does **not** exercise protected routes (`/products`, `/stock`, `/audit`, API mutations) behind Keycloak. A full authenticated scan would need a ZAP context file and session cookies — out of scope for Day 32.

---

## OWASP ZAP baseline — summary

| Result | Count |
|--------|------:|
| **FAIL** | 0 |
| **WARN** | 13 |
| **PASS** | 54 |

No critical/high-severity failures were reported. Warnings are mostly missing security headers and dev-environment configuration. **None were fixed in this sprint** — documented below for follow-up.

### Findings (not fixed)

| # | Alert | Risk | Where seen | Notes / suggested fix |
|---|-------|------|------------|------------------------|
| 1 | Content Security Policy (CSP) Header Not Set | Medium | `/`, `/auth/login-page` | Add a `Content-Security-Policy` header via Flask middleware or reverse proxy. Restrict script/style sources; avoid `unsafe-inline` in production. |
| 2 | Cross-Domain Misconfiguration (CORS `*`) | Medium | Multiple routes | App sets `CORS(app, origins="*")` in `app/main.py`. Tighten to known front-end origins in production. |
| 3 | Missing Anti-clickjacking Header | Medium | HTML responses | Set `X-Frame-Options: DENY` or `Content-Security-Policy: frame-ancestors 'none'`. |
| 4 | Sub Resource Integrity (SRI) Missing | Medium | `/`, `/auth/login-page` | External scripts/styles (e.g. CDN assets) lack `integrity` attributes. Pin CDN resources with SRI hashes or self-host. |
| 5 | Big Redirect Detected | Low | `/auth/login` | OAuth redirect to Keycloak may leak path/query in `Location`. Expected for OAuth; review redirect URLs in production. |
| 6 | Cookie without SameSite Attribute | Low | `/auth/login` | Session cookie should use `SameSite=Lax` or `Strict` and `Secure` behind HTTPS. |
| 7 | Cross-Domain JavaScript Source File Inclusion | Low | Login page | Third-party JS (e.g. Swagger UI CDN on `/docs`) loaded without SRI. |
| 8 | Cross-Origin-Embedder-Policy Missing/Invalid | Low | HTML pages | Optional hardening header for cross-origin isolation. |
| 9 | Cross-Origin-Opener-Policy Missing/Invalid | Low | HTML pages | Optional hardening header; set `same-origin` if embedding is not needed. |
| 10 | Permissions Policy Header Not Set | Low | `/`, `/auth/login-page` | Add `Permissions-Policy` to disable unused browser features. |
| 11 | Server Leaks Version Information | Low | All responses | Werkzeug/Flask `Server` header exposes stack info. Disable or strip in production (gunicorn + proxy). |
| 12 | X-Content-Type-Options Header Missing | Low | HTML responses | Set `X-Content-Type-Options: nosniff`. |
| 13 | Information Disclosure — Suspicious Comments | Info | HTML/JS | Comments in templates or static assets may hint at internals. Review before production. |
| 14 | Non-Storable / Storable Cacheable Content | Info | Various | Cache-Control behavior on redirects and static-like responses. Tune for sensitive vs public pages. |

### Context-specific observations

- **HTTP only:** Local dev uses `http://`. Production should terminate TLS at a load balancer; several cookie/header warnings assume HTTPS.
- **Keycloak OAuth:** Redirects to `localhost:8080` are expected in dev; ZAP flags redirect chains as informational/low risk.
- **Default secret:** `FLASK_SECRET_KEY` fallback in code is a separate concern; not surfaced by this passive scan but should not be used in production.

---

## pip-audit — Python dependencies

**Result:** No known vulnerabilities found in `requirements.txt` (all resolved packages checked).

Sample of audited packages (full list in `pip-audit-report.json`):

- flask 3.1.3
- werkzeug 3.1.8
- cryptography 49.0.0
- pyjwt 2.13.0
- requests 2.34.2
- urllib3 2.7.0
- sqlalchemy 2.0.51
- playwright 1.60.0 (test-only)

`pip-audit` uses the Python Packaging Advisory Database. Re-run after any dependency bump:

```bash
docker compose --profile security run --rm pip-audit
```

---

## Recommended follow-up (post–Day 32)

1. Add security headers middleware (CSP, X-Frame-Options, X-Content-Type-Options, etc.).
2. Restrict CORS to explicit origins.
3. Use HTTPS + `Secure`/`SameSite` cookies in staging/production.
4. Run ZAP with authentication context before go-live.
5. Add `pip-audit` to CI on every `requirements.txt` change.
