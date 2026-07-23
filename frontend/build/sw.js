// Service Worker for RealAICoach — offline-first caching strategy
// Version is bumped automatically by the build hash in the filenames
//
// ⚠️ IMPORTANT: Every code change that modifies cache keys, strategies, or
// message-handling MUST bump all three version numbers below. Bumping
// forces the activate-handler to evict stale chunks left behind by
// previous builds — this is the only reliable guard against "Something
// Went Wrong" errors caused by old clients holding dangling chunk URLs
// after `expo export` regenerates bundle hashes.

const CACHE_NAME = 'realaicoach-v-eae9133a';
const STATIC_CACHE = 'realaicoach-static-eae9133a';
const API_CACHE = 'realaicoach-api-eae9133a';

// Static assets to precache on install (critical path)
const PRECACHE_URLS = [
  '/',
  '/auth/login',
  '/offline.html',
];

// Cache strategies
const STRATEGIES = {
  // Hashed JS/CSS bundles — cache forever (content-addressable)
  immutable: /\/_expo\/static\/(js|css)\/web\/[^/]+\.[a-f0-9]+\./,
  // Font files — cache for a long time
  fonts: /\.(ttf|woff|woff2|otf)(\?|$)/,
  // Image assets — cache with revalidation
  images: /\.(png|jpg|jpeg|gif|svg|webp)(\?|$)/,
  // API responses — network first, cache fallback
  api: /\/api\//,
};

// Install: precache critical assets
self.addEventListener('install', (event) => {
  event.waitUntil(
    (async () => {
      const cache = await caches.open(CACHE_NAME);

      // Add critical routes one-by-one so a single failure does not
      // abort the full precache set.
      for (const url of PRECACHE_URLS) {
        try {
          await cache.add(url);
        } catch {
          // best-effort in volatile preview networks
        }
      }

      // Ensure offline page is always present in cache so fallback never
      // degrades to a plain-text `Offline` response.
      try {
        const offlineResp = await fetch('/offline.html', { cache: 'reload' });
        if (offlineResp && offlineResp.ok) {
          await cache.put('/offline.html', offlineResp.clone());
        }
      } catch {
        // Keep install resilient; runtime fallback will handle misses.
      }
    })()
  );
  // Activate immediately
  self.skipWaiting();
});

// Allow controlled activation from the page when an update is installed
self.addEventListener('message', (event) => {
  if (event?.data?.type === 'SKIP_WAITING') {
    self.skipWaiting();
  }
});

// Activate: clean old caches
self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) => {
      return Promise.all(
        keys
          .filter((key) => key !== CACHE_NAME && key !== STATIC_CACHE && key !== API_CACHE)
          .map((key) => caches.delete(key))
      );
    })
  );
  // Take control of all clients immediately
  self.clients.claim();
});

// Fetch: apply caching strategies
self.addEventListener('fetch', (event) => {
  const { request } = event;
  const url = new URL(request.url);

  // Skip non-GET requests
  if (request.method !== 'GET') return;

  // Skip WebSocket and auth-related requests
  if (url.pathname.startsWith('/api/ws/') || url.pathname.includes('/auth/')) return;

  // Strategy 1: Immutable static assets (JS/CSS with content hash) — Cache First
  if (STRATEGIES.immutable.test(url.pathname)) {
    event.respondWith(cacheFirst(request, STATIC_CACHE));
    return;
  }

  // Strategy 2: Fonts — Cache First with long TTL
  if (STRATEGIES.fonts.test(url.pathname)) {
    event.respondWith(cacheFirst(request, STATIC_CACHE));
    return;
  }

  // Strategy 3: Images — Stale While Revalidate
  if (STRATEGIES.images.test(url.pathname)) {
    event.respondWith(staleWhileRevalidate(request, STATIC_CACHE));
    return;
  }

  // Strategy 4: API requests — Network First with cache fallback
  if (STRATEGIES.api.test(url.pathname)) {
    // Only cache safe, non-sensitive API routes
    if (isCacheableAPI(url.pathname)) {
      event.respondWith(networkFirst(request, API_CACHE, 3000));
    }
    return;
  }

  // Strategy 5: Navigation requests — Network-only with offline fallback
  if (request.mode === 'navigate') {
    event.respondWith(networkOnlyWithOffline(request, 12000));
    return;
  }
});

