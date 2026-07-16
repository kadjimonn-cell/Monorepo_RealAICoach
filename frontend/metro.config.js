// metro.config.js
const { getDefaultConfig } = require("expo/metro-config");
const path = require('path');
const fs = require('fs');
const crypto = require('crypto');
const { FileStore } = require('metro-cache');
const compression = require('compression');
const packageJson = require('./package.json');

const config = getDefaultConfig(__dirname);

// ─── Icon Glyph Map Optimization ───────────────────────────────────────
// Only Ionicons and FontAwesome5Free are used. Replace all other glyph maps
// with empty stubs to save ~280KB from the bundle.
const KEEP_GLYPHMAPS = new Set([
  'Ionicons.json',
  'FontAwesome5Free.json',
  'FontAwesome5Free_meta.json',
]);
const EMPTY_GLYPHMAP = path.resolve(__dirname, 'src/icon-stubs/empty-glyphmap.json');
const EMPTY_META = path.resolve(__dirname, 'src/icon-stubs/empty-meta.json');

const origResolver = config.resolver?.resolveRequest;
config.resolver = {
  ...config.resolver,
  resolveRequest: (context, moduleName, platform) => {
    // Intercept glyph map JSON imports for unused icon families
    if (moduleName.includes('glyphmaps/') && moduleName.endsWith('.json')) {
      const filename = path.basename(moduleName);
      if (!KEEP_GLYPHMAPS.has(filename)) {
        const stub = filename.includes('_meta') ? EMPTY_META : EMPTY_GLYPHMAP;
        const resolver = origResolver || context.resolveRequest;
        return resolver(context, stub, platform);
      }
    }
    // Fall through to default resolver
    if (origResolver) {
      return origResolver(context, moduleName, platform);
    }
    return context.resolveRequest(context, moduleName, platform);
  },
};

// Use a stable on-disk store (shared across web/android)
const root = process.env.METRO_CACHE_ROOT || path.join(__dirname, '.metro-cache');
config.cacheStores = [
  new FileStore({ root: path.join(root, 'cache') }),
];
const packageJsonRaw = fs.readFileSync(path.join(__dirname, 'package.json'), 'utf8');
const metroConfigRaw = fs.readFileSync(path.join(__dirname, 'metro.config.js'), 'utf8');
const cacheVersionHash = crypto
  .createHash('sha256')
  .update(`${packageJson.version}:${packageJsonRaw}:${metroConfigRaw}`)
  .digest('hex')
  .slice(0, 16);
config.cacheVersion = `${packageJson.version}-${cacheVersionHash}`;

// Reduce workers to minimize OOM risk in constrained preview containers
config.maxWorkers = Number(process.env.METRO_MAX_WORKERS || 1);

// MIME type map for common assets
const MIME_TYPES = {
  '.ttf': 'font/ttf',
  '.otf': 'font/otf',
  '.woff': 'font/woff',
  '.woff2': 'font/woff2',
  '.png': 'image/png',
  '.jpg': 'image/jpeg',
  '.jpeg': 'image/jpeg',
  '.gif': 'image/gif',
  '.svg': 'image/svg+xml',
  '.webp': 'image/webp',
};

// Gzip compression middleware
const compress = compression({ level: 6, threshold: 1024 });

config.server = {
  ...config.server,
  enhanceMiddleware: (middleware) => {
    return (req, res, next) => {
      // Apply gzip compression to all responses
      compress(req, res, () => {
        // Cache static assets aggressively
        const url = req.url || '';
        if (url.match(/\.(js|css|png|jpg|jpeg|gif|svg|woff|woff2|ttf|otf)(\?|$)/)) {
          res.setHeader('Cache-Control', 'public, max-age=86400, stale-while-revalidate=604800');
        }

        // Serve static assets from filesystem when Metro's asset pipeline can't
        if (url.startsWith('/assets/?unstable_path=')) {
          try {
            const urlObj = new URL(url, 'http://localhost');
            const assetPath = decodeURIComponent(urlObj.searchParams.get('unstable_path') || '');
            if (assetPath) {
              const fullPath = path.resolve(__dirname, assetPath);
              if (fs.existsSync(fullPath) && fullPath.startsWith(__dirname)) {
                const ext = path.extname(fullPath).toLowerCase();
                const mime = MIME_TYPES[ext] || 'application/octet-stream';
                const data = fs.readFileSync(fullPath);
                res.statusCode = 200;
                res.setHeader('Content-Type', mime);
                res.setHeader('Cache-Control', 'public, max-age=86400');
                res.end(data);
                return;
              }
            }
          } catch (e) {
            // Fall through to default middleware
          }
        }
        return middleware(req, res, next);
      });
    };
  },
};

module.exports = config;
