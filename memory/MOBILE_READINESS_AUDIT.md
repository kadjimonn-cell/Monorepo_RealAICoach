# RealAICoach — Mobile-Readiness Audit
Date: 2026-07-17 · Scope: `/app/frontend` (Expo 54 / expo-router 6 / RN 0.81) + backend native-support surface · **Analysis only, no code changed.**

## 0. Headline
The codebase is an Expo *universal* app written almost entirely in React Native primitives with disciplined
`Platform.OS === 'web'` guarding. Static analysis says **~80% of screens should render on native as-is**.
The real blockers are not "web code everywhere" — they are **IAP (no native purchase SDK), native auth QA,
push/build configuration, and per-screen runtime QA** (the app has never been run on a device).

Measured base: 902 TS/TSX files in `app/` + `src/`; **207 route screens**; 9 `_layout.tsx`; `(tabs)` shell with 5 tabs.

---

## 1. Web-only coupling (quantified)

| Signal | Count | Assessment |
|---|---|---|
| Files touching `document.`/`window.` | 296 / 902 (33%) | Most are inside web guards or `typeof window` checks (pattern verified in `api.ts`, `otelClient.ts`, `(tabs)/index.tsx`) |
| `Platform.OS` checks (total occurrences) | 1,333 | Strong cross-platform discipline |
| Files with explicit `Platform.OS === 'web'` guards | 314 | |
| Files with raw `<div>` JSX | 60 | **56/60 also contain web guards** (spot-checks confirm divs rendered only under `Platform.OS === 'web' &&`). Only 4 unguarded: `app/+html.tsx` (web-only by design) + 3 admin panels (`ThreatDetectionPanel`, `EnterpriseSecurityPanel`, `DeploymentOrchestrationPanel`) |
| `localStorage` users | 82 files, **81 guarded** by `typeof window`/`Platform.OS` | AsyncStorage already used as the native path in `api.ts` |
| Direct `react-dom` importers | 2 (`WebPortal.tsx`, `SmartOnboarding.tsx`) | Need native portal alternative or web guard |
| `getUserMedia`/`mediaDevices` | 7 files | Web mic/camera APIs; native needs expo-audio/expo-camera equivalents |

**Web-only libraries** (break or no-op on native):
- `recharts` — 5 admin components only (`GlobalPerformanceSection`, `AIInsightsPanel`, `ASOAnalyticsSection`, `SEODashboardPanel`, `AutomationEnginePanel`). SVG-DOM based; will not render natively.
- `three` — 2 files, isolated to `src/components/fpsGame/` (would need expo-gl; recommend web-only exclusion).
- `@stripe/stripe-js` — 1 importer (web checkout). Native must hand off via `expo-web-browser` (already a dep) or IAP.
- `pdfjs-dist` — dep present, **0 static importers** (likely dynamic/web-only; verify at native QA).
- `web-vitals`, `@opentelemetry/sdk-trace-web` — guarded (`otelClient.ts` returns early when `typeof window === 'undefined'`).
- `compression`, `@expo/ngrok`, `tar`, `undici` — build/dev-server only, harmless.

**Caveat**: "file contains a guard" ≠ "every DOM reference in it is guarded." Static analysis can't prove
runtime safety; a device-run QA pass per screen is mandatory.

**Estimated native breakage**: ~4 unguarded div components + 5 recharts admin panels + fpsGame + 2 react-dom
portals ≈ **12–15 components, heavily concentrated in the admin console**. Core user screens (tabs, chat,
coaching, careers, subscription UI) follow the guarded universal pattern.

---

