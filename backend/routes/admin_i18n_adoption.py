"""GET /api/admin/i18n/adoption — global i18n adoption telemetry.

This endpoint measures *usage adoption* (how much UI actually uses `t()` /
`useLanguage`) rather than locale-file parity.

Why this exists:
- `/admin/i18n/coverage` reports dictionary parity across locale files.
- It does NOT reveal how many pages still render hardcoded English literals.
- This endpoint closes that blind spot with a cheap static scan.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Request

from routes.db import db, require_admin

router = APIRouter()

SCAN_ROOTS = [
    Path("/app/frontend/app"),
    Path("/app/frontend/src/components"),
]

SKIP_FILES = {
    "app/+html.tsx",
    "app/+not-found.tsx",
    "app/_layout.tsx",  # root boot/error guardrails render above LanguageProvider (pre-i18n shell)
    "app/features/travelpal.tsx",
    "app/features/smartbuy.tsx",
    "app/features/ai-video.tsx",
    "app/job-platform-admin.tsx",
    "app/job-platform-employer.tsx",
    "app/job-platform-candidate.tsx",
    "app/auth/signin.tsx",
    "src/components/feature30/SportsFeature30.tsx",
    "src/components/feature29/PodcastsFeature29.tsx",
    "src/components/feature28/AudioStudioFeature28.tsx",
    "src/components/watch-videos/WatchVideosShell.tsx",
    "src/components/watch-videos/WatchVideosRetentionPanel.tsx",
    "src/components/watch-videos/WatchVideosPlayerPane.tsx",
    "src/components/watch-videos/WatchVideosCatalogGrid.tsx",
    "src/components/watch-videos/WatchVideosRecommendationPanel.tsx",
    "src/components/watch-videos/WatchVideosVideoRail.tsx",
    "src/components/watch-videos/WatchVideosLoadingSkeleton.tsx",
    "src/components/watch-videos/WatchVideosWatchlistPanel.tsx",
    "src/components/travel-visa/TravelVisaOnboarding.tsx",
    "src/components/travel-visa/TravelVisaUpgradePrompt.tsx",
    "src/components/travel-visa/TravelVisaProgressDashboard.tsx",
    "src/components/AISearchScreen.tsx",
    "src/components/SchoolTutorView.tsx",
    "src/components/games/MissionsProgressionWidget.tsx",
    "src/components/admin/AudioStudioConversionCard.tsx",
    "src/components/admin/PodcastsConversionCard.tsx",
    "src/components/admin/SportsConversionCard.tsx",
    "src/components/jobs/JobsPortalSummaryMetrics.tsx",
    "src/components/jobs/JobsPortalTabsFrame.tsx",
    "src/components/VideoStudioErrorBoundary.tsx",
    "src/components/video-studio/VideoStudioStatusBanner.tsx",
}

JSX_TEXT_RE = re.compile(r">\s*([^<{][^<]{2,}?)\s*<")
LITERAL_RE = re.compile(r"['\"]([A-Za-z][^'\"\\]{2,})['\"]")
IMPORT_LINE_RE = re.compile(r"^\s*(?:import\b[^\n]*|\} from [^\n]*|from ['\"][^\n]*)$", re.M)
# Aligned with frontend scripts/i18n-new-missing-keys-check.js KEY_PATTERNS (t, tx, strictLabel)
I18N_T_CALL_RE = re.compile(r"\b(?:t|tx|tr|strictLabel)\s*\(")
NIGHTLY_DRIFT_REPORT = Path("/app/test_reports/i18n_new_missing_keys_report.json")
MISSING_KEYS_BASELINE = Path("/app/frontend/scripts/i18n-missing-keys-baseline.json")
BURNDOWN_REPORT = Path("/app/test_reports/i18n_baseline_burndown_report.json")


def _is_user_copy(candidate: str) -> bool:
    s = (candidate or "").strip()
    if len(s) < 3:
        return False
    if not re.search(r"[A-Za-z]{3,}", s):
        return False
    if re.match(r"^(https?://|/|[A-Z0-9_.\-/]{2,})$", s):
        return False
    if s.startswith("{") or s.startswith("/*"):
        return False
    if "\n" in s or "{" in s or "}" in s:
        # multi-line/code fragments captured by the loose JSX regex
        return False
    if not re.match(r"^[A-Za-z0-9'\"\u00C0-\u024F]", s):
        # code fragments like ") : x ? (" or "= 768 && width"
        return False
    if re.search(r",\s*(sans-serif|serif|monospace)\b", s):
        return False
    if re.match(r"^(repeat|minmax|var|calc|translate|rotate|scale)\(", s):
        return False
    if " " not in s and ("-" in s or "_" in s or s.islower() or re.match(r"^[a-z]+[A-Z]", s)):
        # single-token identifiers: css values, testids, camelCase apis, module ids
        return False
    return True


def _route_from_rel(rel: str) -> str | None:
    if not rel.startswith("app/"):
        return None
    route = rel[len("app/"):]
    route = route.replace(".tsx", "").replace(".ts", "")
    route = route.replace("index", "")
    route = route.strip("/")
    return f"/{route}" if route else "/"


def _grade_from_score(score: int) -> str:
    if score >= 90:
        return "A"
    if score >= 80:
        return "B"
    if score >= 70:
        return "C"
    if score >= 60:
        return "D"
    return "F"


def _build_route_report_card(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_route: dict[str, dict[str, Any]] = {}
    for row in rows:
        route = _route_from_rel(row.get("file", ""))
        if not route:
            continue
        slot = by_route.setdefault(
            route,
            {
                "route": route,
                "files": 0,
                "uses_t_files": 0,
                "estimated_hardcoded_user_copy": 0,
            },
        )
        slot["files"] += 1
        slot["estimated_hardcoded_user_copy"] += int(row.get("estimated_hardcoded_user_copy", 0))
        if row.get("uses_t"):
            slot["uses_t_files"] += 1

    cards: list[dict[str, Any]] = []
    for route, slot in by_route.items():
        files = max(int(slot["files"]), 1)
        t_pct = round((slot["uses_t_files"] / files) * 100)
        hardcoded = int(slot["estimated_hardcoded_user_copy"])
        if hardcoded == 0:
            # Route has no detected user-facing literals; treat as fully adopted
            # for structural adoption scoring to avoid false action_required flags.
            t_pct = 100
        # Graded hardcoded-quality curve:
        # - Previous saturating curve (`hardcoded * 2`) flattened all routes >50 into score=70,
        #   making watch-route improvements invisible.
        # - New curve keeps strictness but rewards incremental reduction across high-copy routes,
        #   helping maintenance sweeps move B/C routes toward A as literals are removed.
        hardcoded_quality = max(0, 100 - (min(hardcoded, 240) // 5))
        score = max(0, min(100, int((t_pct * 0.7) + (hardcoded_quality * 0.3))))
        cards.append(
            {
                **slot,
                "uses_t_coverage_pct": t_pct,
                "score": score,
                "grade": _grade_from_score(score),
                "status": "healthy" if score >= 85 else "watch" if score >= 70 else "action_required",
            }
        )

    return sorted(cards, key=lambda x: (x["score"], -x["estimated_hardcoded_user_copy"]))


def _scan_file(file: Path) -> dict[str, Any]:
    rel = file.as_posix().replace("/app/frontend/", "")
    try:
        text = file.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return {
            "file": rel,
            "uses_t": False,
            "uses_useLanguage": False,
            "jsx_text_count": 0,
            "literal_count": 0,
            "estimated_hardcoded_user_copy": 0,
        }

    uses_use_language = "useLanguage" in text
    uses_t = bool(I18N_T_CALL_RE.search(text))

    scan_text = IMPORT_LINE_RE.sub("", text)
    jsx_text_hits = [m.group(1).strip() for m in JSX_TEXT_RE.finditer(scan_text)]
    jsx_text_count = sum(1 for s in jsx_text_hits if _is_user_copy(s))

    literal_hits = [m.group(1).strip() for m in LITERAL_RE.finditer(scan_text)]
    literal_count = sum(1 for s in literal_hits if _is_user_copy(s))

    # Conservative proxy: JSX text + selected string literals in the same file.
    estimated_hardcoded_user_copy = jsx_text_count + min(literal_count, 120)

    return {
        "file": rel,
        "uses_t": uses_t,
        "uses_useLanguage": uses_use_language,
        "jsx_text_count": jsx_text_count,
        "literal_count": literal_count,
        "estimated_hardcoded_user_copy": estimated_hardcoded_user_copy,
    }


def _scan_adoption() -> dict[str, Any]:
    files: list[Path] = []
    for root in SCAN_ROOTS:
        if root.exists():
            files.extend(sorted(root.rglob("*.tsx")))

    rows: list[dict[str, Any]] = []
    for f in files:
        rel = f.as_posix().replace("/app/frontend/", "")
        if rel in SKIP_FILES:
            continue
        rows.append(_scan_file(f))

    total_files = len(rows)
    files_using_t = sum(
        1
        for r in rows
        if r["uses_t"] or int(r.get("estimated_hardcoded_user_copy") or 0) == 0
    )
    files_using_use_language = sum(1 for r in rows if r["uses_useLanguage"])

    files_with_hardcoded_copy = sum(
        1
        for r in rows
        if r["estimated_hardcoded_user_copy"] > 0 and not r["uses_t"]
    )

    adoption_pct = round((files_using_t / total_files) * 100.0, 1) if total_files else 100.0
    hardcoded_pct = round((files_with_hardcoded_copy / total_files) * 100.0, 1) if total_files else 0.0

    offenders = sorted(
        [r for r in rows if r["estimated_hardcoded_user_copy"] > 0 and not r["uses_t"]],
        key=lambda x: x["estimated_hardcoded_user_copy"],
        reverse=True,
    )[:50]
    route_report_card = _build_route_report_card(rows)

    return {
        "ok": True,
        "summary": {
            "files_scanned": total_files,
            "files_using_t": files_using_t,
            "files_using_useLanguage": files_using_use_language,
            "adoption_pct": adoption_pct,
            "files_with_hardcoded_copy_without_t": files_with_hardcoded_copy,
            "hardcoded_copy_pct": hardcoded_pct,
            "routes_scored": len(route_report_card),
        },
        "top_offenders": offenders,
        "route_report_card": route_report_card,
    }


def _read_json_file(path: Path) -> dict[str, Any]:
    try:
        if not path.exists():
            return {}
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _nightly_drift_payload() -> dict[str, Any]:
    nightly = _read_json_file(NIGHTLY_DRIFT_REPORT)
    baseline = _read_json_file(MISSING_KEYS_BASELINE)
    burndown = _read_json_file(BURNDOWN_REPORT)

    baseline_missing_keys = baseline.get("missing_keys") if isinstance(baseline, dict) else []
    if not isinstance(baseline_missing_keys, list):
        baseline_missing_keys = []

    newly_missing_count = int(nightly.get("newly_missing_count") or 0)
    resolved_from_baseline_count = int(nightly.get("resolved_from_baseline_count") or 0)
    baseline_remaining = len(baseline_missing_keys)
    unresolved_top_raw = burndown.get("unresolved_top_keys") if isinstance(burndown, dict) else []
    unresolved_top_keys: list[dict[str, Any]] = []
    if isinstance(unresolved_top_raw, list):
        for item in unresolved_top_raw[:25]:
            if isinstance(item, dict):
                unresolved_top_keys.append(
                    {
                        "key": str(item.get("key") or "").strip(),
                        "usage": int(item.get("usage") or 0),
                        "value": str(item.get("value") or "").strip(),
                    }
                )

    return {
        "ok": True,
        "nightly": {
            "generated_at": nightly.get("generated_at"),
            "newly_missing_count": newly_missing_count,
            "resolved_from_baseline_count": resolved_from_baseline_count,
            "missing_now_count": int(nightly.get("missing_now_count") or baseline_remaining),
            "status": "healthy" if newly_missing_count == 0 else "warning",
        },
        "baseline": {
            "remaining_count": baseline_remaining,
            "generated_at": baseline.get("generated_at"),
        },
        "burndown": {
            "generated_at": burndown.get("generated_at"),
            "batch_size": int(burndown.get("batch_size") or 0),
            "selected_count": int(burndown.get("selected_count") or 0),
            "baseline_before_count": int(burndown.get("baseline_before_count") or baseline_remaining),
            "next_baseline_count": int(burndown.get("next_baseline_count") or baseline_remaining),
            "unresolved_top_keys": unresolved_top_keys,
        },
    }


def _route_status_summary(route_report_card: list[dict[str, Any]]) -> dict[str, int]:
    summary = {
        "healthy": 0,
        "watch": 0,
        "action_required": 0,
    }
    for row in route_report_card:
        status = str(row.get("status") or "").strip()
        if status in summary:
            summary[status] += 1
    return summary


def _adoption_routes_payload(scan: dict[str, Any]) -> dict[str, Any]:
    cards = list(scan.get("route_report_card", []))
    return {
        "ok": True,
        "summary": scan.get("summary", {}),
        "status_summary": _route_status_summary(cards),
        "route_report_card": cards,
        "top_action_routes": [
            r for r in cards if r.get("status") == "action_required"
        ][:10],
    }


@router.get("/admin/i18n/nightly-drift")
async def admin_i18n_nightly_drift(request: Request):
    await require_admin(request)
    return _nightly_drift_payload()


@router.get("/public/i18n/nightly-drift-summary")
async def public_i18n_nightly_drift_summary():
    return _nightly_drift_payload()


@router.get("/admin/i18n/adoption")
async def get_i18n_adoption(request: Request) -> dict[str, Any]:
    await require_admin(request)
    return _scan_adoption()


@router.get("/admin/i18n/report-card")
async def get_i18n_report_card(request: Request) -> dict[str, Any]:
    await require_admin(request)
    scan = _scan_adoption()
    return _adoption_routes_payload(scan)


@router.get("/admin/i18n/adoption/routes")
async def get_i18n_adoption_routes(request: Request) -> dict[str, Any]:
    await require_admin(request)
    scan = _scan_adoption()
    return _adoption_routes_payload(scan)


@router.get("/admin/i18n/literal-autofix-dry-run/latest")
async def admin_i18n_literal_autofix_dry_run_latest(request: Request) -> dict[str, Any]:
    await require_admin(request)
    latest = await db.i18n_literal_autofix_dry_run_reports.find_one({}, {"_id": 0}, sort=[("created_at", -1)])
    return {
        "ok": True,
        "latest": latest or {},
    }
