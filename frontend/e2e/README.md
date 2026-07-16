# Frontend E2E Suites

## Welcome first-paint regression

This suite guards the Welcome page against white/blank-screen regressions and verifies the critical shell contract:
1. Meaningful first paint on phone / tablet / desktop
2. No blank screen in preview-like embedded context
3. Dark mode remains valid after first paint
4. Locale-safe rendering and critical `data-testid` hooks remain present

### Run command

```bash
cd /app/frontend
E2E_BASE_URL="https://coach-web-preview.preview.emergentagent.com" \
node node_modules/@playwright/test/cli.js test e2e/welcome-first-paint-regression.spec.ts --reporter=list
```

### Shortcut script

```bash
yarn test:welcome:first-paint
```

### Optional embedded-check command

Use this when you want to explicitly exercise the same-origin iframe/embedded contract in a local environment:

```bash
E2E_BASE_URL="http://127.0.0.1:3000" yarn test:welcome:first-paint:embed
```

Notes:
- The embedded Welcome check is intentionally skipped by default in preview/protected environments
- Opt in with `RUN_WELCOME_EMBED_E2E=1` for stable local same-origin verification

## Passkey virtual-authenticator regression

This suite verifies full passkey flow with a virtual authenticator:
1. Login with password
2. Register passkey from Security page
3. Logout
4. Login using passkey mode

### Run command

```bash
cd /app/frontend
E2E_BASE_URL="https://coach-web-preview.preview.emergentagent.com" \
node node_modules/@playwright/test/cli.js test e2e/passkey-virtual-authenticator.spec.ts --project=desktop-chromium --reporter=list
```

### Notes
- Uses free test user from `e2e/helpers/auth.ts`
- Uses CDP `WebAuthn.addVirtualAuthenticator` (Chromium project only)
- Keep this suite in CI as a critical auth regression guard
