#!/usr/bin/env python3
"""One-time: extract tx('key','fallback') pairs from Job Search components and merge into en.ts."""
import re
import sys
from pathlib import Path

sys.path.insert(0, "/app/scripts")
FILES = [
    Path("/app/frontend/app/job-search.tsx"),
    *Path("/app/frontend/src/components/jobSearch").glob("*.tsx"),
]
EN = Path("/app/frontend/src/i18n/locales/en.ts")

pairs = {
    "nav.jobSearch": "Job Search",
    "i18n.route.job-search.probe": "Probe",
}
pat = re.compile(r"tx\(\s*'([^']+)'\s*,\s*'((?:[^'\\]|\\.)*)'\s*\)")
for f in FILES:
    for key, fallback in pat.findall(f.read_text()):
        pairs[key] = fallback.replace("\\'", "'")

text = EN.read_text()
body_match = re.search(r"=\s*\{([\s\S]*?)\};", text)
existing = {}
for m in re.finditer(r'"((?:[^"\\]|\\.)*)"\s*:\s*"((?:[^"\\]|\\.)*)"', body_match.group(1)):
    existing[m.group(1)] = m.group(2)

added = 0
for k, v in pairs.items():
    if k not in existing:
        existing[k] = v.replace("\\", "\\\\").replace('"', '\\"')
        added += 1

lines = ["// Auto-generated locale file for en", "const locale: Record<string, string> = {"]
for key in sorted(existing.keys()):
    lines.append(f'  "{key}": "{existing[key]}",')
lines.append("};")
lines.append("")
lines.append("export default locale;")
lines.append("")
EN.write_text("\n".join(lines))
print(f"Added {added} new keys ({len(pairs)} scanned). en.ts total: {len(existing)}")
