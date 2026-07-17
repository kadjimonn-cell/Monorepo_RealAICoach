#!/usr/bin/env node
/**
 * Assemble a STATIC-servable production build at build/ from the expo-router
 * server-mode export (dist/).
 *
 * Why: app.json uses web.output="server", so `expo export` writes
 *   dist/client/  -> JS bundles + assets (no route HTML)
 *   dist/server/  -> pre-rendered HTML for every route
 * The production platform serves /app/frontend/build as PLAIN STATIC files via
 * nginx (no Node server), so build/ must contain index.html at its root and a
 * directory-index layout for every route. Without this, nginx serves its
 * default "Welcome to nginx!" page (production incident 2026-07-17).
 *
 * What it does:
 *   1. build/ := dist/client (assets, _expo js, pwa files)
 *   2. overlay all route HTML from dist/server (skipping server-side _expo)
 *   3. for every "X.html" also write "X/index.html" so /X resolves under
 *      standard nginx directory-index rules (keeps .br/.gz variants alongside)
 *   4. write 200.html + 404.html fallbacks from the root index.html
 */
const fs = require("fs");
const path = require("path");

const DIST = "dist";
const CLIENT = path.join(DIST, "client");
const SERVER = path.join(DIST, "server");
const OUT = "build";

if (!fs.existsSync(CLIENT) || !fs.existsSync(SERVER)) {
  console.error(`[assemble-static-build] FATAL: ${CLIENT} or ${SERVER} missing — run the expo export first`);
  process.exit(1);
}

fs.rmSync(OUT, { recursive: true, force: true });
fs.cpSync(CLIENT, OUT, { recursive: true });

let htmlCount = 0;
let mirrorCount = 0;

function overlay(relDir) {
  const abs = path.join(SERVER, relDir);
  for (const entry of fs.readdirSync(abs, { withFileTypes: true })) {
    const rel = path.join(relDir, entry.name);
    if (entry.isDirectory()) {
      if (entry.name === "_expo") continue; // server-side bundles: not needed for static serving
      overlay(rel);
      continue;
    }
    const isHtmlFamily = /\.html(\.(br|gz))?$/.test(entry.name);
    if (!isHtmlFamily) continue;
    const dest = path.join(OUT, rel);
    fs.mkdirSync(path.dirname(dest), { recursive: true });
    fs.copyFileSync(path.join(SERVER, rel), dest);
    if (entry.name.endsWith(".html")) htmlCount += 1;

    // Mirror "X.html" (and compressed variants) to "X/index.html" so that a
    // request to /X serves it under nginx directory-index resolution.
    const m = entry.name.match(/^(.+?)\.html(\.(br|gz))?$/);
    const stem = m ? m[1] : "";
    if (stem && stem !== "index" && !stem.startsWith("+") && !stem.startsWith("_")) {
      const mirror = path.join(OUT, relDir, stem, `index.html${m[2] || ""}`);
      fs.mkdirSync(path.dirname(mirror), { recursive: true });
      fs.copyFileSync(path.join(SERVER, rel), mirror);
      if (!m[2]) mirrorCount += 1;
    }
  }
}
overlay("");

// SPA-style fallbacks from the root page.
const rootIndex = path.join(OUT, "index.html");
if (!fs.existsSync(rootIndex)) {
  console.error("[assemble-static-build] FATAL: no root index.html produced — dist/server/index.html missing");
  process.exit(1);
}
for (const fallback of ["200.html", "404.html"]) {
  const target = path.join(OUT, fallback);
  if (!fs.existsSync(target)) fs.copyFileSync(rootIndex, target);
}

console.log(
  `[assemble-static-build] done: build/ = client assets + ${htmlCount} route HTML pages (+${mirrorCount} directory-index mirrors); root index.html OK`
);
