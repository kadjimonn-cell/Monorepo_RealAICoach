# EAS BUILD RUNBOOK — RealAICoach (Expo SDK 54, single codebase /app/frontend)

Last updated: 2026-07-20 (Phase 3). App config: `app.json` (bundle `com.realaicoach.app`, EAS projectId `391b98a8-29da-4861-924a-4934ed4a4cd3`, owner `hypoduchrist91`). Build profiles: `eas.json` (development / preview / production).

## 0. What you need (accounts & credentials)
| Item | Needed for | Where |
|---|---|---|
| Expo account (owner `hypoduchrist91`) | all EAS builds | expo.dev |
| Apple Developer Program membership (Team ID `L568YJ4KFH`) | iOS builds, Sign in with Apple, push, IAP | developer.apple.com |
| App Store Connect app record for `com.realaicoach.app` | TestFlight/production + IAP products | appstoreconnect.apple.com |
| Google Play Console app for `com.realaicoach.app` | Android production + Play Billing | play.google.com/console |
| APNs key (auto-managed by EAS) + FCM/Google service account for push | push delivery | EAS credentials flow |

## 1. First development build (test native SSO, voice, push, deep links, IAP)
```bash
cd /app/frontend            # (in your local clone)
npm install -g eas-cli      # once
eas login                   # Expo account
# iOS (device): requires Apple Developer login; EAS manages certs/profiles
eas build --platform ios --profile development
# Android (device/emulator):
eas build --platform android --profile development
```
- Install the resulting build on your device (QR from the EAS build page).
- Run `npx expo start` locally and connect the dev client to Metro.
- The dev build (NOT Expo Go) is required for: Apple Sign-In, native Google SSO, expo-notifications remote push, expo-iap purchases.

## 2. iOS specifics
- `usesAppleSignIn: true` + `expo-apple-authentication` plugin already configured; enable the "Sign in with Apple" capability on the App ID in the Apple Developer portal (EAS usually prompts/handles this).
- IAP: create subscription products in App Store Connect with EXACT product IDs from the backend catalog:
  - `com.realaicoach.basic.monthly`, `com.realaicoach.basic.yearly`
  - `com.realaicoach.premium.monthly`, `com.realaicoach.premium.yearly`
  (confirm the full list via `GET /api/iap/products`)
- Sandbox tester account (App Store Connect → Users → Sandbox) for purchase testing.
- Universal links: `associatedDomains: applinks:realaicoach.app` is configured; the site already serves `/.well-known/apple-app-site-association` (Team ID `L568YJ4KFH`). Re-publish the web app first, then install the iOS build.

## 3. Android specifics
- First `eas build` for Android generates the app signing key (or use Play App Signing). AFTER the first production build:
  1. Get the release SHA-1 and SHA-256: `eas credentials -p android` (or Play Console → App integrity).
  2. **Google native SSO**: create an OAuth client (type Android, package `com.realaicoach.app`, the SHA-1) in Google Cloud Console → set `GOOGLE_ANDROID_CLIENT_ID` in the backend env → native Google sign-in switches on automatically.
  3. **App Links**: set `ANDROID_CERT_SHA256=<sha256>` in the WEB build environment and re-publish — `scripts/generate-wellknown.js` bakes it into `/.well-known/assetlinks.json`.
- Play Billing: create matching subscription products in Play Console (same product IDs as above). Add a license-tester Gmail for sandbox purchases.
- Push: upload the FCM service account JSON via `eas credentials -p android` (expo-notifications).

## 4. Production builds & store submission
```bash
eas build --platform ios --profile production
eas build --platform android --profile production
# Submission (after store listings exist):
eas submit --platform ios      # needs ascAppId (App Store Connect app ID)
eas submit --platform android  # first AAB must be uploaded manually once
```

## 5. Backend env expected by native features (already wired; values needed)
- `GOOGLE_ANDROID_CLIENT_ID` (after step 3.2) — native Android Google SSO.
- `APPLE_IAP_KEY_ID` / `APPLE_IAP_ISSUER_ID` / `APPLE_IAP_PRIVATE_KEY_*` — Apple receipt verification (present).
- `GOOGLE_PLAY_*_SERVICE_ACCOUNT_*` + `GOOGLE_PLAY_PACKAGE_NAME` — Google receipt verification (present).

## 6. Device test checklist (dev build)
1. Email/password + native Google sign-in (iOS), broker fallback (Android until client ID exists).
2. Apple Sign-In end-to-end (iOS device with Apple ID).
3. Coaching chat: record voice → transcript + AI reply + feedback.
4. Push: accept permission → token registered (`/api/notifications/push-token`) → test delivery (EAS/FCM/APNs configured).
5. Deep links: `realaicoach://chat/<id>`, `/careers`, `/auth/reset-password?token=x`; universal links after well-known files live + fingerprints set.
6. IAP: sandbox purchase Basic + Premium, verify entitlement unlocks, then "Restore Purchases" after reinstall.
7. Confirm Stripe/PayPal/FedaPay are NOT visible in the native payment screen (store compliance).
