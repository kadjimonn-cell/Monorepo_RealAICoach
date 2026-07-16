/* eslint-env node */
/* global __dirname */
const { express, createProxyMiddleware } = require('@realaicoach/web-runtime');
const compression = require('compression');
const path = require('path');
const fs = require('fs');
const crypto = require('crypto');
const http = require('http');
const { execFileSync } = require('child_process');
const { runSidebarPolicyGuard } = require('./scripts/sidebar-policy-guard');

const PORT = 3000;
function canReachLocalPort(port) {
  try {
    execFileSync('bash', ['-lc', `timeout 1 bash -c '</dev/tcp/127.0.0.1/${port}'`], { stdio: 'ignore' });
    return true;
  } catch {
    return false;
  }
}

function detectBackendPort() {
  const envPortRaw = String(process.env.BACKEND_PORT || process.env.INTERNAL_BACKEND_PORT || '').trim();
  const envPort = Number(envPortRaw);
  // Never fall back to non-app ports (e.g. 8010 internal tools server):
  // proxying /api to a wrong server silently breaks currency/plans/i18n data.
  const candidates = [
    Number.isFinite(envPort) && envPort > 0 ? envPort : null,
    8001,
  ].filter(Boolean);

  for (const p of candidates) {
    if (canReachLocalPort(p)) return Number(p);
  }
  return candidates[candidates.length - 1] || 8001;
}

let backendPort = detectBackendPort();
let lastBackendRedetectAtMs = 0;

function redetectBackendPortOnFailure() {
  const now = Date.now();
  if (now - lastBackendRedetectAtMs < 5000) return;
  lastBackendRedetectAtMs = now;
  const detected = detectBackendPort();
  if (detected !== backendPort) {
    console.warn(`[api-proxy] backend port re-detected: ${backendPort} -> ${detected}`);
    backendPort = detected;
  }
}
const EXPO_DEV_PORT = 3001;
const DIST_DIR = path.join(__dirname, 'dist');
const CLIENT_DIR = path.join(DIST_DIR, 'client');
const SERVER_DIR = path.join(DIST_DIR, 'server');
const BUILD_STATE_DIR = path.join(__dirname, '.cache');
const BUILD_STATE_FILE = path.join(BUILD_STATE_DIR, 'production-build-state.json');
const BUILD_STATE_FILE_FALLBACK = '/tmp/frontend-production-build-state.json';
const EXPORT_BUILD_LOCK_FILE = '/tmp/frontend_export_build.lock';
let expoFallbackUnavailableLastLogAtMs = 0;

function clearMetroCaches(reason = 'unspecified', options = {}) {
  const deep = options && options.deep === true;
  const targets = [
    '/tmp/frontend-metro-cache',
    '/tmp/metro-cache',
  ];

  if (deep) {
    targets.push(
      path.join(__dirname, 'node_modules', '.cache', 'metro'),
      path.join(__dirname, '.expo'),
    );
  }

  try {
    const tmpEntries = fs.readdirSync('/tmp');
    for (const name of tmpEntries) {
      if (name.startsWith('metro-file-map-')) {
        targets.push(path.join('/tmp', name));
      }
    }
  } catch (_err) {
    // non-blocking
  }

  let clearedAny = false;
  for (const target of targets) {
    try {
      if (!fs.existsSync(target)) continue;
      fs.rmSync(target, {
        recursive: true,
        force: true,
        maxRetries: 6,
        retryDelay: 120,
      });
      clearedAny = true;
    } catch (err) {
      console.warn('[metro-cache] failed to clear', target, '-', err.message);
    }
  }

  if (clearedAny) {
    console.log(`[metro-cache] cleared stale Metro caches (${reason}).`);
  }
}

function readFrontendEnvFile() {
  const envMap = {};
  try {
    const envPath = path.join(__dirname, '.env');
    if (!fs.existsSync(envPath)) return envMap;
    const lines = fs.readFileSync(envPath, 'utf-8').split(/\r?\n/);
    for (const line of lines) {
      if (!line || line.trim().startsWith('#') || !line.includes('=')) continue;
      const [k, ...rest] = line.split('=');
      envMap[String(k || '').trim()] = rest.join('=').trim();
    }
  } catch (_err) {
    // ignore
  }
  return envMap;
}

const FRONTEND_ENV = readFrontendEnvFile();

