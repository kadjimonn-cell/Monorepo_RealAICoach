from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from datetime import datetime, timezone

# Ensure /app/backend is importable when script runs from /app/backend/scripts
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from routes.db import db
from utils.email_template_policy import PROTECTED_SUBJECT_OVERRIDE_PREFIXES, PROTECTED_SUBJECT_OVERRIDE_KEYS


def _build_protected_query() -> dict:
    prefix_or = [{"email_type": {"$regex": f"^{prefix}"}} for prefix in PROTECTED_SUBJECT_OVERRIDE_PREFIXES]
    template_prefix_or = [{"template_type": {"$regex": f"^{prefix}"}} for prefix in PROTECTED_SUBJECT_OVERRIDE_PREFIXES]
    exact = list(PROTECTED_SUBJECT_OVERRIDE_KEYS)
    return {
        "active": True,
        "$or": [
            {"email_type": {"$in": exact}},
            {"template_type": {"$in": exact}},
            *prefix_or,
            *template_prefix_or,
        ],
    }


async def main() -> None:
    query = _build_protected_query()
    before = await db.email_subject_overrides.count_documents(query)
    print(f"active_protected_overrides_before={before}")

    now_iso = datetime.now(timezone.utc).isoformat()
    result = await db.email_subject_overrides.update_many(
        query,
        {
            "$set": {
                "active": False,
                "disabled_reason": "protected_template_subject_override_block",
                "disabled_at": now_iso,
            }
        },
    )
    print(f"modified={result.modified_count}")

    after = await db.email_subject_overrides.count_documents(query)
    print(f"active_protected_overrides_after={after}")


if __name__ == "__main__":
    asyncio.run(main())
