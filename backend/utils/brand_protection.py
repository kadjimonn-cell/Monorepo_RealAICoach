"""Centralized brand protection for translation-safe content."""

from __future__ import annotations

import os
import re
import uuid
from collections import Counter
from datetime import datetime, timezone
from typing import Any

from dotenv import load_dotenv


load_dotenv(os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env"))


PROTECTED_BRANDS_MULTI = [
    "RealAICoach LLC",
    "Google Play",
    "App Store",
    "Apple Pay",
]

PROTECTED_BRANDS_SINGLE = [
    "Google",
    "Microsoft",
    "Apple",
    "LLC",
    "RealAICoach",
    "PayPal",
    "Stripe",
    "FedaPay",
    "OpenAI",
    "Anthropic",
    "Gemini",
    "Claude",
]

PROTECTED_BRANDS = PROTECTED_BRANDS_MULTI + PROTECTED_BRANDS_SINGLE

_MULTI_ESCAPED = [re.escape(item) for item in PROTECTED_BRANDS_MULTI]
_SINGLE_ESCAPED = [r"\b" + re.escape(item) + r"\b" for item in PROTECTED_BRANDS_SINGLE]
BRAND_PATTERN = re.compile("|".join(_MULTI_ESCAPED + _SINGLE_ESCAPED))


def extract_protected_brands(text: str) -> list[str]:
    if not text:
        return []
    return [match.group(0) for match in BRAND_PATTERN.finditer(text)]


def protect_brands(text: str) -> tuple[str, dict[str, str]]:
    restore_map: dict[str, str] = {}
    idx = 0

    def _replace(match: re.Match) -> str:
        nonlocal idx
        token = f"{{{{BRAND_{idx}}}}}"
        restore_map[token] = match.group(0)
        idx += 1
        return token

    return BRAND_PATTERN.sub(_replace, text), restore_map


def restore_brands(text: str, restore_map: dict[str, str]) -> str:
    result = text
    for token, brand in restore_map.items():
        result = result.replace(token, brand)
    return result


def preserves_protected_brands(source_text: str, candidate_text: str) -> bool:
    source_brands = extract_protected_brands(source_text)
    if not source_brands:
        return True
    source_counts = Counter(source_brands)
    candidate_counts = Counter(extract_protected_brands(str(candidate_text or "")))
    return all(candidate_counts.get(brand, 0) >= required for brand, required in source_counts.items())


def scan_brand_violations(source_text: str, candidate_text: str) -> list[dict[str, Any]]:
    violations = []
    source_counts = Counter(extract_protected_brands(source_text))
    candidate_counts = Counter(extract_protected_brands(str(candidate_text or "")))
    for brand, required in source_counts.items():
        found = candidate_counts.get(brand, 0)
        if found < required:
            violations.append({
                "brand": brand,
                "reason": "missing_exact_brand_token",
                "required_occurrences": required,
                "found_occurrences": found,
            })
    return violations


def enforce_protected_brands(source_text: str, candidate_text: str) -> str:
    if not extract_protected_brands(source_text):
        return candidate_text
    return candidate_text if preserves_protected_brands(source_text, candidate_text) else source_text


async def ai_validate_brand_integrity(source_text: str, candidate_text: str, target_lang: str) -> dict[str, Any]:
    violations = scan_brand_violations(source_text, candidate_text)
    if not violations:
        return {
            "status": "clean",
            "corrected_text": candidate_text,
            "violations": [],
        }

    api_key = os.environ.get("EMERGENT_LLM_KEY", "")
    if not api_key:
        return {
            "status": "no_ai_key",
            "corrected_text": enforce_protected_brands(source_text, candidate_text),
            "violations": violations,
        }

    try:
        from emergentintegrations.llm.chat import LlmChat, UserMessage

        chat = LlmChat(
            api_key=api_key,
            session_id=f"brand-protect-{uuid.uuid4().hex[:10]}",
            system_message=(
                "You validate translated text for protected brand integrity. "
                f"Never translate or mutate these brand names: {', '.join(PROTECTED_BRANDS)}. "
                "Return JSON only with keys corrected_text and violations."
            ),
        ).with_model("openai", "gpt-4o")

        response = await chat.send_message(UserMessage(text=str({
            "target_lang": target_lang,
            "source_text": source_text,
            "candidate_text": candidate_text,
            "protected_brands": PROTECTED_BRANDS,
        })))
        import json
        parsed = json.loads(response) if str(response).strip().startswith("{") else {}
        corrected = str(parsed.get("corrected_text") or candidate_text)
        corrected = enforce_protected_brands(source_text, corrected)
        return {
            "status": "ai_validated",
            "corrected_text": corrected,
            "violations": parsed.get("violations") or violations,
        }
    except Exception:
        return {
            "status": "ai_fallback",
            "corrected_text": enforce_protected_brands(source_text, candidate_text),
            "violations": violations,
        }


def build_brand_audit_record(source_text: str, candidate_text: str, target_lang: str, status: str, violations: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "audit_id": f"bpa_{uuid.uuid4().hex[:12]}",
        "source_text": source_text,
        "candidate_text": candidate_text,
        "target_lang": target_lang,
        "status": status,
        "violations": violations,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }