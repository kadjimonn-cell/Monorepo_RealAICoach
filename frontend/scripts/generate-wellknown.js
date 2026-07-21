#!/usr/bin/env node
/**
 * Generates universal-link association files into public/.well-known/ so that
 * `expo export` copies them to the static build root:
 *   /.well-known/apple-app-site-association  (iOS Universal Links)
 *   /.well-known/assetlinks.json             (Android App Links)
 *
 * Parameterized via env (all optional; sensible defaults for RealAICoach):
 *   APPLE_TEAM_ID            – Apple Developer Team ID   (default: L568YJ4KFH)
 *   APPLE_BUNDLE_ID          – iOS bundle identifier     (default: com.realaicoach.app)
 *   ANDROID_PACKAGE_NAME     – Android applicationId     (default: com.realaicoach.app)
 *   ANDROID_CERT_SHA256      – comma-separated SHA-256 cert fingerprints of the
 *                              RELEASE signing key. Until provided, assetlinks.json
 *                              is emitted with an empty fingerprint list (won't
 *                              verify — Android falls back to the chooser dialog).
 */
'use strict';

const fs = require('node:fs');
const path = require('node:path');

const APPLE_TEAM_ID = (process.env.APPLE_TEAM_ID || 'L568YJ4KFH').trim();
const APPLE_BUNDLE_ID = (process.env.APPLE_BUNDLE_ID || 'com.realaicoach.app').trim();
const ANDROID_PACKAGE_NAME = (process.env.ANDROID_PACKAGE_NAME || 'com.realaicoach.app').trim();
const ANDROID_CERT_SHA256 = (process.env.ANDROID_CERT_SHA256 || '')
  .split(',')
  .map((s) => s.trim())
  .filter(Boolean);

const outDir = path.join(__dirname, '..', 'public', '.well-known');
fs.mkdirSync(outDir, { recursive: true });

const aasa = {
  applinks: {
    apps: [],
    details: [
      {
        appIDs: [`${APPLE_TEAM_ID}.${APPLE_BUNDLE_ID}`],
        appID: `${APPLE_TEAM_ID}.${APPLE_BUNDLE_ID}`,
        paths: ['*'],
        components: [{ '/': '*' }],
      },
    ],
  },
  webcredentials: {
    apps: [`${APPLE_TEAM_ID}.${APPLE_BUNDLE_ID}`],
  },
};

const assetlinks = [
  {
    relation: ['delegate_permission/common.handle_all_urls'],
    target: {
      namespace: 'android_app',
      package_name: ANDROID_PACKAGE_NAME,
      sha256_cert_fingerprints: ANDROID_CERT_SHA256,
    },
  },
];

fs.writeFileSync(path.join(outDir, 'apple-app-site-association'), JSON.stringify(aasa, null, 2));
fs.writeFileSync(path.join(outDir, 'assetlinks.json'), JSON.stringify(assetlinks, null, 2));

console.log(`[wellknown] apple-app-site-association -> appID ${APPLE_TEAM_ID}.${APPLE_BUNDLE_ID}`);
if (ANDROID_CERT_SHA256.length === 0) {
  console.log('[wellknown] assetlinks.json emitted WITHOUT cert fingerprints (set ANDROID_CERT_SHA256 for production App Links verification).');
} else {
  console.log(`[wellknown] assetlinks.json -> ${ANDROID_PACKAGE_NAME} with ${ANDROID_CERT_SHA256.length} fingerprint(s).`);
}