function getExpectedPreviewHost() {
  const pickHost = (value) => {
    const rawVal = String(value || '').trim();
    if (!rawVal) return '';
    try {
      const parsed = new URL(rawVal);
      return String(parsed.hostname || '').toLowerCase();
    } catch {
      return rawVal.replace(/^https?:\/\//i, '').split('/')[0].toLowerCase();
    }
  };

  const candidates = [
    FRONTEND_ENV.REACT_APP_BACKEND_URL,
    FRONTEND_ENV.EXPO_PUBLIC_BACKEND_URL,
    FRONTEND_ENV.EXPO_PACKAGER_HOSTNAME,
    FRONTEND_ENV.EXPECTED_PREVIEW_HOST,
    process.env.REACT_APP_BACKEND_URL,
    process.env.EXPO_PUBLIC_BACKEND_URL,
    process.env.EXPO_PACKAGER_HOSTNAME,
    process.env.EXPECTED_PREVIEW_HOST,
  ];

  for (const candidate of candidates) {
    const host = pickHost(candidate);
    if (host.includes('preview.emergentagent.com')) {
      return host;
    }
  }

  return '';
}

const EXPECTED_PREVIEW_HOST = getExpectedPreviewHost();
const DIST_FORCE_REBUILD_ENABLED = String(
  process.env.DIST_FORCE_REBUILD
  || FRONTEND_ENV.DIST_FORCE_REBUILD
  || '',
).trim() === '1';
const EXPORT_NODE_OPTIONS = String(
  process.env.FRONTEND_EXPORT_NODE_OPTIONS
  || FRONTEND_ENV.FRONTEND_EXPORT_NODE_OPTIONS
  || process.env.NODE_OPTIONS
  || '--max-old-space-size=1536',
).trim();
const PREVIEW_HOST_RE = /([a-z0-9-]+\.preview\.emergentagent\.com)/gi;

const DIST_RUNTIME_STATUS = {
  mode: 'boot',
  last_reason: 'startup',
  last_result: 'unknown',
  last_updated_at: new Date().toISOString(),
  last_build_duration_ms: 0,
  last_build_error: '',
};

function ensureReactNativeWebBabelRuntimeShim() {
  const sourceRuntimeDir = path.join(__dirname, 'node_modules', '@babel', 'runtime');
  const targetBabelDir = path.join(__dirname, 'node_modules', 'react-native-web', 'node_modules', '@babel');
  const targetRuntimeDir = path.join(targetBabelDir, 'runtime');
  const helperProbe = path.join(targetRuntimeDir, 'helpers', 'esm', 'toPropertyKey.js');
  const sourceHelperProbe = path.join(sourceRuntimeDir, 'helpers', 'esm', 'toPropertyKey.js');
  let shimAdjusted = false;

  try {
    if (!fs.existsSync(sourceRuntimeDir)) {
      console.warn('[startup-runtime-shim] source @babel/runtime missing; skipping shim setup.');
      return false;
    }

    if (fs.existsSync(helperProbe)) {
      return true;
    }

    fs.mkdirSync(targetBabelDir, { recursive: true });
    if (!fs.existsSync(targetRuntimeDir)) {
      try {
        fs.symlinkSync(sourceRuntimeDir, targetRuntimeDir, 'dir');
        shimAdjusted = true;
      } catch (_err) {
        fs.cpSync(sourceRuntimeDir, targetRuntimeDir, { recursive: true, force: true });
        shimAdjusted = true;
      }
    } else {
      // Non-destructive repair: avoid removing runtime folder while Metro is reading it.
      try {
        fs.cpSync(sourceRuntimeDir, targetRuntimeDir, { recursive: true, force: false });
      } catch (_err) {
        // Best effort; we'll patch helper probe directly below if still missing.
      }

      if (!fs.existsSync(helperProbe) && fs.existsSync(sourceHelperProbe)) {
        fs.mkdirSync(path.dirname(helperProbe), { recursive: true });
        fs.copyFileSync(sourceHelperProbe, helperProbe);
        shimAdjusted = true;
      }
    }

    const ready = fs.existsSync(helperProbe);
    if (!ready) {
      console.warn('[startup-runtime-shim] helper probe still missing after shim creation.');
    } else if (shimAdjusted) {
      clearMetroCaches('babel-runtime-shim-adjusted');
    }
    return ready;
  } catch (err) {
    console.warn('[startup-runtime-shim] failed to prepare runtime shim:', err.message);
    return false;
  }
}

function updateDistRuntimeStatus(patch = {}) {
  Object.assign(DIST_RUNTIME_STATUS, patch, {
    last_updated_at: new Date().toISOString(),
  });
}

function toSafeHeaderValue(value) {
  return String(value ?? '')
    .replace(/[^A-Za-z0-9 .,:;_\-\/()\[\]{}]+/g, ' ')
    .replace(/\s+/g, ' ')
    .trim()
    .slice(0, 240);
}

function assertStartupPreviewHostSafety() {
  const allowedHost = String(EXPECTED_PREVIEW_HOST || '').toLowerCase();
  if (!allowedHost) {
    throw new Error('Preview startup guard: EXPECTED_PREVIEW_HOST missing from .env');
  }

  const envFiles = [
    path.join(__dirname, '.env'),
    path.join(__dirname, '..', 'backend', '.env'),
  ];

  const violations = [];
  for (const envFile of envFiles) {
    if (!fs.existsSync(envFile)) {
      violations.push(`${envFile}: missing env file`);
      continue;
    }
    const text = fs.readFileSync(envFile, 'utf-8');
    const lowered = text.toLowerCase();

    if (lowered.includes('trust-layer-checkout')) {
      violations.push(`${envFile}: blocked token trust-layer-checkout detected`);
    }

    const hosts = new Set(Array.from(lowered.matchAll(PREVIEW_HOST_RE)).map((m) => m[1]));
    for (const host of hosts) {
      if (host !== allowedHost) {
        violations.push(`${envFile}: stale preview host '${host}' (allowed '${allowedHost}')`);
      }
    }
  }

  const hardViolations = violations.filter((v) => (
    v.includes('blocked token trust-layer-checkout') || v.includes('missing env file')
  ));
  const staleHostViolations = violations.filter((v) => !hardViolations.includes(v));

  if (staleHostViolations.length) {
    console.warn(`[startup-guard] non-blocking stale preview-host checks:\n${staleHostViolations.map((v) => `- ${v}`).join('\n')}`);
  }

  if (hardViolations.length) {
    throw new Error(`Preview startup guard failed:\n${hardViolations.map((v) => `- ${v}`).join('\n')}`);
  }
}

assertStartupPreviewHostSafety();
ensureReactNativeWebBabelRuntimeShim();
clearMetroCaches('startup-initialization');

function getEffectiveRequestHost(req) {
  const xForwardedHost = String((req && req.headers && req.headers['x-forwarded-host']) || '')
    .split(',')[0]
    .trim()
    .split(':')[0]
    .toLowerCase();
  const hostHeader = String((req && req.headers && req.headers.host) || '')
    .split(':')[0]
    .toLowerCase();
  return xForwardedHost || hostHeader;
}

function isPreviewLikeHost(hostname) {
  const h = String(hostname || '').toLowerCase();
  return h.includes('preview.emergentagent.com') || h.endsWith('.emergent.sh') || h.includes('.preview.emergentcf.cloud');
}

function requestIsPreview(req) {
  const reqHost = getEffectiveRequestHost(req);
  if (isPreviewLikeHost(reqHost)) return true;
  if (EXPECTED_PREVIEW_HOST && isPreviewLikeHost(EXPECTED_PREVIEW_HOST)) return true;
  return false;
}

function resolveExpectedPreviewHost(req) {
  const reqHost = getEffectiveRequestHost(req);
  // Runtime canonicalization rule:
  // If the incoming host is already a preview host, trust it for this request.
  // This prevents stale startup env values from pinning cross-fork expected hosts.
  if (reqHost && reqHost.includes('preview.emergentagent.com')) {
    return reqHost;
  }
  return String(EXPECTED_PREVIEW_HOST || '').toLowerCase();
}

function isWrapperArtifactPath(pathname) {
  const p = String(pathname || '/');
  return p === '/wo' || p.startsWith('/loading-preview') || p.startsWith('/s/');
}

function withMergedQueryPath(req, basePath, params = {}) {
  const originalUrl = String((req && req.url) || '');
  const rawQuery = originalUrl.includes('?') ? originalUrl.split('?')[1] : '';
  const merged = new URLSearchParams(rawQuery);
  Object.entries(params).forEach(([k, v]) => {
    if (!merged.has(k)) merged.set(k, String(v));
  });
  const qs = merged.toString();
  return qs ? `${basePath}?${qs}` : basePath;
}

function isTrustedShellHost(hostname) {
  const h = String(hostname || '').toLowerCase();
  return (
    h === 'app.emergent.sh'
    || h.endsWith('.emergent.sh')
    || h === 'app.emergentagent.com'
    || h.endsWith('.emergentagent.com')
  );
}

function isDocumentLikeRequest(req) {
  const method = String((req && req.method) || 'GET').toUpperCase();
  if (method !== 'GET' && method !== 'HEAD') return false;

  const pathName = String((req && req.path) || '/');
  if (pathName.startsWith('/api') || pathName.startsWith('/_preview')) return false;

  const fetchDest = String((req && req.headers && req.headers['sec-fetch-dest']) || '').toLowerCase();
  if (fetchDest === 'document') return true;

  const accept = String((req && req.headers && req.headers.accept) || '').toLowerCase();
  if (!accept) return true;
  return accept.includes('text/html') || accept.includes('*/*');
}

function canonicalizeShellPath(pathName) {
  const pathText = String(pathName || '/');
  if (pathText.startsWith('/s/') || pathText === '/wo' || pathText.startsWith('/loading-preview')) {
    return '/';
  }
  return pathText;
}

function hasDistArtifacts() {
  if (!(fs.existsSync(DIST_DIR) && fs.existsSync(CLIENT_DIR))) {
    return false;
  }

  const hasClientBundle = fs.existsSync(path.join(CLIENT_DIR, '_expo', 'static', 'js', 'web'));
  if (!hasClientBundle) return false;

  if (!fs.existsSync(SERVER_DIR)) {
    return false;
  }

  const hasServerEntry = (
    fs.existsSync(path.join(SERVER_DIR, 'index.html'))
    || fs.existsSync(path.join(SERVER_DIR, '(tabs)', 'index.html'))
  );

  return hasServerEntry;
}

function hasDistClientFallbackArtifacts() {
  if (!(fs.existsSync(DIST_DIR) && fs.existsSync(CLIENT_DIR))) {
    return false;
  }

  const hasHtmlFallback = [
    'v7-preview.html',
    'offline.html',
    'ms-login.html',
    'qr.html',
  ].some((fileName) => fs.existsSync(path.join(CLIENT_DIR, fileName)));

  return hasHtmlFallback;
}

function readBuildState() {
  const candidates = [BUILD_STATE_FILE, BUILD_STATE_FILE_FALLBACK];
  for (const filePath of candidates) {
    try {
      if (!fs.existsSync(filePath)) continue;
      const raw = fs.readFileSync(filePath, 'utf-8');
      const parsed = JSON.parse(raw);
      if (parsed && typeof parsed === 'object') {
        return {
          ...parsed,
          __state_file: filePath,
        };
      }
    } catch {
      // Try next candidate
    }
  }
  return null;
}

function writeBuildState(state) {
  const payload = JSON.stringify(state, null, 2);
  const targets = [BUILD_STATE_FILE, BUILD_STATE_FILE_FALLBACK];

  for (const targetPath of targets) {
    try {
      const parentDir = path.dirname(targetPath);
      if (!fs.existsSync(parentDir)) {
        fs.mkdirSync(parentDir, { recursive: true });
      }
      fs.writeFileSync(targetPath, payload);
      return {
        ok: true,
        filePath: targetPath,
      };
    } catch (err) {
      console.warn('[dist-self-heal] Failed writing build state target:', targetPath, '-', err.message);
    }
  }

  return {
    ok: false,
    filePath: '',
  };
}

function getDistServerMtimeMs() {
  try {
    if (!fs.existsSync(SERVER_DIR)) return null;
    return fs.statSync(SERVER_DIR).mtimeMs;
  } catch {
    return null;
  }
}

function getLatestIndexBundleInfo() {
  const jsWebDir = path.join(CLIENT_DIR, '_expo', 'static', 'js', 'web');
  if (!fs.existsSync(jsWebDir)) return null;

  const bundles = fs.readdirSync(jsWebDir)
    .filter((f) => /^index-[a-f0-9]+\.js$/.test(f))
    .map((f) => {
      const abs = path.join(jsWebDir, f);
      const stat = fs.statSync(abs);
      return {
        name: f,
        path: abs,
        size: stat.size,
        mtime: stat.mtimeMs,
      };
    })
    .sort((a, b) => b.mtime - a.mtime);

  return bundles.length > 0 ? bundles[0] : null;
}

function extractBundleHash(bundleName) {
  const match = String(bundleName || '').match(/^index-([a-f0-9]+)\.js$/i);
  return match ? match[1] : '';
}

function isBuildStateUsable(state) {
  if (!state || typeof state !== 'object') return false;
  const fingerprint = String(state.source_fingerprint || '').trim();
  const bundleName = String(state.index_bundle || '').trim();
  const builtAt = String(state.built_at || '').trim();
  if (!fingerprint || !bundleName || !builtAt) return false;

  const bundlePath = path.join(CLIENT_DIR, '_expo', 'static', 'js', 'web', bundleName);
  if (!fs.existsSync(bundlePath)) return false;

  return true;
}

function verifyStaticExportArtifacts() {
  if (!(fs.existsSync(DIST_DIR) && fs.existsSync(CLIENT_DIR))) {
    throw new Error('Dist verification failed: dist/client artifacts are missing.');
  }

  const bundle = getLatestIndexBundleInfo();
  if (!bundle) {
    throw new Error('Dist verification failed: index bundle not found in dist/client/_expo/static/js/web.');
  }

  const minBundleBytes = 1024 * 1024;
  if (!Number.isFinite(bundle.size) || bundle.size < minBundleBytes) {
    throw new Error(`Dist verification failed: index bundle too small (${bundle.size} bytes).`);
  }

  try {
    execFileSync('node', ['--check', bundle.path], {
      cwd: __dirname,
      stdio: 'pipe',
      timeout: 45000,
      killSignal: 'SIGKILL',
    });
  } catch (err) {
    const stderr = (err.stderr && err.stderr.toString()) || '';
    const concise = stderr.split('\n').find(Boolean) || err.message;
    throw new Error(`Dist verification failed: index bundle syntax check failed (${concise}).`);
  }

  return bundle;
}

function isPidRunning(pid) {
  if (!Number.isFinite(pid) || pid <= 0) return false;
  try {
    process.kill(pid, 0);
    return true;
  } catch {
    return false;
  }
}

function getActiveExportBuildLock() {
  try {
    if (!fs.existsSync(EXPORT_BUILD_LOCK_FILE)) return null;
    const raw = fs.readFileSync(EXPORT_BUILD_LOCK_FILE, 'utf-8');
    const parsed = JSON.parse(raw);
    const pid = Number(parsed && parsed.pid);

    if (isPidRunning(pid)) {
      return {
        pid,
        started_at: parsed.started_at || '',
        reason: parsed.reason || 'unknown',
      };
    }

    fs.rmSync(EXPORT_BUILD_LOCK_FILE, { force: true });
    return null;
  } catch {
    return null;
  }
}

function hydrateBuildStateFromExistingDist(sourceFingerprint) {
  if (!hasDistArtifacts()) return false;

  const state = readBuildState();
  if (state && state.source_fingerprint) {
    return false;
  }

  const bundle = getLatestIndexBundleInfo();
  const distServerMtimeMs = getDistServerMtimeMs();
  writeBuildState({
    source_fingerprint: sourceFingerprint,
    built_at: new Date().toISOString(),
    dist_server_mtime_ms: Number.isFinite(distServerMtimeMs) ? distServerMtimeMs : 0,
    index_bundle: bundle ? bundle.name : '',
    index_bundle_size_bytes: bundle ? bundle.size : 0,
    adopted_existing_dist: true,
  });

  return true;
}

function computeSourceFingerprint() {
  const hash = crypto.createHash('sha256');
  const scanRoots = [
    path.join(__dirname, 'app'),
    path.join(__dirname, 'src'),
    path.join(__dirname, 'public'),
  ];
  const skipDirs = new Set(['node_modules', 'dist', '.expo', 'web-build', '.next', '.git']);
  const rootFiles = [
    'package.json',
    'yarn.lock',
    'app.json',
    'babel.config.js',
    'metro.config.js',
    'tsconfig.json',
    'expo-env.d.ts',
  ];

  function feed(relativePath, stat) {
    hash.update(`${relativePath}|${stat.size}|${Math.floor(stat.mtimeMs)}\n`);
  }

  function walk(dir) {
    if (!fs.existsSync(dir)) return;
    const entries = fs.readdirSync(dir, { withFileTypes: true })
      .sort((a, b) => a.name.localeCompare(b.name));
    for (const ent of entries) {
      if (ent.name.startsWith('.')) continue;
      const abs = path.join(dir, ent.name);
      const rel = path.relative(__dirname, abs).replace(/\\/g, '/');
      if (ent.isDirectory()) {
        if (skipDirs.has(ent.name)) continue;
        walk(abs);
      } else if (ent.isFile()) {
        if (rel === 'public/sw.js') continue;
        try {
          const stat = fs.statSync(abs);
          feed(rel, stat);
        } catch {
          // ignore ephemeral fs races
        }
      }
    }
  }

  for (const root of scanRoots) walk(root);

  for (const file of rootFiles) {
    const abs = path.join(__dirname, file);
    if (!fs.existsSync(abs)) continue;
    try {
      const stat = fs.statSync(abs);
      feed(file, stat);
    } catch {
      // ignore
    }
  }

  return hash.digest('hex');
}

function cleanExportStaging() {
  const targets = [
    path.join(DIST_DIR, 'client', '_expo', 'static', 'js', 'web'),
    path.join(DIST_DIR, 'client', '_expo', 'static', 'css', 'web'),
    SERVER_DIR,
  ];

  for (const target of targets) {
    try {
      if (!fs.existsSync(target)) continue;
      fs.rmSync(target, {
        recursive: true,
        force: true,
        maxRetries: 8,
        retryDelay: 120,
      });
    } catch (err) {
      console.warn('[dist-self-heal] staging cleanup skipped for', target, '-', err.message);
    }
  }
}

function cleanDistServerRecovery() {
  if (!fs.existsSync(SERVER_DIR)) return;

  const attempts = [
    () => fs.rmSync(SERVER_DIR, { recursive: true, force: true, maxRetries: 10, retryDelay: 180 }),
    () => {
      const tombstone = `${SERVER_DIR}.stale.${Date.now()}`;
      fs.renameSync(SERVER_DIR, tombstone);
      fs.rmSync(tombstone, { recursive: true, force: true, maxRetries: 10, retryDelay: 180 });
    },
  ];

  for (const run of attempts) {
    try {
      if (!fs.existsSync(SERVER_DIR)) return;
      run();
      if (!fs.existsSync(SERVER_DIR)) return;
    } catch (_err) {
      // continue to next recovery strategy
    }
  }

  if (fs.existsSync(SERVER_DIR)) {
    throw new Error(`Unable to clean dist/server before export: ${SERVER_DIR}`);
  }
}

function runStaticExportBuild(reason, sourceFingerprint) {
  const t0 = Date.now();
  console.log(`[dist-self-heal] Triggered: ${reason}`);
  updateDistRuntimeStatus({
    mode: 'self-heal',
    last_reason: reason,
    last_result: 'running',
    last_build_error: '',
    last_build_duration_ms: 0,
  });

  const env = {
    ...process.env,
    CI: process.env.CI || '1',
    EXPO_NO_INTERACTIVE: '1',
    NODE_OPTIONS: EXPORT_NODE_OPTIONS,
    METRO_MAX_WORKERS: process.env.METRO_MAX_WORKERS || FRONTEND_ENV.METRO_MAX_WORKERS || '1',
    FORCE_COLOR: process.env.FORCE_COLOR || '0',
  };

  try {
    try {
      fs.writeFileSync(
        EXPORT_BUILD_LOCK_FILE,
        JSON.stringify({ pid: process.pid, started_at: new Date().toISOString(), reason }, null, 2),
        'utf-8',
      );
    } catch (_lockErr) {
      // non-blocking
    }

    ensureReactNativeWebBabelRuntimeShim();

    const i18nSeedScript = path.join(__dirname, '..', 'scripts', 'i18n_v2_seed_locales.py');
    const shouldRunI18nSeed = String(process.env.RUN_I18N_SEED || '').trim() === '1';
    if (shouldRunI18nSeed && fs.existsSync(i18nSeedScript)) {
      try {
        execFileSync('python3', [i18nSeedScript], {
          cwd: __dirname,
          stdio: ['ignore', 'pipe', 'pipe'],
          env,
          timeout: 45000,
          killSignal: 'SIGKILL',
        });
      } catch (seedErr) {
        const stderr = (seedErr.stderr && seedErr.stderr.toString()) || '';
        const concise = stderr.split('\n').find(Boolean) || seedErr.message;
        console.warn('[dist-self-heal] i18n seed skipped (non-blocking):', concise);
      }
    }

    execFileSync('node', ['scripts/enforce-exact-expo-pin.js'], {
      cwd: __dirname,
      stdio: 'inherit',
      env,
    });

    execFileSync('node', ['scripts/verify-package-json.js'], {
      cwd: __dirname,
      stdio: 'inherit',
      env,
    });

    execFileSync('node', ['scripts/runtime-crash-sentinel.js', '--scope=critical'], {
      cwd: __dirname,
      stdio: 'inherit',
      env,
    });

    execFileSync('node', ['scripts/ui-contract-gate.js'], {
      cwd: __dirname,
      stdio: 'inherit',
      env,
    });

    execFileSync('node', ['scripts/sidenav-gallery-parity-gate.js'], {
      cwd: __dirname,
      stdio: 'inherit',
      env,
    });

    execFileSync('node', ['scripts/contrast-gate.js'], {
      cwd: __dirname,
      stdio: 'inherit',
      env,
    });

    execFileSync('node', ['scripts/brand-exclusion-gate.js'], {
      cwd: __dirname,
      stdio: 'inherit',
      env,
    });

    execFileSync('node', ['scripts/brand-exclusion-canary.js'], {
      cwd: __dirname,
      stdio: 'inherit',
      env,
    });

    execFileSync('node', ['scripts/theme-build-gate.js'], {
      cwd: __dirname,
      stdio: 'inherit',
      env,
    });

    clearMetroCaches('pre_static_export_build', { deep: true });

  const hadDistBeforeBuild = hasDistArtifacts();
    if (!hadDistBeforeBuild) {
      cleanDistServerRecovery();
      cleanExportStaging();
    } else {
      console.log('[dist-self-heal] Preserving last-known-good dist during forced rebuild.');
    }

    execFileSync('node', ['node_modules/expo/bin/cli', 'export', '--platform', 'web', '--max-workers', String(env.METRO_MAX_WORKERS)], {
      cwd: __dirname,
      stdio: 'inherit',
      env,
      timeout: 480000,
      killSignal: 'SIGKILL',
    });

    const verifiedBundle = verifyStaticExportArtifacts();
    console.log(`[dist-self-heal] verified index bundle ${verifiedBundle.name} (${verifiedBundle.size} bytes)`);

    execFileSync('node', ['scripts/bump-sw.js'], {
      cwd: __dirname,
      stdio: 'inherit',
      env,
    });

    execFileSync('node', ['scripts/precompress-assets.js'], {
      cwd: __dirname,
      stdio: 'inherit',
      env,
    });

    const builtBundle = verifyStaticExportArtifacts();

    const distServerMtimeMs = getDistServerMtimeMs();
    const writeResult = writeBuildState({
      source_fingerprint: sourceFingerprint,
      built_at: new Date().toISOString(),
      dist_server_mtime_ms: Number.isFinite(distServerMtimeMs) ? distServerMtimeMs : builtBundle.mtime,
      index_bundle: builtBundle.name,
      index_bundle_size_bytes: builtBundle.size,
      adopted_existing_dist: false,
    });
    if (!writeResult.ok) {
      throw new Error('Dist verification failed: unable to persist build-state metadata.');
    }

    updateDistRuntimeStatus({
      mode: 'dist',
      last_reason: reason,
      last_result: 'success',
      last_build_duration_ms: Date.now() - t0,
      last_build_error: '',
    });
    console.log(`[dist-self-heal] ✓ static export refreshed in ${Date.now() - t0} ms`);
    return true;
  } catch (err) {
    updateDistRuntimeStatus({
      mode: 'degraded',
      last_reason: reason,
      last_result: 'failed',
      last_build_duration_ms: Date.now() - t0,
      last_build_error: String(err?.message || 'unknown build error'),
    });
    console.error('[dist-self-heal] ✗ static export refresh failed:', err.message);
    return false;
  } finally {
    try {
      fs.rmSync(EXPORT_BUILD_LOCK_FILE, { force: true });
    } catch (_err) {
      // non-blocking
    }
  }
}

function ensureDistUpToDate() {
  const sourceFingerprint = computeSourceFingerprint();
  const hydratedBuildState = hydrateBuildStateFromExistingDist(sourceFingerprint);
  const state = readBuildState();
  const distExists = hasDistArtifacts();
  const stateUsable = isBuildStateUsable(state);

  const fingerprintChanged = !state || String(state.source_fingerprint || '') !== sourceFingerprint;

  if (distExists && !stateUsable) {
    console.warn('[dist-self-heal] build_state missing/invalid while dist exists; forcing static export rebuild.');
    const rebuilt = runStaticExportBuild('missing_or_invalid_build_state', sourceFingerprint);
    if (rebuilt) {
      return true;
    }
    updateDistRuntimeStatus({
      mode: 'expo-fallback',
      last_reason: 'build_state_missing_rebuild_failed',
      last_result: 'failed',
    });
    return false;
  }

  if (distExists && !fingerprintChanged) {
    const reason = hydratedBuildState
      ? 'dist_adopted_existing_state'
      : 'fingerprint_unchanged';
    if (hydratedBuildState) {
      console.log('[dist-self-heal] Adopted existing dist and hydrated missing build-state metadata.');
    } else {
      console.log('[dist-self-heal] Dist is up-to-date (fingerprint unchanged).');
    }
    updateDistRuntimeStatus({
      mode: 'dist',
      last_reason: reason,
      last_result: 'success',
      last_build_error: '',
    });
    return true;
  }

  if (!distExists) {
    const blockingSelfHealEnabled = String(
      process.env.BLOCKING_DIST_SELF_HEAL
      || FRONTEND_ENV.BLOCKING_DIST_SELF_HEAL
      || '',
    ).trim() === '1';

    const activeLock = getActiveExportBuildLock();
    const canUseExpoFallbackNow = canReachLocalPort(EXPO_DEV_PORT);
    const shouldRunBlockingSelfHeal = blockingSelfHealEnabled && !activeLock;

    if (blockingSelfHealEnabled && canUseExpoFallbackNow && !activeLock) {
      console.warn('[dist-self-heal] dist artifacts missing; blocking self-heal remains enabled and will run once at startup even with Expo fallback available.');
    }

    if (shouldRunBlockingSelfHeal) {
      if (activeLock) {
        console.warn(
          `[dist-self-heal] active export lock detected (pid=${activeLock.pid}, reason=${activeLock.reason || 'unknown'}); skipping duplicate startup rebuild.`
        );
        updateDistRuntimeStatus({
          mode: 'expo-fallback',
          last_reason: 'dist_missing_active_export_lock',
          last_result: 'degraded',
          last_build_error: '',
        });
        return false;
      }

      clearMetroCaches('dist_missing_startup_blocking_self_heal', { deep: true });
      console.warn('[dist-self-heal] dist artifacts missing; attempting bounded static export recovery.');
      const rebuilt = runStaticExportBuild('dist_missing_startup', sourceFingerprint);
      if (rebuilt) {
        return true;
      }
      console.warn('[dist-self-heal] blocking self-heal failed; falling back to Expo dev proxy.');
    } else {
      console.warn('[dist-self-heal] dist artifacts missing; skipping blocking export and falling back to Expo dev proxy.');
    }

    if (DIST_FORCE_REBUILD_ENABLED && !shouldRunBlockingSelfHeal) {
      console.warn('[dist-self-heal] DIST_FORCE_REBUILD is enabled but startup remains non-blocking while dist artifacts are missing.');
    }

    updateDistRuntimeStatus({
      mode: 'expo-fallback',
      last_reason: 'dist_missing_non_blocking_startup',
      last_result: 'degraded',
    });
    return false;
  }

  // Dist exists but fingerprint changed.
  // Platform freshness policy: never serve stale dist for preview traffic.
  console.warn('[dist-self-heal] Source fingerprint changed; forcing startup static export rebuild to prevent stale preview bundle.');
  const rebuilt = runStaticExportBuild('fingerprint_changed_startup', sourceFingerprint);
  if (rebuilt) {
    return true;
  }

  updateDistRuntimeStatus({
    mode: 'expo-fallback',
    last_reason: 'fingerprint_changed_rebuild_failed',
    last_result: 'failed',
  });
  return false;
}

let HAS_DIST = false;

// ─────────────────────────────────────────────────────────────────────
// Startup syntax probe (black-screen prevention)
// ─────────────────────────────────────────────────────────────────────
//
// Why: On Apr 25, 2026 a JSX auto-fixer corrupted 5 source files. Metro's
// bundler crashed (`SyntaxError: Unexpected token`); `dist/` never built;
// this server fell back to the dev proxy where the dev server OOM-looped;
// the preview iframe rendered a black screen with infinite spinner.
//
// To convert that silent failure mode into a fast, visible CrashLoopBackOff
// at deploy-time (so future regressions are caught here, not on a user's
// phone), we run two cheap probes BEFORE serving the first request:
//
//   1. auto_fixer_corruption_guard.py — catches the 5 known mangled
//      patterns (arrow functions split by `=` / `>` and TS generics with
//      props leaked in). ~50 ms.
//
//   2. @babel/parser probe — Metro uses Babel; we parse every .ts/.tsx
//      / .js/.jsx in src/ + app/ with the same JSX + TS plugins Metro
//      uses. Any unparseable file → fail. ~1-2 s for ~600 files. This
//      catches ALL syntax errors, not just the 5 known shapes.
//
// Either probe failing → process.exit(1) → supervisor flags a CrashLoop
// instead of silently proxying broken HTML to the user's phone.
//
// Bypass switch (use sparingly, only for emergency hot-patching):
//   SKIP_STARTUP_PROBE=1 node serve-production.js
function runStartupSyntaxProbe() {
  const skipStartupProbe = String(
    process.env.SKIP_STARTUP_PROBE
    || FRONTEND_ENV.SKIP_STARTUP_PROBE
    || '',
  ).trim() === '1';

  if (skipStartupProbe) {
    console.warn('[startup-probe] SKIPPED via SKIP_STARTUP_PROBE=1 — '
      + 'do not use in production. The black-screen guardrail is OFF.');
    return;
  }

  const t0 = Date.now();

  // ── Probe 1: auto-fixer corruption guard ──
  const guardPath = path.join(__dirname, '..', 'scripts', 'auto_fixer_corruption_guard.py');
  if (fs.existsSync(guardPath)) {
    try {
      execFileSync('python3', [guardPath], { stdio: ['ignore', 'pipe', 'pipe'] });
    } catch (e) {
      const stderr = (e.stderr && e.stderr.toString()) || e.message;
      const stdout = (e.stdout && e.stdout.toString()) || '';
      console.error('\n[startup-probe] ✗ auto-fixer corruption guard FAILED');
      console.error('  Refusing to start the production server. Black-screen risk.\n');
      if (stdout.trim()) console.error(stdout);
      if (stderr.trim()) console.error(stderr);
      process.exit(1);
    }
  } else {
    console.warn('[startup-probe] auto-fixer guard script not found at',
      guardPath, '— skipping (run `yarn guard:auto-fixer` manually).');
  }

  // ── Probe 2: Babel parse pass over every source file ──
  let parser;
  try {
    parser = require('@babel/parser');
  } catch {
    console.warn('[startup-probe] @babel/parser unavailable — skipping JSX parse probe.');
    return;
  }
  const SCAN_DIRS = [path.join(__dirname, 'src'), path.join(__dirname, 'app')];
  const SOURCE_EXT = /\.(tsx|ts|jsx|js)$/;
  const SKIP_DIRS = new Set(['node_modules', 'dist', '.expo', 'web-build', '.next']);

  const failures = [];
  let scanned = 0;

  function walk(dir) {
    let entries;
    try { entries = fs.readdirSync(dir, { withFileTypes: true }); }
    catch { return; }
    for (const ent of entries) {
      if (ent.isDirectory()) {
        if (SKIP_DIRS.has(ent.name) || ent.name.startsWith('.')) continue;
        walk(path.join(dir, ent.name));
      } else if (ent.isFile() && SOURCE_EXT.test(ent.name)) {
        const p = path.join(dir, ent.name);
        let src;
        try { src = fs.readFileSync(p, 'utf-8'); } catch { continue; }
        scanned++;
        try {
          parser.parse(src, {
            sourceType: 'module',
            allowReturnOutsideFunction: true,
            plugins: ['jsx', 'typescript', 'classProperties', 'optionalChaining',
                      'nullishCoalescingOperator', 'topLevelAwait', 'decorators-legacy'],
          });
        } catch (err) {
          // Babel parse error → exact file:line:column + reason
          const loc = err.loc ? `${err.loc.line}:${err.loc.column}` : '?:?';
          const rel = path.relative(__dirname, p);
          failures.push({ file: rel, loc, message: err.message.split('\n')[0] });
          // Cap at 10 to keep logs readable; we already know the build is broken.
          if (failures.length >= 10) break;
        }
      }
    }
    if (failures.length >= 10) return;
  }
  for (const d of SCAN_DIRS) {
    if (fs.existsSync(d)) walk(d);
    if (failures.length >= 10) break;
  }

  if (failures.length > 0) {
    console.error('\n[startup-probe] ✗ Babel parse probe FAILED — '
      + failures.length + ' file(s) cannot be parsed by Metro. '
      + 'Refusing to start (black-screen prevention):\n');
    for (const f of failures) {
      console.error(`  ${f.file}:${f.loc}`);
      console.error(`    ${f.message}\n`);
    }
    console.error('Fix the syntax error(s) above, OR set SKIP_STARTUP_PROBE=1 '
      + 'for emergency hot-patching only.\n');
    process.exit(1);
  }

  console.log(`[startup-probe] ✓ ${scanned} source files parsed cleanly · `
    + `auto-fixer guard clean · ${Date.now() - t0} ms`);
}

runStartupSyntaxProbe();
runSidebarPolicyGuard();
HAS_DIST = ensureDistUpToDate();
if (!HAS_DIST) {
  updateDistRuntimeStatus({
    mode: 'expo-fallback',
    last_reason: DIST_RUNTIME_STATUS.last_reason || 'startup_dist_unavailable',
    last_result: DIST_RUNTIME_STATUS.last_result === 'unknown' ? 'degraded' : DIST_RUNTIME_STATUS.last_result,
  });
}
console.log(`[startup] API proxy backend port selected: ${backendPort}`);

const app = express();
const expoWarmupState = {
  ready: false,
  warming: false,
  last_started_at: '',
  last_ready_at: '',
  last_error: '',
};
let distPromotionRestartScheduled = false;

function scheduleDistPromotionRestart(reason = 'dist_artifacts_detected') {
  if (distPromotionRestartScheduled) return;
  distPromotionRestartScheduled = true;
  console.log(`[dist-fallback] scheduling process restart to promote dist mode (${reason}).`);
  setTimeout(() => {
    process.exit(0);
  }, 180);
}

function startExpoWarmup(reason = 'startup') {
  if (HAS_DIST || expoWarmupState.warming || expoWarmupState.ready) return;
  if (!canReachLocalPort(EXPO_DEV_PORT)) return;

  expoWarmupState.warming = true;
  expoWarmupState.last_started_at = new Date().toISOString();
  expoWarmupState.last_error = '';
  console.log(`[expo-fallback] warmup started (${reason}).`);

  const req = http.request({
    host: '127.0.0.1',
    port: EXPO_DEV_PORT,
    path: '/',
    method: 'GET',
    headers: {
      'user-agent': 'rac-expo-warmup-probe',
      accept: 'text/html,*/*;q=0.8',
      origin: `http://127.0.0.1:${EXPO_DEV_PORT}`,
    },
  }, (res) => {
    res.resume();
    res.on('end', () => {
      expoWarmupState.warming = false;
      if (res.statusCode && res.statusCode >= 200 && res.statusCode < 500) {
        expoWarmupState.ready = true;
        expoWarmupState.last_ready_at = new Date().toISOString();
        console.log(`[expo-fallback] warmup ready (status=${res.statusCode}).`);
      } else {
        expoWarmupState.last_error = `warmup status ${res.statusCode || 'unknown'}`;
      }
    });
  });

  req.setTimeout(240000, () => {
    expoWarmupState.warming = false;
    expoWarmupState.last_error = 'warmup_timeout';
    req.destroy();
  });

  req.on('error', (err) => {
    expoWarmupState.warming = false;
    expoWarmupState.last_error = String(err?.message || 'warmup_error');
  });

  req.end();
}

function sanitizeExpoProxyRequest(proxyReq, req) {
  try {
    if (proxyReq && typeof proxyReq.removeHeader === 'function') {
      // Prevent Expo dev-server CORS middleware from rejecting proxied preview origins.
      proxyReq.removeHeader('origin');
      proxyReq.removeHeader('referer');
    }

    if (proxyReq && typeof proxyReq.setHeader === 'function') {
      const host = getEffectiveRequestHost(req);
      if (host) proxyReq.setHeader('x-forwarded-host', host);
    }
  } catch (err) {
    console.warn('[expo-fallback] proxy request sanitization skipped:', err.message);
  }
}

function ensureExpoFallbackDevServer() {
  if (!canReachLocalPort(EXPO_DEV_PORT)) {
    expoWarmupState.ready = false;

    const nowMs = Date.now();
    if (nowMs - expoFallbackUnavailableLastLogAtMs > 5000) {
      console.warn(
        `[expo-fallback] Expo dev server not reachable on port ${EXPO_DEV_PORT}; awaiting supervisor-managed expo service.`
      );
      expoFallbackUnavailableLastLogAtMs = nowMs;
    }
    return false;
  }

  if (!expoWarmupState.ready) {
    startExpoWarmup('readiness-gate');
    // Do not hard-block user requests while warmup is in progress.
    // Allow proxying and let Expo compile progressively.
    return true;
  }

  return true;
}

const expoFallbackProxy = createProxyMiddleware({
  target: `http://127.0.0.1:${EXPO_DEV_PORT}`,
  changeOrigin: true,
  ws: true,
  timeout: 120000,
  proxyTimeout: 120000,
  onProxyReq: (proxyReq, req, _res) => {
    sanitizeExpoProxyRequest(proxyReq, req);
  },
  onProxyReqWs: (proxyReq, req, _socket, _options, _head) => {
    sanitizeExpoProxyRequest(proxyReq, req);
  },
  onError: (err, _req, res) => {
    expoWarmupState.ready = false;
    startExpoWarmup('proxy-error');
    console.error('Expo fallback proxy error:', err.message);
    if (!res.headersSent) {
      res.status(503).send('Frontend fallback is warming up. Please retry in a few seconds.');
    }
  },
});

function sendDistClientFallback(req, res, next) {
  const requestedPath = String(req.path || '').replace(/^\/+/, '');
  const normalizedPath = requestedPath.toLowerCase();
  const isRootRequest = !normalizedPath || normalizedPath === '/';
  const staticFallbackAllowlist = new Set(['v7-preview', 'offline', 'ms-login', 'qr']);
  const candidates = [];

  if (isRootRequest) {
    candidates.push('v7-preview.html', 'offline.html', 'ms-login.html');
  } else {
    const canonicalPath = normalizedPath
      .replace(/\.html$/, '')
      .replace(/\/index$/, '')
      .replace(/\/+$/, '');

    const isStaticFallbackRoute = staticFallbackAllowlist.has(canonicalPath);
    if (!isStaticFallbackRoute) {
      return next();
    }

    if (normalizedPath.endsWith('.html')) candidates.push(normalizedPath);
    candidates.push(`${canonicalPath}.html`);
    candidates.push(path.join(canonicalPath, 'index.html'));
  }

  for (const relPath of candidates) {
    const safeRelPath = String(relPath || '').replace(/^\/+/, '');
    const absPath = path.join(CLIENT_DIR, safeRelPath);
    if (fs.existsSync(absPath) && fs.statSync(absPath).isFile()) {
      res.setHeader('Cache-Control', 'no-store, no-cache, must-revalidate, max-age=0');
      return res.sendFile(absPath);
    }
  }

  return next();
}

app.use((req, res, next) => {
  const buildState = readBuildState() || {};
  const bundleName = String(buildState.index_bundle || '');
  const bundleHash = extractBundleHash(bundleName);
  res.setHeader('x-rac-serving-mode', HAS_DIST ? 'dist-last-known-good' : 'expo-proxy-fallback');
  res.setHeader('x-rac-dist-runtime-result', toSafeHeaderValue(DIST_RUNTIME_STATUS.last_result || 'unknown'));
  if (bundleHash) {
    res.setHeader('x-rac-dist-bundle-hash', bundleHash);
  }
  next();
});

// Wrapper artifact route recovery:
// /wo, /s/*, and /loading-preview are shell wrapper artifacts and not app routes.
// Canonicalize to root on preview requests so users never see stale wrapper pages.
app.use((req, res, next) => {
  if (!isDocumentLikeRequest(req)) return next();
  const pathName = String(req.path || '/');
  const trackMatch = pathName.match(/^\/careers\/track\/([^/?#]+)/i);
  if (!trackMatch) return next();

  const applicationId = decodeURIComponent(String(trackMatch[1] || '').trim());
  if (!applicationId) return next();

  const target = withMergedQueryPath(req, '/track-application', {
    id: applicationId,
    ref: 'legacy-careers-track-link',
  });
  res.setHeader('Cache-Control', 'no-store, no-cache, must-revalidate, max-age=0');
  return res.redirect(307, target);
});

app.use((req, res, next) => {
  if (!requestIsPreview(req)) return next();
  if (!isDocumentLikeRequest(req)) return next();
  if (!isWrapperArtifactPath(req.path)) return next();

  const target = withMergedQueryPath(req, '/', { previewHostRecovered: 1 });
  res.setHeader('x-rac-wrapper-path-recovered', String(req.path || '/'));
  res.setHeader('Cache-Control', 'no-store, no-cache, must-revalidate, max-age=0');
  return res.redirect(307, target);
});

// Preview host consistency guard.
// Platform rule: each fork gets its own auto-assigned preview URL.
// Enforce canonical redirect only for trusted shell hosts to avoid stale wrapper snapshots.
app.use((req, res, next) => {
  const expectedHost = resolveExpectedPreviewHost(req);
  if (!expectedHost) return next();
  const reqHost = getEffectiveRequestHost(req);

  if (!reqHost || reqHost === expectedHost) return next();
  const isPreviewHost = isPreviewLikeHost(reqHost);
  if (!isPreviewHost) return next();

  if (isTrustedShellHost(reqHost) && isDocumentLikeRequest(req)) {
    const safePath = canonicalizeShellPath(req.path || '/');
    const target = `https://${expectedHost}${safePath}${req.url.includes('?') ? `?${String(req.url).split('?')[1]}` : ''}`;
    res.setHeader('x-rac-preview-host-redirect', `${reqHost}->${expectedHost}`);
    res.setHeader('Cache-Control', 'no-store, no-cache, must-revalidate, max-age=0');
    return res.redirect(307, target);
  }

  // Keep serving current host and expose drift for diagnostics only for non-shell preview hosts.
  res.setHeader('x-rac-preview-host-mismatch', `${reqHost}!=${expectedHost}`);
  return next();
});

// Lightweight preview health endpoint for scheduler probes.
// Keep this route dependency-free so health checks never trigger page rendering.
app.get('/_preview/health', (req, res) => {
  let distServerMtimeMs = null;
  try {
    if (fs.existsSync(SERVER_DIR)) {
      distServerMtimeMs = fs.statSync(SERVER_DIR).mtimeMs;
    }
  } catch {
    distServerMtimeMs = null;
  }

  const buildState = readBuildState();
  const bundleName = String((buildState && buildState.index_bundle) || '');
  const bundleHash = extractBundleHash(bundleName);

  res.setHeader('Cache-Control', 'no-store');
  return res.status(200).json({
    ok: true,
    has_dist: HAS_DIST,
    expected_preview_host: resolveExpectedPreviewHost(req) || '',
    active_bundle_hash: bundleHash,
    backend_port: backendPort,
    uptime_sec: Math.round(process.uptime()),
    build_state: buildState,
    dist_runtime: {
      ...DIST_RUNTIME_STATUS,
      has_dist_artifacts: hasDistArtifacts(),
      dist_server_mtime_ms: distServerMtimeMs,
      expo_fallback: {
        ...expoWarmupState,
      },
    },
  });
});

// API proxy - forward /api requests to backend
app.use('/api', createProxyMiddleware({
  target: `http://127.0.0.1:8001`,
  router: () => `http://127.0.0.1:${backendPort}`,
  changeOrigin: true,
  ws: true,
  timeout: 20000,
  proxyTimeout: 20000,
  pathRewrite: (path) => (path.startsWith('/api/') ? path : `/api${path}`),
  onError: (err, req, res) => {
    console.error('API proxy error:', err.message);
    redetectBackendPortOnFailure();
    res.status(502).json({ error: 'Backend unavailable' });
  },
}));

// Compatibility alias for stale hashed logo requests observed during fallback boot.
app.get(/^\/assets\/images\/logo\.[a-f0-9]{32}\.png$/i, (req, res, next) => {
  const logoPath = path.join(__dirname, 'assets', 'images', 'logo.png');
  if (!fs.existsSync(logoPath)) return next();
  const previewRequest = requestIsPreview(req);
  res.setHeader('Cache-Control', previewRequest
    ? 'no-store, no-cache, must-revalidate, max-age=0'
    : 'public, max-age=3600');
  return res.sendFile(logoPath);
});

// If no dist folder, proxy everything to expo dev server
if (!HAS_DIST) {
  console.log('No dist folder found, proxying to Expo dev server on port', EXPO_DEV_PORT);
  const hasClientFallback = hasDistClientFallbackArtifacts();
  if (hasClientFallback) {
    console.log('[dist-fallback] serving dist/client html fallback while Expo warms.');
    app.use((req, res, next) => {
      if (req.path.startsWith('/api/')) return next();
      if (req.path.startsWith('/_preview/')) return next();
      if (req.path.startsWith('/_expo/')) return next();
      if (req.path.startsWith('/assets/')) return next();
      if (req.path.startsWith('/fonts/')) return next();
      if (req.path.startsWith('/support/')) return next();
      return sendDistClientFallback(req, res, next);
    });

    app.use('/assets', express.static(CLIENT_DIR, {
      maxAge: 0,
      setHeaders: (res) => {
        res.setHeader('Cache-Control', 'no-store, no-cache, must-revalidate, max-age=0');
      },
    }));

    app.use('/fonts', express.static(path.join(DIST_DIR, 'fonts'), {
      maxAge: 0,
      setHeaders: (res) => {
        res.setHeader('Cache-Control', 'no-store, no-cache, must-revalidate, max-age=0');
      },
    }));
  }
  app.use((req, _res, next) => {
    if (HAS_DIST) return next();
    if (!hasDistArtifacts()) return next();
    HAS_DIST = true;
    updateDistRuntimeStatus({
      mode: 'dist',
      last_reason: 'dist_artifacts_detected_during_fallback',
      last_result: 'success',
      last_build_error: '',
    });
    scheduleDistPromotionRestart('dist_artifacts_detected_during_fallback');
    next();
  });
  startExpoWarmup('fallback-startup');
  ensureExpoFallbackDevServer();
  // Never hard-block with synthetic 503 while Metro is warming.
  // Let requests flow to Expo proxy so initial compile can complete.
  app.use((req, _res, next) => {
    ensureExpoFallbackDevServer();
    next();
  });
  app.use((req, _res, next) => {
    if (req.path === '/certificate-verify' || req.path.startsWith('/certificate-verify/')) {
      const queryStart = req.url.indexOf('?');
      req.url = queryStart >= 0 ? `/${req.url.slice(queryStart)}` : '/';
    }
    next();
  });
  app.use('/', expoFallbackProxy);
  
  app.listen(PORT, '0.0.0.0', () => {
    console.log(`Production server running on port ${PORT} (proxying to Expo dev server)`);
  });
} else {

// Gzip compression (fallback for non-precompressed assets)
app.use(compression({ level: 6, threshold: 512 }));

// Serve pre-compressed Brotli/Gzip JS files for fastest delivery
app.use('/_expo/static', (req, res, next) => {
  if (!req.path.endsWith('.js')) return next();

  const accept = req.headers['accept-encoding'] || '';
  const basePath = path.join(CLIENT_DIR, '_expo', 'static', req.path);
  const previewRequest = requestIsPreview(req);

  // Try Brotli first (best compression)
  if (accept.includes('br') && fs.existsSync(basePath + '.br')) {
    res.setHeader('Content-Encoding', 'br');
    res.setHeader('Content-Type', 'application/javascript');
    res.setHeader('Cache-Control', previewRequest
      ? 'no-store, no-cache, must-revalidate, max-age=0'
      : 'public, max-age=31536000, immutable');
    res.setHeader('Vary', 'Accept-Encoding');
    return res.sendFile(basePath + '.br');
  }

  // Try Gzip
  if (accept.includes('gzip') && fs.existsSync(basePath + '.gz')) {
    res.setHeader('Content-Encoding', 'gzip');
    res.setHeader('Content-Type', 'application/javascript');
    res.setHeader('Cache-Control', previewRequest
      ? 'no-store, no-cache, must-revalidate, max-age=0'
      : 'public, max-age=31536000, immutable');
    res.setHeader('Vary', 'Accept-Encoding');
    return res.sendFile(basePath + '.gz');
  }

  next();
});

// Serve service worker from root with correct headers
app.get('/sw.js', (req, res) => {
  const swPath = path.join(CLIENT_DIR, 'sw.js');
  if (fs.existsSync(swPath)) {
    res.setHeader('Content-Type', 'application/javascript');
    res.setHeader('Cache-Control', 'no-cache, no-store, must-revalidate');
    res.setHeader('Service-Worker-Allowed', '/');
    return res.sendFile(swPath);
  }
  res.status(404).end();
});

// Serve offline fallback page
app.get('/offline.html', (req, res) => {
  const offlinePath = path.join(CLIENT_DIR, 'offline.html');
  if (fs.existsSync(offlinePath)) {
    res.setHeader('Content-Type', 'text/html');
    res.setHeader('Cache-Control', 'no-cache');
    return res.sendFile(offlinePath);
  }
  res.status(404).end();
});

// Serve PWA manifest with correct MIME type
app.get('/manifest.json', (req, res) => {
  const manifestPath = path.join(CLIENT_DIR, 'manifest.json');
  if (fs.existsSync(manifestPath)) {
    res.setHeader('Content-Type', 'application/manifest+json');
    res.setHeader('Cache-Control', 'public, max-age=86400');
    return res.sendFile(manifestPath);
  }
  res.status(404).end();
});

// Security headers
app.use((req, res, next) => {
  res.setHeader('X-Content-Type-Options', 'nosniff');
  // Allow iframe embedding from Emergent platform and same-origin
  res.setHeader('Content-Security-Policy', "frame-ancestors 'self' https://*.emergentagent.com https://*.emergent.sh https://app.emergent.sh");
  next();
});

// Long-lived cache for hashed static assets
app.use('/_expo/static', express.static(path.join(CLIENT_DIR, '_expo', 'static'), {
  maxAge: '365d',
  immutable: true,
  setHeaders: (res, filePath, stat) => {
    try {
      const req = res.req;
      if (requestIsPreview(req)) {
        res.setHeader('Cache-Control', 'no-store, no-cache, must-revalidate, max-age=0');
        res.setHeader('Surrogate-Control', 'no-store');
        res.setHeader('Pragma', 'no-cache');
        res.setHeader('Expires', '0');
      }
    } catch (_err) {
      // non-blocking
    }
  },
}));

// Medium cache for other assets
app.use('/assets', express.static(path.join(CLIENT_DIR, 'assets'), {
  maxAge: '7d',
  setHeaders: (res) => {
    try {
      if (requestIsPreview(res.req)) {
        res.setHeader('Cache-Control', 'no-store, no-cache, must-revalidate, max-age=0');
        res.setHeader('Surrogate-Control', 'no-store');
      }
    } catch (_err) {}
  },
}));
app.use('/fonts', express.static(path.join(DIST_DIR, 'fonts'), {
  maxAge: '30d',
  setHeaders: (res) => {
    try {
      if (requestIsPreview(res.req)) {
        res.setHeader('Cache-Control', 'no-store, no-cache, must-revalidate, max-age=0');
        res.setHeader('Surrogate-Control', 'no-store');
      }
    } catch (_err) {}
  },
}));

// Short cache for root static files
app.use(express.static(CLIENT_DIR, {
  maxAge: '1h',
  index: false,
  setHeaders: (res) => {
    try {
      if (requestIsPreview(res.req)) {
        res.setHeader('Cache-Control', 'no-store, no-cache, must-revalidate, max-age=0');
        res.setHeader('Surrogate-Control', 'no-store');
      }
    } catch (_err) {}
  },
}));
app.use(express.static(DIST_DIR, {
  maxAge: '1h',
  index: false,
  setHeaders: (res) => {
    try {
      if (requestIsPreview(res.req)) {
        res.setHeader('Cache-Control', 'no-store, no-cache, must-revalidate, max-age=0');
        res.setHeader('Surrogate-Control', 'no-store');
      }
    } catch (_err) {}
  },
}));

// Build timestamp for cache busting
const BUILD_TS = Date.now();

// Find the latest index bundle in client dir
function getLatestIndexBundle() {
  const jsWebDir = path.join(CLIENT_DIR, '_expo', 'static', 'js', 'web');
  if (!fs.existsSync(jsWebDir)) return null;
  const bundles = fs.readdirSync(jsWebDir)
    .filter(f => /^index-[a-f0-9]+\.js$/.test(f))
    .map(f => ({ name: f, mtime: fs.statSync(path.join(jsWebDir, f)).mtimeMs }))
    .sort((a, b) => b.mtime - a.mtime);
  return bundles.length > 0 ? bundles[0].name : null;
}

function getTransformedHTML(filePath) {
  if (!fs.existsSync(filePath)) return null;
  let html = fs.readFileSync(filePath, 'utf-8');
  // Dynamically swap in latest index bundle to pick up hot-rebuilt code
  const latestBundle = getLatestIndexBundle();
  if (latestBundle) {
    html = html.replace(/index-[a-f0-9]+\.js/g, latestBundle);
  }
  // Add cache-busting query param to all JS file references
  html = html.replace(/(src="[^"]+\.js)(")/g, `$1?v=${BUILD_TS}$2`);
  // Inject cache-purge script to force service worker update
  const cachePurgeScript = `<script>
    (async function(){if(!('serviceWorker' in navigator))return;
    var regs=await navigator.serviceWorker.getRegistrations();regs.forEach(function(r){r.update()});
    var keys=await caches.keys();keys.forEach(function(n){caches.delete(n)});
    var regs=await navigator.serviceWorker.getRegistrations();for(var r of regs){await r.unregister()};})();
  </script>`;
  html = html.replace('</head>', cachePurgeScript + '</head>');
  return html;
}

// SSR handler - catch all routes
app.use((req, res, next) => {
  // Skip if already handled
  if (res.headersSent) return next();

  const cleanPath = req.path.replace(/\/$/, '') || '/';
  const relativePath = cleanPath === '/' ? '' : cleanPath.replace(/^\//, '');

  // Try server-rendered page (exact path)
  const serverPage = path.join(SERVER_DIR, relativePath, 'index.html');
  let html = getTransformedHTML(serverPage);
  if (html) {
    res.setHeader('Content-Type', 'text/html');
    res.setHeader('Cache-Control', 'private, no-store, no-cache, must-revalidate, max-age=0, s-maxage=0');
    res.setHeader('Surrogate-Control', 'no-store');
    res.setHeader('Pragma', 'no-cache');
    res.setHeader('Expires', '0');
    return res.send(html);
  }

  // Try direct HTML file
  const serverFile = path.join(SERVER_DIR, relativePath ? `${relativePath}.html` : 'index.html');
  html = getTransformedHTML(serverFile);
  if (html) {
    res.setHeader('Content-Type', 'text/html');
    res.setHeader('Cache-Control', 'no-store, no-cache, must-revalidate, max-age=0');
    res.setHeader('Surrogate-Control', 'no-store');
    return res.send(html);
  }

  // Try (tabs) directory fallback — Expo puts tab routes under (tabs)/
  const tabsFile = path.join(SERVER_DIR, '(tabs)', `${relativePath}.html`);
  html = getTransformedHTML(tabsFile);
  if (html) {
    res.setHeader('Content-Type', 'text/html');
    res.setHeader('Cache-Control', 'no-store, no-cache, must-revalidate, max-age=0');
    res.setHeader('Surrogate-Control', 'no-store');
    return res.send(html);
  }

  // Try (tabs)/index for root path
  if (cleanPath === '/' || cleanPath === '') {
    const tabsIndex = path.join(SERVER_DIR, '(tabs)', 'index.html');
    html = getTransformedHTML(tabsIndex);
    if (html) {
      res.setHeader('Content-Type', 'text/html');
      res.setHeader('Cache-Control', 'no-store, no-cache, must-revalidate, max-age=0');
      return res.send(html);
    }
  }

function injectFpsMatchOg(html, matchId, req) {
  const host = req.headers['x-forwarded-host'] || req.headers.host || '';
  const proto = req.headers['x-forwarded-proto'] || 'https';
  const origin = host ? `${proto}://${host}` : '';
  const pageUrl = `${origin}/fps-match/${matchId}`;
  const imageUrl = `${origin}/api/games-station/match-card/${matchId}/social-preview.png`;
  const tags = [
    '<meta property="og:type" content="website"/>',
    '<meta property="og:site_name" content="RealAICoach"/>',
    '<meta property="og:title" content="FPS Match Card — RealAICoach Arena"/>',
    '<meta property="og:description" content="Kills, deaths, K/D and best streak from a live multiplayer FPS match. Sign in to play."/>',
    `<meta property="og:url" content="${pageUrl}"/>`,
    `<meta property="og:image" content="${imageUrl}"/>`,
    '<meta property="og:image:type" content="image/png"/>',
    '<meta property="og:image:width" content="1200"/>',
    '<meta property="og:image:height" content="630"/>',
    '<meta name="twitter:card" content="summary_large_image"/>',
    '<meta name="twitter:title" content="FPS Match Card — RealAICoach Arena"/>',
    `<meta name="twitter:image" content="${imageUrl}"/>`,
  ].join('');
  // Crawlers take the FIRST og:* occurrence — strip the static site defaults before injecting.
  html = html.replace(/<meta\s+(?:property="og:[^"]*"|name="twitter:[^"]*")[^>]*\/?>/g, '');
  return html.replace('</head>', tags + '</head>');
}

  // Allow dynamic route handlers that may not have a pre-rendered static html file yet.
  // Serve root index so Expo Router can resolve client-side route segments.
  const dynamicRoutePrefixes = ['/interview-room', '/certificate-verify', '/certificate-operations', '/admin/offers', '/fps-match'];
  if (dynamicRoutePrefixes.some((prefix) => cleanPath === prefix || cleanPath.startsWith(prefix + '/'))) {
    const rootIndexDynamic = path.join(SERVER_DIR, 'index.html');
    html = getTransformedHTML(rootIndexDynamic);
    if (html) {
      const fpsMatch = cleanPath.match(/^\/fps-match\/([A-Za-z0-9_-]{1,32})\/?$/);
      if (fpsMatch) html = injectFpsMatchOg(html, fpsMatch[1], req);
      res.setHeader('Content-Type', 'text/html');
      res.setHeader('Cache-Control', 'no-store, no-cache, must-revalidate, max-age=0');
      res.setHeader('Surrogate-Control', 'no-store');
      return res.send(html);
    }
  }

  // Unknown path → serve +not-found.html with HTTP 404 before the
  // root-index fallback, so bad URLs (e.g. /does-not-exist) render the
  // Page-Not-Found screen instead of silently rendering the welcome home.
  // The client-side `+not-found.tsx` also auto-redirects to / after 2s.
  //
  // NOTE on URL rewriting: Expo Router's client-side bootstrap reads
  // `window.location.pathname` to decide which route to mount. For an
  // unknown path like `/does-not-exist`, expo-router falls through to
  // the Stack root instead of mounting `+not-found.tsx` — the user ends
  // up on the welcome page despite the 404 status. We fix this by
  // injecting a history.replaceState('/+not-found') right before the JS
  // bundle mounts, so the client router sees `/+not-found` and mounts
  // the correct screen. The original mistyped URL is preserved in
  // sessionStorage under `gtec_not_found_from` for telemetry / UX.
  const notFoundPage = path.join(SERVER_DIR, '+not-found.html');
  html = getTransformedHTML(notFoundPage);
  if (html) {
    const original = cleanPath.replace(/"/g, '%22');
    const rewriteScript = `<script>(function(){try{
      var from=${JSON.stringify(original)};
      if(typeof sessionStorage!=='undefined'){sessionStorage.setItem('gtec_not_found_from',from);}
      if(typeof history!=='undefined'&&history.replaceState){history.replaceState(null,'','/+not-found');}
    }catch(e){}})();</script>`;
    html = html.replace('</head>', rewriteScript + '</head>');
    res.status(404);
    res.setHeader('Content-Type', 'text/html');
    res.setHeader('Cache-Control', 'no-store, no-cache, must-revalidate, max-age=0');
    res.setHeader('Surrogate-Control', 'no-store');
    return res.send(html);
  }

  // Fallback to root index
  const rootIndex = path.join(SERVER_DIR, 'index.html');
  html = getTransformedHTML(rootIndex);
  if (html) {
    res.setHeader('Content-Type', 'text/html');
    res.setHeader('Cache-Control', 'no-store, no-cache, must-revalidate, max-age=0');
    res.setHeader('Surrogate-Control', 'no-store');
    return res.send(html);
  }

  // Last resort
  const clientIndex = path.join(CLIENT_DIR, 'index.html');
  html = getTransformedHTML(clientIndex);
  if (html) {
    res.setHeader('Content-Type', 'text/html');
    res.setHeader('Cache-Control', 'no-store, no-cache, must-revalidate, max-age=0');
    res.setHeader('Surrogate-Control', 'no-store');
    return res.send(html);
  }

  // Final fallback: if static SSR artifacts are incomplete for this route,
  // delegate to Expo dev server so preview URLs remain operational.
  if (!canReachLocalPort(EXPO_DEV_PORT)) {
    ensureExpoFallbackDevServer();
    res.setHeader('Retry-After', '5');
    return res.status(503).send('Frontend fallback is warming up. Please retry in a few seconds.');
  }
  return expoFallbackProxy(req, res, () => {
    if (!res.headersSent) {
      res.status(404).send('Not Found');
    }
  });
});

app.listen(PORT, '0.0.0.0', () => {
  console.log(`Production server running on port ${PORT}`);
});
}
