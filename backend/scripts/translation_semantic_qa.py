#!/usr/bin/env python3
"""Translation semantic QA for ID Checker locale quality.

Checks beyond simple string replacement:
- required ID Checker brand keys present and normalized
- placeholder token parity vs English baseline
- heuristic warning for likely untranslated English values in non-en locales
"""

from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path("/app/frontend/src/i18n/locales")
REPORT_DIR = Path("/app/test_reports")
REPORT_JSON = REPORT_DIR / "translation_semantic_qa.json"
REPORT_MD = REPORT_DIR / "translation_semantic_qa.md"
REPORT_HISTORY_JSON = REPORT_DIR / "translation_semantic_qa_history.json"

RE_KEYVAL = re.compile(r'^\s*"([^"]+)"\s*:\s*"(.*)"\s*,?\s*$')
RE_TOKEN = re.compile(r"\{[a-zA-Z0-9_]+\}")

REQUIRED_BRAND_KEYS = {
    "idVerification.title": "ID Checker",
    "nav.idVerification": "ID Checker",
}

CORE_GLOSSARY_KEYS = [
    "idVerification.title",
    "idVerification.form.personalInfo",
    "idVerification.review.title",
    "idVerification.sections.aiAnalysis",
    "idVerification.status.underReview",
    "idVerification.status.verified",
    "idVerification.status.rejected",
    "idVerification.status.banned",
    "idVerification.notice.title",
    "idVerification.notice.body",
    "idVerification.actions.submitForAi",
    "nav.idVerification",
]


