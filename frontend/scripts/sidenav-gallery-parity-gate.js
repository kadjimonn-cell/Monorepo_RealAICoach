#!/usr/bin/env node

const fs = require('fs');
const path = require('path');

const FRONTEND_ROOT = path.resolve(__dirname, '..');
const REPO_ROOT = path.resolve(FRONTEND_ROOT, '..');
const APP_SHELL_PATH = path.join(FRONTEND_ROOT, 'src', 'components', 'AppShell.tsx');
const REGISTRY_PATH = path.join(REPO_ROOT, 'backend', 'routes', 'feature_registry.py');
const QUALITY_DIR = path.join(FRONTEND_ROOT, '.quality');
const REPORT_PATH = path.join(QUALITY_DIR, 'sidenav_gallery_parity_report.json');

function readText(filePath) {
  return fs.readFileSync(filePath, 'utf8');
}

function parseSidebarCandidates(appShellText) {
  const blockMatch = appShellText.match(/const\s+BASE_NAV_ITEMS\s*=\s*\[([\s\S]*?)\];/);
  if (!blockMatch) return [];
  const block = blockMatch[1];
  const objMatches = block.match(/\{[\s\S]*?\}/g) || [];

  const candidateSections = new Set(['_section_platform', '_section_ai_tools', '_section_hiring', '_section_verification']);
  const out = [];
  let currentSection = null;

  for (const raw of objMatches) {
    const key = (raw.match(/key:\s*'([^']+)'/) || [])[1];
    if (!key) continue;
    const label = (raw.match(/label:\s*'([^']+)'/) || [])[1] || key;
    const href = (raw.match(/href:\s*'([^']+)'/) || [])[1] || null;
    const isSection = /section:\s*true/.test(raw);
    if (isSection) {
      currentSection = key;
      continue;
    }
    if (!href) continue;
    if (key === 'ai-gallery') continue;
    if (!candidateSections.has(String(currentSection || ''))) continue;
    out.push({ key, label, href, section: currentSection });
  }

  return out;
}

function parseRegistryDefaults(registryText) {
  const marker = 'CORE_SIDENAV_FEATURE_DEFAULTS = [';
  const start = registryText.indexOf(marker);
  if (start === -1) return [];
  const listStart = registryText.indexOf('[', start);
  if (listStart === -1) return [];

  let depth = 0;
  let listEnd = -1;
  for (let i = listStart; i < registryText.length; i += 1) {
    const ch = registryText[i];
    if (ch === '[') depth += 1;
    if (ch === ']') {
      depth -= 1;
      if (depth === 0) {
        listEnd = i;
        break;
      }
    }
  }
  if (listEnd === -1) return [];

  const block = registryText.slice(start, listEnd + 1);
  const rx = /\{[\s\S]*?"feature_id":\s*"([^"]+)"[\s\S]*?"route":\s*"([^"]+)"[\s\S]*?\}/g;
  const out = [];
  let m;
  while ((m = rx.exec(block)) !== null) {
    out.push({ feature_id: m[1], route: m[2] });
  }
  return out;
}

function ensureQualityDir() {
  if (!fs.existsSync(QUALITY_DIR)) fs.mkdirSync(QUALITY_DIR, { recursive: true });
}

function run() {
  const appShell = readText(APP_SHELL_PATH);
  const registry = readText(REGISTRY_PATH);

  const sidebarCandidates = parseSidebarCandidates(appShell);
  const registryDefaults = parseRegistryDefaults(registry);
  const registryById = new Map(registryDefaults.map((r) => [r.feature_id, r.route]));
  const registryRoutes = new Set(registryDefaults.map((r) => r.route));

  const missingById = [];
  const missingByRoute = [];

  for (const nav of sidebarCandidates) {
    if (!registryById.has(nav.key)) missingById.push(nav);
    if (!registryRoutes.has(nav.href)) missingByRoute.push(nav);
  }

  const report = {
    generated_at: new Date().toISOString(),
    sidebar_candidate_count: sidebarCandidates.length,
    registry_defaults_count: registryDefaults.length,
    missing_by_feature_id_count: missingById.length,
    missing_by_route_count: missingByRoute.length,
    missing_by_feature_id: missingById,
    missing_by_route: missingByRoute,
    pass: missingById.length === 0 && missingByRoute.length === 0,
  };

  ensureQualityDir();
  fs.writeFileSync(REPORT_PATH, JSON.stringify(report, null, 2));

  if (!report.pass) {
    console.error('[sidenav-gallery-parity-gate] FAILED');
    console.error(` - Missing by feature_id: ${missingById.length}`);
    console.error(` - Missing by route: ${missingByRoute.length}`);
    console.error(` - Report: ${REPORT_PATH}`);
    process.exit(1);
  }

  console.log('[sidenav-gallery-parity-gate] PASS');
  console.log(` - Sidebar candidates: ${sidebarCandidates.length}`);
  console.log(` - Registry defaults: ${registryDefaults.length}`);
  console.log(` - Report: ${REPORT_PATH}`);
}

run();
