# RealAICoach API v1 — Multi-Platform Client Reference

Web-first, API-driven architecture. The web app is the primary client; future
Android/iOS apps consume the exact same backend services with **no code
duplication** — only UI implementation is required on mobile.

## Base URLs

| Contract | Base path | Notes |
|---|---|---|
| Versioned (mobile + new clients) | `/api/v1/*` | Stable v1 contract. Responses carry `X-API-Version: 1`. |
| Legacy (current web) | `/api/*` | Identical handlers. Fully backward compatible. |

Both paths hit the same handlers — `/api/v1/<path>` is transparently mapped to
`/api/<path>` by an outermost ASGI shim, so every security layer (auth gate,
CSRF, WAF, rate limiting, IDOR, sanitization) applies identically.

## Client Handshake

`GET /api/v1/client/bootstrap` (public) — call once on app launch.
Returns: API version, per-platform min supported versions, auth capability map,
feature/config endpoints, i18n endpoints, theming contracts (app `v2-light-dark`,
email `v7-light-dark`), and docs URLs.

## Authentication (shared layer — web, Android, iOS)

- **Web:** httpOnly cookies (`session_token`), CSRF via `X-Requested-With` header on mutating requests.
- **Native:** send `X-Client-Platform: android | ios | expo | mobile | native`
  on auth endpoints → `session_token` + `refresh_token` are returned in the
  response body for secure device storage. Use `Authorization: Bearer <token>` thereafter.
- **Refresh:** `POST /api/v1/auth/token/refresh` with `{"refresh_token": "..."}`.
- **RBAC:** server-authoritative roles/permissions; admin routes deny-by-default.
- **MFA / OTP / Passkeys / OAuth (Google, Microsoft, Apple):** all supported, platform-agnostic.
- Sessions, subscriptions, AI history, uploads, notifications, settings,
  progress and analytics are stored server-side → automatically synchronized
  across all devices for the same account.

## Core surface (v1)

| Area | Endpoint | Auth |
|---|---|---|
| Health | `GET /api/v1/health` | public |
| Bootstrap | `GET /api/v1/client/bootstrap` | public |
| Login | `POST /api/v1/auth/login` | public |
| Register | `POST /api/v1/auth/register` | public |
| Token refresh | `POST /api/v1/auth/token/refresh` | public |
| Current user | `GET /api/v1/auth/me` | session |
| Feature registry | `GET /api/v1/features/registry` | public |
| Global config | `GET /api/v1/config/global` | public |
| i18n languages | `GET /api/v1/i18n/languages` | public |
| Subscription plans | `GET /api/v1/payments/subscriptions/plans` | session |
| Subscription status | `GET /api/v1/payments/subscriptions/status` | session |
| Notifications | `GET /api/v1/notifications` | session |

## Platform conventions

- **Errors:** JSON `{"detail": "...", "code": "..."}` with standard HTTP status codes.
- **Rate limiting:** enforced globally; respect `Retry-After` on 429.
- **Compression:** gzip for responses ≥ 500 bytes.
- **Pagination:** list endpoints accept `page` / `limit` (or cursor params where documented).
- **CSRF:** non-GET requests without browser cookies still require `X-Requested-With: XMLHttpRequest` (or any value).
- **i18n:** auto-translate pipeline; query supported languages via `/api/v1/i18n/languages`.
- **Observability:** all requests traced (OTel) with structured logs and audit trails.

## Machine-readable contracts

- `contracts/v1/*.contract.json` — endpoint contracts consumed by pytest contract tests.
- `GET /api/v1/openapi.json` — full OpenAPI 3 schema (**admin auth required**).
- `GET /api/v1/docs` — Swagger UI (**admin auth required**).

## Client Version Enforcement

Native requests carrying both `X-Client-Platform` (android/ios/expo/mobile/native)
and `X-App-Version` are checked against the DB-backed platform policy
(`client_version_policy` collection, admin-managed, cached 60s):

- Below `min_supported_version` → **`426 Upgrade Required`** with
  `{"code": "CLIENT_UPDATE_REQUIRED", "min_supported_version", "latest_version", "update_url"}`.
- Fail-open: web requests (no platform header), missing `X-App-Version`,
  malformed versions and DB errors never block.
- Always exempt: `/api/health`, `/api/client/bootstrap` (so outdated clients can discover the required version).
- Admin management: `GET /api/v1/admin/client-version-policy`,
  `PUT /api/v1/admin/client-version-policy/{platform}` (platforms: `android`, `ios`, `expo`, `default`; changes audit-logged).

## Regression guarantees

- Legacy `/api/*` paths are untouched — zero changes to existing route modules.
- Contract tests: `backend/tests/test_api_v1_multiplatform_architecture.py`.