def parse_locale(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        m = RE_KEYVAL.match(line)
        if not m:
            continue
        out[m.group(1)] = m.group(2)
    return out


def placeholder_tokens(text: str) -> set[str]:
    return set(RE_TOKEN.findall(text or ""))


def likely_untranslated_english(value: str) -> bool:
    if not value:
        return False
    if len(value.split()) < 5:
        return False
    ascii_ratio = sum(1 for ch in value if ord(ch) < 128) / max(len(value), 1)
    if ascii_ratio < 0.95:
        return False
    english_markers = {"the", "and", "your", "please", "review", "document", "verification", "checker"}
    words = {w.strip(".,:;!?()[]{}\"'").lower() for w in value.split()}
    return len(words.intersection(english_markers)) >= 3


def normalize_value(value: str) -> str:
    return re.sub(r"\s+", " ", (value or "").strip().lower())


def load_history() -> dict:
    if not REPORT_HISTORY_JSON.exists():
        return {"runs": []}
    try:
        parsed = json.loads(REPORT_HISTORY_JSON.read_text(encoding="utf-8"))
        if isinstance(parsed, dict) and isinstance(parsed.get("runs"), list):
            return parsed
    except Exception:
        pass
    return {"runs": []}


def save_history(history: dict) -> None:
    runs = history.get("runs", [])
    if len(runs) > 40:
        history["runs"] = runs[-40:]
    REPORT_HISTORY_JSON.write_text(json.dumps(history, indent=2), encoding="utf-8")


def main() -> int:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    locale_files = sorted(ROOT.glob("*.ts"))
    if not locale_files:
        print("No locale files found")
        return 1

    en_path = ROOT / "en.ts"
    if not en_path.exists():
        print("Missing en.ts baseline")
        return 1

    en = parse_locale(en_path)
    critical: list[str] = []
    warnings: list[str] = []
    checked = 0
    locale_glossary: dict[str, dict] = {}

    history = load_history()
    previous_runs = history.get("runs", [])
    previous_locale_data = previous_runs[-1].get("locales", {}) if previous_runs else {}

    for path in locale_files:
        locale = path.stem
        values = parse_locale(path)
        checked += 1

        for k, expected in REQUIRED_BRAND_KEYS.items():
            actual = values.get(k)
            if actual is None:
                critical.append(f"[{locale}] missing key: {k}")
            elif actual != expected:
                critical.append(f"[{locale}] {k} expected '{expected}' got '{actual}'")

        missing_core = [k for k in CORE_GLOSSARY_KEYS if k not in values]
        if locale == "en" and missing_core:
            for key in missing_core:
                critical.append(f"[{locale}] missing glossary key: {key}")
        elif missing_core:
            warnings.append(f"[{locale}] glossary coverage incomplete: missing {len(missing_core)} key(s)")

        glossary_values = {k: values.get(k, "") for k in CORE_GLOSSARY_KEYS if k in values}
        prev_glossary = (previous_locale_data.get(locale) or {}).get("glossary") or {}
        overlap = [k for k in glossary_values if k in prev_glossary]
        changed = [
            k
            for k in overlap
            if normalize_value(glossary_values.get(k, "")) != normalize_value(prev_glossary.get(k, ""))
        ]
        drift_score = round((len(changed) / max(len(overlap), 1)) * 100, 2) if overlap else 0.0

        if overlap and drift_score >= 60:
            critical.append(f"[{locale}] glossary drift too high: {drift_score}% ({len(changed)}/{len(overlap)} keys changed)")
        elif overlap and drift_score >= 25:
            warnings.append(f"[{locale}] glossary drift warning: {drift_score}% ({len(changed)}/{len(overlap)} keys changed)")

        unchanged_from_en = 0
        for k, v in glossary_values.items():
            if locale != "en" and normalize_value(v) == normalize_value(en.get(k, "")):
                unchanged_from_en += 1
        if locale != "en" and glossary_values and unchanged_from_en >= max(4, int(len(glossary_values) * 0.75)):
            warnings.append(
                f"[{locale}] glossary appears mostly English fallback ({unchanged_from_en}/{len(glossary_values)} core terms unchanged)"
            )

        coverage_pct = round((len(glossary_values) / len(CORE_GLOSSARY_KEYS)) * 100, 2)
        locale_score = max(0.0, round(100 - drift_score - (len(missing_core) * 4), 2))
        locale_glossary[locale] = {
            "coverage_pct": coverage_pct,
            "drift_score_pct": drift_score,
            "changed_keys": changed[:50],
            "missing_keys": missing_core[:50],
            "score": locale_score,
            "glossary": glossary_values,
        }

        for key, en_val in en.items():
            if not key.startswith("idVerification."):
                continue
            local_val = values.get(key)
            if local_val is None:
                continue
            if placeholder_tokens(en_val) != placeholder_tokens(local_val):
                warnings.append(
                    f"[{locale}] token mismatch for {key}: expected {sorted(placeholder_tokens(en_val))}, got {sorted(placeholder_tokens(local_val))}"
                )
            if locale != "en" and likely_untranslated_english(local_val):
                warnings.append(f"[{locale}] possibly untranslated value for {key}: {local_val[:140]}")

    payload = {
        "status": "failed" if critical else "passed",
        "checked_locale_files": checked,
        "critical_count": len(critical),
        "warning_count": len(warnings),
        "core_glossary_keys": CORE_GLOSSARY_KEYS,
        "glossary_drift": {
            locale: {
                "coverage_pct": data["coverage_pct"],
                "drift_score_pct": data["drift_score_pct"],
                "score": data["score"],
                "changed_keys": data["changed_keys"],
                "missing_keys": data["missing_keys"],
            }
            for locale, data in locale_glossary.items()
        },
        "critical": critical,
        "warnings": warnings[:300],
    }
    REPORT_JSON.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    history.setdefault("runs", []).append(
        {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "status": payload["status"],
            "locales": {
                locale: {
                    "coverage_pct": data["coverage_pct"],
                    "drift_score_pct": data["drift_score_pct"],
                    "score": data["score"],
                    "glossary": data["glossary"],
                }
                for locale, data in locale_glossary.items()
            },
        }
    )
    save_history(history)

    md = [
        "## Translation Semantic QA",
        "",
        f"- Status: **{payload['status'].upper()}**",
        f"- Locale files checked: **{checked}**",
        f"- Critical issues: **{len(critical)}**",
        f"- Warnings: **{len(warnings)}**",
        f"- Glossary drift history file: `{REPORT_HISTORY_JSON}`",
        "",
    ]

    scored_locales = sorted(
        ((locale, data["score"], data["drift_score_pct"], data["coverage_pct"]) for locale, data in locale_glossary.items()),
        key=lambda x: (x[1], -x[2]),
    )
    md.append("### Per-locale glossary score")
    for locale, score, drift, coverage in scored_locales[:20]:
        md.append(f"- [{locale}] score={score} • drift={drift}% • coverage={coverage}%")

    if critical:
        md.append("### Critical Issues")
        for c in critical[:300]:
            md.append(f"- {c}")
    if warnings:
        md.append("")
        md.append("### Warnings")
        for w in warnings[:200]:
            md.append(f"- {w}")
    REPORT_MD.write_text("\n".join(md) + "\n", encoding="utf-8")

    print(f"report_json={REPORT_JSON}")
    print(f"report_md={REPORT_MD}")
    if critical:
        print("Translation semantic QA FAILED")
        return 1
    print("Translation semantic QA PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
