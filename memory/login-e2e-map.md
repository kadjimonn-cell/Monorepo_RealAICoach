# Login E2E Selector Contract

Last Updated: 2026-05-10
Scope: `/auth/login` and conditional login states (2FA modal, success overlay, reset/logout banners)

## Purpose
- Provide a stable selector contract for auth automation.
- Prevent brittle tests when styles/layout change.
- Keep naming consistent with kebab-case `data-testid` strategy.

## Contract Rules
- Prefer `data-testid` selectors over text or style selectors.
- Treat these IDs as API-level contract for QA automation.
- Do not rename/remove contract selectors without updating this file and E2E tests.
- Additive changes are preferred over breaking changes.

## Test Credentials (Stable)
- Standard success login user:
  - Email: `admin@realaicoach.app`
  - Password: `NewAdminPass2026!`
- Stable 2FA user:
  - Email: `e2e.2fa.stable@realaicoach.app`
  - Password: `Stable2FAPass2026!`
  - Expected result: backend returns `requires_2fa: true`, UI shows 2FA modal.

## Route-Level Selectors
- `login-screen`
- `login-card`
- `login-heading`
- `login-subheading`
- `login-theme-toggle`
- `login-security-badge`
- `login-register-link`

## Password Flow Selectors
- `login-method-password`
- `login-email-input`
- `login-password-input`
- `login-toggle-password`
- `remember-me-toggle`
- `login-submit-button`
- `login-forgot-password`
- `password-strength` (conditional)

## OTP Login Flow Selectors
- `login-method-otp`
- `login-otp-request`
- `login-otp-segmented-otp`
- `login-otp-otp-box-0` ... `login-otp-otp-box-7`
- `login-otp-hint` (conditional)
- `login-otp-verify`

## SSO & Diagnostics Selectors
- `login-google-button`
- `login-microsoft-button`
- `login-apple-button`
- `sso-diagnostics-waiting` (conditional)
- `sso-diagnostics-cancel` (conditional)
- `sso-diagnostics-fallback` (conditional)
- `sso-diagnostics-dismiss` (conditional)
- `sso-diagnostics-redirect-top` (conditional)
- `sso-diagnostics-magic-email` (conditional)
- `sso-diagnostics-send-magic-link` (conditional)
- `sso-diagnostics-qr` (conditional)
- `sso-diagnostics-password` (conditional)
- `sso-diagnostics-resend-magic` (conditional)

## Quick Auth Selectors
- `login-pin-mode`
- `login-passkey-mode`
- `login-qr-mode`
- `login-pin-input` (conditional)
- `login-pin-submit` (conditional)
- `login-passkey-submit` (conditional)
- `qr-login-panel` (conditional)
- `qr-code-display` (conditional)
- `qr-regenerate-btn` (conditional)
- `qr-retry-btn` (conditional)

## 2FA Modal Selectors (Conditional)
- `2fa-modal-overlay`
- `2fa-modal-card`
- `2fa-modal-header`
- `2fa-modal-title`
- `2fa-modal-subtitle`
- `2fa-otp-display`
- `2fa-otp-message`
- `2fa-otp-expiry-note`
- `2fa-segmented-otp`
- `2fa-otp-box-0` ... `2fa-otp-box-7`
- `2fa-verify-button`
- `2fa-resend-button`
- `2fa-cancel-button`
- `2fa-error-box` / `2fa-error-text` (conditional)

## Status/Banner Selectors (Conditional)
- `login-logout-success-banner`
- `login-logout-success-dismiss`
- `login-reset-success-banner`
- `login-reset-success-dismiss`
- `login-error`
- `login-recovery-box`
- `login-recovery-countdown`
- `login-recovery-reset-password`
- `login-recovery-contact-support`
- `login-risk-guidance-box`
- `login-open-id-verification-button`

## Success Overlay Selectors (Conditional)
- `login-success-overlay`
- `login-success-icon`
- `login-success-title`
- `login-success-subtitle`