## 2. Navigation & layout
- expo-router v6 route tree with `(tabs)` shell (index, practice, progress, downloads, profile, admin-console), 9 `_layout.tsx`, 1 modal presentation. **Structure is native-compatible.**
- `app/+native-intent.tsx` **already exists** and normalizes incoming system deep-link paths — good.
- `scheme: "realaicoach"` set → custom-scheme deep links work.
- **Missing**: `ios.associatedDomains` and `android.intentFilters` → no Universal Links / App Links (https://realaicoach.app/... won't open the app). Also needs `apple-app-site-association` + `assetlinks.json` served by the backend/domain.
- `web.output: "server"` affects only the web build; native ignores it. `expo-router.origin: https://realaicoach.app` is set, which native uses to resolve relative fetches — fine, but note API calls go through `resolveRuntimeBaseUrl()` which already supports `EXPO_PUBLIC_BACKEND_URL` for native.
- No web-specific layout primitives in the shell; `AppShell`/`GlobalNavBar` are RN-based (require-cycle warnings exist but are non-blocking).

---

## 3. Native config state (app.json / EAS)
Present ✅:
- `ios.bundleIdentifier: com.realaicoach.app`, buildNumber, `supportsTablet`, infoPlist usage strings (camera, photos, mic, FaceID)
- `android.package: com.realaicoach.app`, versionCode, adaptiveIcon, permissions (CAMERA, RECORD_AUDIO, BIOMETRIC…)
- icon, splash, `expo-local-authentication` + `expo-notifications` plugins
- `eas.json` (development/preview/production profiles) + EAS `projectId` (391b98a8-…)

Missing ❌ for a store-ready EAS build:
1. `ios.associatedDomains` + `android.intentFilters` (universal/app links)
2. Push credentials: APNs key upload to EAS; `google-services.json` for FCM (not in repo); `notification` config (icon/color)
3. `runtimeVersion` + `updates` config (only needed if using EAS Update / OTA)
4. `expo-dev-client` not installed (needed for the `development` profile builds)
5. Store metadata/assets pipeline (screenshots, privacy manifests / `NSPrivacyAccessedAPITypes`)
6. Package version drift warnings (`expo@54.0.34` vs expected `~54.0.36`, expo-font, expo-router) — align before EAS build
7. `expo-av` is deprecated (replaced by expo-audio/expo-video); still works on SDK 54 but plan migration

---

## 4. Auth on native — **mostly already built** (biggest positive surprise)
- Backend `get_current_user` accepts **`Authorization: Bearer <jwt>` first**, cookie fallback (routes/db.py:703).
- Backend login/SSO returns `session_token`/`refresh_token` **in the JSON body** when the client sends `X-Client-Platform: ios|android|native|mobile|expo` (`_allow_native_auth_tokens`, routes/auth.py).
- Frontend `src/services/api.ts` is dual-mode: web = cookie-only (`WEB_COOKIE_ONLY_AUTH`); native = token from AsyncStorage cache, attached as `Bearer` (line 766). `AuthContext` calls `setCachedToken(response.data.session_token)`.
- CSRF middleware passes any request carrying an `authorization` header — native POSTs won't be CSRF-blocked.

Gaps:
- **Nothing verified on a real device** — the native token path is untested end-to-end (login → persist → restart → refresh → logout).
- Tokens in AsyncStorage (plaintext); **`expo-secure-store` is not used anywhere** — recommended for JWT storage on device.
- Google/Microsoft/Apple SSO flows use `window.opener.postMessage` popups (web pattern); native needs `expo-auth-session`/`expo-web-browser` redirect flows + Apple Sign-In capability (mandatory on iOS if other social logins are offered).
- Biometric re-login: `expo-local-authentication` plugin configured — wire-up state unknown, verify.

---

## 5. Payments on native — **the #1 blocker**
- Backend is substantial: `routes/iap.py` has `/products`, `/checkout-preview`, `POST /apple/verify`, `POST /google/verify`, readiness/status/timeline/history endpoints; `routes/google_play.py` for Play Console. Apple/Google key material is provisioned per earlier sessions.
- Frontend subscription UI (`app/subscription/plans.tsx`) already lists `apple_iap` / `google_iap` as "handoff" payment methods with test IDs.
- **BUT: no native purchase SDK exists** — `react-native-iap` / `expo-iap` / StoreKit / Play Billing client is absent from package.json. The actual purchase step (fetch SKUs, purchase, obtain receipt, send to `/apple/verify` | `/google/verify`) is not implemented client-side.
- **Store compliance**: Apple/Google require IAP for digital subscriptions. Stripe/PayPal/FedaPay buttons for digital goods **must be hidden on native builds** (Apple 3.1.1) or the app will be rejected. Mobile-money flows for *physical/external* services need case-by-case review. US-specific external-purchase-link exceptions exist but are jurisdiction-dependent — treat IAP as the required default.
- Products/SKUs must be created in App Store Connect + Play Console and matched to backend product IDs.

Effort: native IAP client + purchase state machine + receipt→backend verify + restore purchases + gateway-visibility rules per platform. This is the largest single work item.

---

## 6. Push notifications — **~70% ready**
- Native: `src/hooks/usePushNotifications.ts` already implements the full expo-notifications flow (guarded native-only require, Android channel, permission request, Expo push token registration → backend). Backend `routes/notifications.py` recognizes `ExponentPushToken…` and there is a full notification engine + admin push routes.
- Web: separate VAPID/serviceWorker path (`useWebPush`, `src/utils/pushNotifications.ts`) — stays web-only, coexists fine.
- Missing: APNs key + FCM `google-services.json` in EAS credentials; device-level verification that backend sends via Expo Push API for native tokens (verify the sender side handles both VAPID and Expo tokens); notification icon/color config in app.json.

---

## 7. Other material findings
- **Fonts**: `@expo-google-fonts/manrope` + expo-font — native-compatible ✅. Icon glyph-map stubbing in metro.config.js is platform-neutral ✅.
- **Mic/voice**: 7 files use `getUserMedia` (web). Native voice recording must use expo-av (present, deprecated) or expo-audio. AI coaching voice features need this port.
- **Camera/uploads**: `expo-image-picker` + `expo-document-picker` present ✅ — uploads likely work; verify multipart handling on native.
- **fpsGame (three.js)**: exclude from native or port to expo-gl (not worth it initially).
- **Admin console on native**: recharts panels + 3 unguarded-div panels break. Recommendation: gate the admin console to web ("open on desktop") for v1 — admin on a phone is low-value.
- **`/app/mobile`**: essentially an empty Expo starter (3 route files) — not a usable head start; the real universal app is `/app/frontend`.
- **OTel**: browser-only tracing correctly no-ops natively; consider native telemetry later.
- **i18n**: custom i18n in `src/i18n` — platform-neutral, should work ✅.

---

## 8. Deliverable answers

### (a) % of app that runs on native as-is
**~80% of screens should render**; core user journeys (auth UI, tabs, chat/coaching, careers, content, profile) follow the guarded universal pattern. Functionally end-to-end today: ~60–65%, because purchases (IAP), voice features, SSO, and push credentials need work. Confidence caveat: zero device-run history — expect a QA long-tail.

### (b) Top blockers, ranked by effort (high → low)
1. **Native IAP purchase flow** — no purchase SDK; store-compliance gating of non-IAP gateways (L)
2. **Per-screen native runtime QA** — 207 screens never run on device; fix guard escapes, layout bugs (L, spread out)
3. **Native SSO flows** (Google/Microsoft/Apple via expo-auth-session; Apple Sign-In mandatory on iOS) (M)
4. **Push/build credentials + config** — APNs, FCM, associatedDomains/intentFilters, expo-dev-client, package version alignment (M)
5. **Voice/mic port** for AI coaching features (getUserMedia → expo-audio) (M)
6. **Token storage hardening** (AsyncStorage → expo-secure-store) + native auth E2E QA (S)
7. **Admin console** — gate to web for v1 (S) or port charts to victory-native (M/L later)
8. **fpsGame/three** — exclude on native (S)

### (c) Phased effort estimate
- **Phase 1 — "It builds & you can log in" (S/M)**: EAS dev build, fix package drift, expo-dev-client, native auth E2E (login/refresh/logout/SecureStore), gate admin+fpsGame to web, smoke the 5 tabs.
- **Phase 2 — "Core product works" (M)**: per-screen QA of user-facing routes, native SSO, voice port, push credentials + E2E push, deep links (associatedDomains/intentFilters + AASA/assetlinks).
- **Phase 3 — "You can charge money" (L)**: IAP SDK integration, SKU setup in both stores, receipt verify wiring to existing backend, restore purchases, platform-conditional payment-method visibility, store review compliance.
- **Phase 4 — "Ship" (M)**: store assets/metadata, privacy manifests, TestFlight/internal track, review-feedback loop.

### (d) Recommended path
1. Keep `/app/frontend` as the single universal codebase (it was clearly built for this); ignore `/app/mobile`.
2. Native-first screens: **(tabs) shell, auth, chat/AI coaching, careers, content library, profile/settings** — these are the guarded, high-value surfaces. Explicitly web-gate: admin console, fpsGame, SEO/blog-management surfaces.
3. Do Phase 1 in an Expo-template job against this same backend (backend already speaks native auth) before scoping Phases 2–3 precisely — the first device run will convert this static estimate into a concrete punch list.
4. Treat IAP as its own project with store-account prerequisites (SKUs, banking, agreements) started early since Apple/Google review lead times dominate the calendar.
