#!/usr/bin/env node
/**
 * Pre-compress JS/CSS/JSON/HTML/SVG files under dist/ into .br and .gz.
 *
 * Rationale: `serve-production.js` already has a pre-compressed asset
 * handler that serves `*.br` and `*.gz` files directly (see lines ~54-79).
 * When the files don't exist, the fallback `compression()` middleware does
 * not reliably compress large bundles served by `express.static`, leaving
 * the main 5.3MB `index-*.js` uncompressed on the wire.
 *
 * Running this script post-export eliminates that hot path:
 *   - Brotli (level 11): best ratio for JS; ~1.1MB for a 5.3MB bundle
 *   - Gzip  (level 9):   fallback for browsers that don't send `br`
 *
 * Tracked by GTEC V2 Performance section — closes the `slow_p50_render`
 * finding observed on 2026-04-24.
 */
const fs = require('fs');
const path = require('path');
const zlib = require('zlib');

const DIST = path.join(__dirname, '..', 'dist');
const EXTS = new Set(['.js', '.css', '.json', '.html', '.svg', '.map']);
const MIN_BYTES = 1024; // below this, compression overhead isn't worth it
const MIN_FREE_MB = Number(process.env.PRECOMPRESS_MIN_FREE_MB || 256);

let compressed = 0;
let skipped = 0;
let totalRaw = 0;
let totalBr = 0;
let totalGz = 0;

function getFreeDiskMb(targetPath) {
  try {
    const stat = fs.statfsSync(targetPath);
    return (stat.bavail * stat.bsize) / (1024 * 1024);
  } catch (_err) {
    return null;
  }
}

function* walk(dir) {
  if (!fs.existsSync(dir)) return;
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) {
      yield* walk(full);
    } else if (entry.isFile()) {
      yield full;
    }
  }
}

function compressFile(file) {
  const ext = path.extname(file).toLowerCase();
  if (!EXTS.has(ext)) return;
  if (file.endsWith('.br') || file.endsWith('.gz')) return;

  const stat = fs.statSync(file);
  if (stat.size < MIN_BYTES) {
    skipped++;
    return;
  }

  const buf = fs.readFileSync(file);
  totalRaw += buf.length;

  // Brotli — max quality (11) for static builds
  const brPath = file + '.br';
  const brNeedsUpdate =
    !fs.existsSync(brPath) || fs.statSync(brPath).mtimeMs < stat.mtimeMs;
  if (brNeedsUpdate) {
    const br = zlib.brotliCompressSync(buf, {
      params: {
        [zlib.constants.BROTLI_PARAM_QUALITY]: 11,
        [zlib.constants.BROTLI_PARAM_SIZE_HINT]: buf.length,
      },
    });
    fs.writeFileSync(brPath, br);
    totalBr += br.length;
  } else {
    totalBr += fs.statSync(brPath).size;
  }

  // Gzip — level 9
  const gzPath = file + '.gz';
  const gzNeedsUpdate =
    !fs.existsSync(gzPath) || fs.statSync(gzPath).mtimeMs < stat.mtimeMs;
  if (gzNeedsUpdate) {
    const gz = zlib.gzipSync(buf, { level: 9 });
    fs.writeFileSync(gzPath, gz);
    totalGz += gz.length;
  } else {
    totalGz += fs.statSync(gzPath).size;
  }

  compressed++;
}

console.log('[precompress] walking dist/');
const freeMb = getFreeDiskMb(DIST);
if (freeMb !== null && freeMb < MIN_FREE_MB) {
  console.warn(
    `[precompress] skipped due to low disk space: ${freeMb.toFixed(1)}MB free (< ${MIN_FREE_MB}MB)`,
  );
  process.exit(0);
}
const t0 = Date.now();
for (const file of walk(DIST)) {
  try {
    compressFile(file);
  } catch (e) {
    console.error('[precompress] FAIL', file, e.message);
  }
}
const t1 = Date.now();

const fmt = (n) => (n / 1024 / 1024).toFixed(2) + ' MiB';
const pct = (n, d) => (d > 0 ? ((1 - n / d) * 100).toFixed(1) + '%' : '0%');

console.log(
  `[precompress] done in ${t1 - t0}ms: ${compressed} compressed, ${skipped} skipped`,
);
console.log(
  `[precompress] raw=${fmt(totalRaw)}  br=${fmt(totalBr)} (${pct(
    totalBr,
    totalRaw,
  )} saved)  gz=${fmt(totalGz)} (${pct(totalGz, totalRaw)} saved)`,
);