## Recommended E2E Cases
1. **Standard Success Login**
   - Fill `login-email-input`, `login-password-input`
   - Click `login-submit-button`
   - Assert `login-success-overlay` briefly appears

2. **2FA Modal Trigger**
   - Use stable 2FA user credentials
   - Submit password login
   - Assert `2fa-modal-card` + `2fa-verify-button` visible

3. **OTP Login Mode Render**
   - Click `login-method-otp`
   - Assert segmented OTP container and verify button

4. **Banner States**
   - `/auth/login?logout=1` => `login-logout-success-banner`
   - `/auth/login?reset=success` => `login-reset-success-banner`

5. **Full 2FA Completion (Non-Production)**
   - Login with stable 2FA user using password form.
   - Use admin test helper endpoint `POST /api/auth/admin/e2e/otp/issue` with admin JWT and allowlisted target email.
   - Fill OTP in `2fa-segmented-otp` and submit `2fa-verify-button`.
   - Assert success redirect/login completion.

## Register Route (`/auth/register`) Selector Contract
- `register-screen`
- `register-card`
- `register-back-button`
- `register-plan-banner` (conditional)
- `register-error` (conditional)
- `register-name-input`
- `register-email-input`
- `register-password-input`
- `register-toggle-password`
- `register-confirm-password-input`
- `register-submit-button`
- `register-google-button`
- `register-microsoft-button`
- `register-apple-button`
- `register-login-link`

## Forgot Password Route (`/auth/forgot-password`) Selector Contract
- `forgot-password-screen`
- `forgot-password-header`
- `forgot-password-back`
- `forgot-password-header-title`
- `forgot-password-form` (conditional)
- `forgot-password-icon`
- `forgot-password-title`
- `forgot-password-subtitle`
- `forgot-password-email-input`
- `forgot-password-send`
- `forgot-password-back-login-secondary`
- `forgot-password-sent-section` (conditional)
- `forgot-password-sent-title` (conditional)
- `forgot-password-back-login` (conditional)
- `forgot-password-resend` (conditional)

## Reset Password Route (`/auth/reset-password`) Selector Contract
- `reset-password-screen`
- `reset-password-header`
- `reset-password-back`
- `reset-password-header-title`

### Method Step (conditional)
- `reset-method-section`
- `reset-method-title`
- `reset-method-email`
- `reset-email-input`
- `reset-send-link`

### Sent Step (conditional)
- `reset-sent-section`
- `reset-sent-title`
- `reset-sent-back-login`
- `reset-sent-resend`

### New Password Step (conditional)
- `reset-new-password-section`
- `reset-new-password-title`
- `reset-new-password-input`
- `reset-new-password-toggle`
- `reset-confirm-password-input`
- `reset-confirm-button`

### Success Step (conditional)
- `reset-success-section`
- `reset-success-title`
- `reset-success-login`

## Auth Recovery Route E2E Cases
1. **Register Page Contract Sanity**
   - Visit `/auth/register`
   - Assert presence of `register-name-input`, `register-email-input`, `register-submit-button`, `register-login-link`.

2. **Forgot Password Submit + Sent State**
   - Visit `/auth/forgot-password`
   - Enter email in `forgot-password-email-input`
   - Click `forgot-password-send`
   - Assert `forgot-password-sent-section` appears.

3. **Reset Password Method Step**
   - Visit `/auth/reset-password`
   - Assert `reset-method-section`, `reset-email-input`, and `reset-send-link`.

4. **Reset Password Token Step**
   - Visit `/auth/reset-password?token=<valid-or-test-token>`
   - Assert `reset-new-password-section`, `reset-new-password-input`, `reset-confirm-button`.

## Change Management
- If a selector must change:
  1. Update component and this contract in same PR.
  2. Keep backward-compatible alias for one cycle when possible.
  3. Re-run login E2E matrix before merge.
