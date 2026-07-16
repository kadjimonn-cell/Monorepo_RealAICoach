const fs = require('fs');
const path = require('path');

const ROOT = '/app';
const TARGET_DIRS = [
  '/app/frontend/src/components/admin',
  '/app/frontend/src/components',
  '/app/frontend/app',
];

const BANNED_TOKENS = [
  '#0F172A', '#111827', '#1E293B', '#0B0F1A', '#08101F', '#020617', '#050A18', '#1A2236', '#151D2E',
];

function listFiles(dir) {
  const entries = fs.readdirSync(dir, { withFileTypes: true });
  const out = [];
  for (const entry of entries) {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) {
      out.push(...listFiles(full));
      continue;
    }
    if (entry.isFile() && full.endsWith('.tsx')) out.push(full);
  }
  return out;
}

function scanFile(filePath) {
  const text = fs.readFileSync(filePath, 'utf-8');
  const hits = [];
  for (const token of BANNED_TOKENS) {
    const regex = new RegExp(token.replace('#', '\\#'), 'gi');
    const match = text.match(regex);
    if (match && match.length) {
      hits.push({ token, count: match.length });
    }
  }
  return hits;
}

function run() {
  const fileHits = [];
  for (const dir of TARGET_DIRS) {
    if (!fs.existsSync(dir)) continue;
    const files = listFiles(dir);
    for (const file of files) {
      const hits = scanFile(file);
      if (hits.length) {
        fileHits.push({
          file: file.replace(ROOT, ''),
          total: hits.reduce((acc, h) => acc + h.count, 0),
          hits,
        });
      }
    }
  }

  fileHits.sort((a, b) => b.total - a.total);
  const tokenTotals = {};
  for (const row of fileHits) {
    for (const hit of row.hits) {
      tokenTotals[hit.token] = (tokenTotals[hit.token] || 0) + hit.count;
    }
  }

  const report = {
    generated_at: new Date().toISOString(),
    scanned_directories: TARGET_DIRS.map((d) => d.replace(ROOT, '')),
    files_with_hits: fileHits.length,
    total_hits: fileHits.reduce((acc, row) => acc + row.total, 0),
    token_totals: tokenTotals,
    top_files: fileHits.slice(0, 30),
  };

  fs.writeFileSync('/app/memory/theme_audit_report.json', JSON.stringify(report, null, 2));

  const lines = [];
  lines.push('# Theme Audit Report');
  lines.push(`Generated: ${report.generated_at}`);
  lines.push(`Files with hits: ${report.files_with_hits}`);
  lines.push(`Total hardcoded dark-token hits: ${report.total_hits}`);
  lines.push('');
  lines.push('## Token Totals');
  for (const [token, count] of Object.entries(tokenTotals).sort((a, b) => b[1] - a[1])) {
    lines.push(`- ${token}: ${count}`);
  }
  lines.push('');
  lines.push('## Top Files');
  for (const row of report.top_files.slice(0, 20)) {
    lines.push(`- ${row.file} (${row.total})`);
  }

  fs.writeFileSync('/app/memory/theme_audit_report.md', lines.join('\n'));
  console.log(`Theme audit complete: ${report.files_with_hits} files, ${report.total_hits} hits`);
}

run();
