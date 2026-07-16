from __future__ import annotations

import json
import math
import pathlib
import re
from dataclasses import dataclass


ROOT = pathlib.Path("/app")
ADMIN_DIR = ROOT / "frontend" / "src" / "components" / "admin"
MEMORY_DIR = ROOT / "memory"
TARGET_BUDGET = 0
PLANNED_BATCHES = 6

TEXT_LITERAL_RE = re.compile(r"<Text[^>]*>\s*([^<{][^<{]*[A-Za-z][^<{]*)\s*</Text>")
PLACEHOLDER_LITERAL_RE = re.compile(r"placeholder\s*=\s*['\"]([^'\"]*[A-Za-z][^'\"]*)['\"]")
ALERT_CONFIRM_LITERAL_RE = re.compile(r"(?:window\.)?(?:alert|confirm)\(\s*['\"]([^'\"]*[A-Za-z][^'\"]*)['\"]")

ALLOWED_LITERALS = {"N/A", "UTC", "JSON", "CSV", "HTTP", "AI", "AUTO"}


@dataclass
class Offender:
    path: str
    count: int


def _normalize(value: str) -> str:
    return " ".join(value.strip().split())


def _scan_file(path: pathlib.Path) -> int:
    src = path.read_text(encoding="utf-8", errors="ignore")
    if "@i18n-guard-ignore" in src:
        return 0

    hits = 0
    for matcher in (TEXT_LITERAL_RE, PLACEHOLDER_LITERAL_RE, ALERT_CONFIRM_LITERAL_RE):
        for match in matcher.finditer(src):
            text = _normalize(match.group(1))
            if not text or text in ALLOWED_LITERALS:
                continue
            hits += 1
    return hits


def _collect_offenders() -> list[Offender]:
    offenders: list[Offender] = []
    for path in sorted(ADMIN_DIR.rglob("*.tsx")):
        count = _scan_file(path)
        if count > 0:
            offenders.append(Offender(path=str(path.relative_to(ROOT)), count=count))
    offenders.sort(key=lambda o: o.count, reverse=True)
    return offenders


def _build_batches(selected: list[Offender], batch_count: int, target_total: int) -> list[list[Offender]]:
    if not selected:
        return [[] for _ in range(batch_count)]

    per_batch_goal = max(1, math.ceil(target_total / batch_count))
    batches: list[list[Offender]] = []
    current: list[Offender] = []
    running = 0

    for offender in selected:
        current.append(offender)
        running += offender.count
        if running >= per_batch_goal and len(batches) < batch_count - 1:
            batches.append(current)
            current = []
            running = 0

    batches.append(current)
    while len(batches) < batch_count:
        batches.append([])
    return batches


def main() -> None:
    MEMORY_DIR.mkdir(parents=True, exist_ok=True)

    offenders = _collect_offenders()
    current_total = sum(o.count for o in offenders)
    needed_reduction = max(0, current_total - TARGET_BUDGET)

    selected: list[Offender] = []
    running = 0
    for offender in offenders:
        if running >= needed_reduction:
            break
        selected.append(offender)
        running += offender.count

    batches = _build_batches(selected, PLANNED_BATCHES, needed_reduction)

    payload = {
        "mode": "phase_5_zero",
        "current_total": current_total,
        "target_budget": TARGET_BUDGET,
        "needed_reduction": needed_reduction,
        "selected_reduction_capacity": running,
        "selected_file_count": len(selected),
        "top_offenders": [o.__dict__ for o in offenders[:100]],
        "selected_offenders": [o.__dict__ for o in selected],
        "batches": [
            {
                "batch": index + 1,
                "target_reduction": math.ceil(needed_reduction / PLANNED_BATCHES) if needed_reduction else 0,
                "planned_reduction": sum(item.count for item in batch),
                "items": [item.__dict__ for item in batch],
            }
            for index, batch in enumerate(batches)
        ],
    }

    json_path = MEMORY_DIR / "phase5_zero_plan.json"
    json_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    md_lines = [
        "# Phase 5 (Strict Zero) i18n Reduction Plan",
        "",
        f"- Current total literals: **{current_total}**",
        f"- Target budget: **{TARGET_BUDGET}**",
        f"- Reduction required: **{needed_reduction}**",
        f"- Planned reduction capacity in this plan: **{running}**",
        f"- Planned batches: **{PLANNED_BATCHES}**",
        "",
        "## Recommended Batch Plan",
        "",
    ]

    for idx, batch in enumerate(payload["batches"], start=1):
        md_lines.append(f"### Batch {idx}")
        md_lines.append(f"- Planned reduction: **{batch['planned_reduction']}**")
        if not batch["items"]:
            md_lines.append("- No files assigned")
            md_lines.append("")
            continue
        md_lines.append("")
        md_lines.append("| File | Literals |")
        md_lines.append("|---|---:|")
        for item in batch["items"]:
            md_lines.append(f"| `{item['path']}` | {item['count']} |")
        md_lines.append("")

    md_lines.append("## Top Remaining Offenders")
    md_lines.append("")
    md_lines.append("| File | Literals |")
    md_lines.append("|---|---:|")
    for item in payload["top_offenders"][:30]:
        md_lines.append(f"| `{item['path']}` | {item['count']} |")

    md_path = MEMORY_DIR / "phase5_zero_plan.md"
    md_path.write_text("\n".join(md_lines) + "\n", encoding="utf-8")

    print(f"wrote {json_path}")
    print(f"wrote {md_path}")


if __name__ == "__main__":
    main()
