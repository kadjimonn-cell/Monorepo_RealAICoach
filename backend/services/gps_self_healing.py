from __future__ import annotations

import re
import uuid
from typing import Any, Dict, List


async def record_self_healing_audit(db: Any, repairs: List[Dict[str, Any]], now_iso, *, source: str = "get_global_platform_state"):
    if not repairs:
        return
    doc = {
        "audit_id": f"gps_heal_{uuid.uuid4().hex[:12]}",
        "source": source,
        "repairs": repairs,
        "repair_count": len(repairs),
        "created_at": now_iso(),
    }
    await db.gps_self_healing_audit.insert_one(doc)


def align_faq_feature_count_claims(state: Dict[str, Any], now_iso) -> List[Dict[str, Any]]:
    feature_count = len([f for f in (state.get("features") or []) if f.get("enabled", True)])
    if feature_count <= 0:
        return []

    repairs: List[Dict[str, Any]] = []
    count_pattern = re.compile(r"\b\d+\s+(?=(?:specialized\s+)?(?:AI\s+)?(?:copilots?|features?|tools?))", re.IGNORECASE)
    for item in state.get("faq") or []:
        question = str(item.get("question") or "")
        answer = str(item.get("answer") or "")
        if not question and not answer:
            continue

        repaired_question = count_pattern.sub(f"{feature_count} ", question)
        repaired_answer = count_pattern.sub(f"{feature_count} ", answer)
        if repaired_question != question or repaired_answer != answer:
            if repaired_question != question:
                item["question"] = repaired_question
            if repaired_answer != answer:
                item["answer"] = repaired_answer
            item["updated_at"] = now_iso()
            repairs.append(
                {
                    "type": "faq_stale_feature_count_repair",
                    "faq_id": item.get("faq_id"),
                    "feature_count": feature_count,
                    "before_question_excerpt": question[:240],
                    "after_question_excerpt": repaired_question[:240],
                    "before_answer_excerpt": answer[:240],
                    "after_answer_excerpt": repaired_answer[:240],
                }
            )
    return repairs