#!/usr/bin/env node
// Tiny reverse proxy: 0.0.0.0:3001 -> 127.0.0.1:3000 (single-Metro mode).
//
// The preview pod has an 8 GB cgroup memory cap; running a second full Metro
// instance for native alongside the web Metro caused kernel OOM pod kills.
// The web Metro on port 3000 is an Expo dev server and already serves native
// (Expo Go) manifests and bundles for any platform, so the platform's mobile
// preview route (expo.preview host -> port 3001) is satisfied by proxying to it.
//
// RESILIENCE: after every (re)start this process also acts as a warmer — it
// keeps requesting the web root from Metro with a long timeout until Metro
// answers 200 quickly, so preview iframes recover from pod restarts without
// manual help. The proxy itself never crash-loops: upstream connections are
// made per-request and failures return 502.
const http = require('http');
const net = require('net');

const TARGET_HOST = '127.0.0.1';
const TARGET_PORT = 3000;
const LISTEN_PORT = 3001;

const server = http.createServer((req, res) => {
  const upstream = http.request(
    { host: TARGET_HOST, port: TARGET_PORT, path: req.url, method: req.method, headers: req.headers },
    (ur) => {
      res.writeHead(ur.statusCode || 502, ur.headers);
      ur.pipe(res);
    }
  );
  upstream.on('error', () => {
    if (!res.headersSent) res.writeHead(502, { 'content-type': 'text/plain' });
    res.end('metro upstream unavailable');
  });
  req.pipe(upstream);
});

// WebSocket upgrade passthrough (Metro HMR / Expo Go message socket)
server.on('upgrade', (req, socket, head) => {
  const upstream = net.connect(TARGET_PORT, TARGET_HOST, () => {
    const lines = [`${req.method} ${req.url} HTTP/1.1`];
    for (let i = 0; i < req.rawHeaders.length; i += 2) {
      lines.push(`${req.rawHeaders[i]}: ${req.rawHeaders[i + 1]}`);
    }
    upstream.write(lines.join('\r\n') + '\r\n\r\n');
    if (head && head.length) upstream.write(head);
    socket.pipe(upstream);
    upstream.pipe(socket);
  });
  upstream.on('error', () => socket.destroy());
  socket.on('error', () => upstream.destroy());
});

server.listen(LISTEN_PORT, '0.0.0.0', () => {
  console.log(`[mobile-proxy] 0.0.0.0:${LISTEN_PORT} -> ${TARGET_HOST}:${TARGET_PORT} (single-Metro mode)`);
});

// ── Post-restart Metro warmer ────────────────────────────────────────────────
// Requests "/" from Metro with a very long timeout until it responds 200 fast
// twice in a row (= SSR route cache warm), then warms the native manifest once.
const WARM_FAST_MS = 20000;
const WARM_MAX_ATTEMPTS = 60;
let warmConsecutiveFast = 0;

function warmManifest() {
  const req = http.get(
    { host: TARGET_HOST, port: TARGET_PORT, path: '/', headers: { 'expo-platform': 'android' } },
    (res) => {
      res.resume();
      res.on('end', () => console.log(`[mobile-proxy] native manifest warm: ${res.statusCode}`));
    }
  );
  req.setTimeout(120000, () => req.destroy());
  req.on('error', () => {});
}

function warmWeb(attempt) {
  if (attempt >= WARM_MAX_ATTEMPTS) {
    console.log('[mobile-proxy] warmer gave up (max attempts)');
    return;
  }
  const started = Date.now();
  const req = http.get(
    { host: TARGET_HOST, port: TARGET_PORT, path: '/', headers: { 'user-agent': 'preview-warmer' } },
    (res) => {
      res.resume();
      res.on('end', () => {
        const elapsed = Date.now() - started;
        const fastOk = res.statusCode === 200 && elapsed < WARM_FAST_MS;
        warmConsecutiveFast = fastOk ? warmConsecutiveFast + 1 : 0;
        console.log(`[mobile-proxy] warm ${attempt}: ${res.statusCode} in ${Math.round(elapsed / 1000)}s`);
        if (warmConsecutiveFast >= 2) {
          console.log('[mobile-proxy] web warmup complete');
          warmManifest();
          return;
        }
        setTimeout(() => warmWeb(attempt + 1), 8000);
      });
    }
  );
  req.setTimeout(280000, () => req.destroy());
  req.on('error', () => {
    warmConsecutiveFast = 0;
    setTimeout(() => warmWeb(attempt + 1), 15000);
  });
}

setTimeout(() => warmWeb(0), 20000);