// Cache-First: return cached if available, otherwise fetch and cache
async function cacheFirst(request, cacheName) {
  const cached = await caches.match(request);
  if (cached) return cached;

  try {
    const response = await fetch(request);
    if (response.ok) {
      const cache = await caches.open(cacheName);
      cache.put(request, response.clone());
    }
    return response;
  } catch {
    return new Response('Offline', { status: 503 });
  }
}

// Stale-While-Revalidate: return cached immediately, update in background
async function staleWhileRevalidate(request, cacheName) {
  const cache = await caches.open(cacheName);
  const cached = await cache.match(request);

  const fetchPromise = fetch(request)
    .then((response) => {
      if (response.ok) {
        cache.put(request, response.clone());
      }
      return response;
    })
    .catch(() => cached);

  return cached || fetchPromise;
}

// Network-First: try network, fall back to cache with timeout
async function networkFirst(request, cacheName, timeout) {
  const cache = await caches.open(cacheName);

  try {
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), timeout);

    const response = await fetch(request, { signal: controller.signal });
    clearTimeout(timeoutId);

    if (response.ok) {
      cache.put(request, response.clone());
    }
    return response;
  } catch {
    const cached = await cache.match(request);
    if (cached) return cached;

    // For navigation requests, serve the offline fallback page
    if (request.mode === 'navigate') {
      const offlinePage = await caches.match('/offline.html');
      if (offlinePage) return offlinePage;
    }

    return new Response('Offline', { status: 503 });
  }
}

// Navigation Network-only: never cache app shell HTML to avoid stale chunk mismatches
async function networkOnlyWithOffline(request, timeout) {
  try {
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), timeout);
    const response = await fetch(request, { signal: controller.signal, cache: 'no-store' });
    clearTimeout(timeoutId);
    return response;
  } catch {
    const offlinePage = await caches.match('/offline.html');
    if (offlinePage) return offlinePage;

    // Try a direct network fetch for offline page if cache missed.
    try {
      const networkOffline = await fetch('/offline.html', { cache: 'reload' });
      if (networkOffline && networkOffline.ok) {
        const cache = await caches.open(CACHE_NAME);
        cache.put('/offline.html', networkOffline.clone());
        return networkOffline;
      }
    } catch {
      // fall through to emergency inline HTML
    }

    // Emergency HTML fallback avoids showing a raw plain-text `Offline` page.
    return new Response(
      '<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Offline</title></head><body style="font-family:-apple-system,BlinkMacSystemFont,Segoe UI,sans-serif;padding:24px;background:#0f172a;color:#e2e8f0"><h1 style="margin:0 0 8px">You\'re Offline</h1><p style="margin:0 0 12px">Connection looks unstable. Please retry in a moment.</p><button onclick="location.reload()" style="padding:10px 14px;border:0;border-radius:8px;background:#2563eb;color:#fff">Try Again</button></body></html>',
      {
        status: 503,
        headers: { 'Content-Type': 'text/html; charset=utf-8' },
      }
    );
  }
}

// Only cache non-sensitive, read-only API routes
function isCacheableAPI(pathname) {
  const cacheable = [
    '/api/config/global',
    '/api/features/registry',
    '/api/system/vanity-metrics',
    '/api/payments/currencies',
  ];
  return cacheable.some((p) => pathname.startsWith(p));
}

// ── Web Push Notification Handlers ──

self.addEventListener('push', (event) => {
  let data = {};
  if (event.data) {
    try {
      data = event.data.json();
    } catch {
      data = { title: 'RealAICoach', body: event.data.text() };
    }
  }

  const options = {
    body: data.body || 'You have a new notification',
    icon: data.icon || '/api/static/images/favicon-64.png',
    badge: '/api/static/images/favicon-64.png',
    tag: data.tag || 'realaicoach-' + Date.now(),
    data: { url: data.url || '/' },
    vibrate: [100, 50, 100],
    requireInteraction: false,
  };

  event.waitUntil(
    self.registration.showNotification(data.title || 'RealAICoach', options)
  );
});

self.addEventListener('notificationclick', (event) => {
  event.notification.close();

  const targetUrl = event.notification.data?.url || '/';

  event.waitUntil(
    clients.matchAll({ type: 'window', includeUncontrolled: true }).then((clientList) => {
      // Focus existing window if available
      for (const client of clientList) {
        if (new URL(client.url).origin === self.location.origin && 'focus' in client) {
          client.navigate(targetUrl);
          return client.focus();
        }
      }
      // Otherwise open a new window
      return clients.openWindow(targetUrl);
    })
  );
});
