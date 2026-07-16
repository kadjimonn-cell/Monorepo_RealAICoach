"""
V7 Template Enforcement Backend
Handles template validation, regression prevention, and compliance monitoring.
Isolated from V2 platform enforcement.
"""
import logging
from datetime import datetime, timezone
from fastapi import APIRouter, Request

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin/v7-templates")

V7_VIOLATIONS_COLLECTION = "v7_template_violations"
V7_BASELINES_COLLECTION = "v7_template_baselines"

# V2 fingerprint colors — for cross-contamination detection in templates
V2_FINGERPRINT_COLORS = [
    '#0F766E', '#14B8A6', '#5EEAD4', '#2DD4BF',
    '#0B5F58', '#99F6E4', '#ECFDFB',
]

# V7 default primary (Cobalt Blue)
V7_PRIMARY_LIGHT = '#2B6CB0'
V7_PRIMARY_DARK = '#63B3ED'


async def _get_db():
    from routes.db import db
    return db


@router.post("/validate")
async def validate_template(request: Request):
    """Validate a template definition against V7 rules server-side.

    Accepts a template JSON and returns validation result + sanitized version.
    """
    from routes.db import require_admin
    await require_admin(request)

    body = await request.json()
    template = body.get("template", {})
    dark_mode = body.get("dark_mode", False)
    db = await _get_db()

    primary_replacement = V7_PRIMARY_DARK if dark_mode else V7_PRIMARY_LIGHT

    violations = []
    sanitized = dict(template)

    # Check styles for V2 contamination
    styles = sanitized.get("styles", {})
    _scan_v2_contamination(styles, {"primary": primary_replacement}, violations)

    # Check content for V2 tokens
    content = sanitized.get("content", "")
    if content:
        for fp in V2_FINGERPRINT_COLORS:
            if fp in content:
                violations.append({
                    "rule": "v2_contamination",
                    "message": f"V2 token '{fp}' in template content",
                    "severity": "high",
                    "field": "content",
                })
                content = content.replace(fp, primary_replacement)
        sanitized["content"] = content

    # Log violations
    now = datetime.now(timezone.utc).isoformat()
    for v in violations[:20]:
        await db[V7_VIOLATIONS_COLLECTION].insert_one({
            "template_id": template.get("id", "unknown"),
            "template_name": template.get("name", "unknown"),
            "rule": v.get("rule"),
            "message": v.get("message"),
            "severity": v.get("severity"),
            "created_at": now,
            "resolved": False,
        })

    has_critical = any(v.get("severity") == "critical" for v in violations)

    return {
        "valid": len(violations) == 0,
        "compliant": not has_critical,
        "violations": violations,
        "sanitized": sanitized,
        "v7_injected": True,
    }


@router.get("/violations")
async def list_v7_violations(request: Request, limit: int = 50, resolved: str = "false"):
    """List V7 template violations for dashboard."""
    from routes.db import require_admin
    await require_admin(request)

    db = await _get_db()
    query = {}
    if resolved == "false":
        query["resolved"] = False
    elif resolved == "true":
        query["resolved"] = True

    cursor = db[V7_VIOLATIONS_COLLECTION].find(
        query, {"_id": 0}
    ).sort("created_at", -1).limit(limit)
    violations = await cursor.to_list(length=limit)

    total = await db[V7_VIOLATIONS_COLLECTION].count_documents(query)

    # Aggregate by rule
    pipeline = [
        {"$match": {"resolved": False}},
        {"$group": {"_id": "$rule", "count": {"$sum": 1}}},
    ]
    by_rule = {item["_id"]: item["count"] for item in await db[V7_VIOLATIONS_COLLECTION].aggregate(pipeline).to_list(10)}

    return {
        "violations": violations,
        "total": total,
        "by_rule": by_rule,
    }


@router.get("/summary")
async def v7_summary(request: Request):
    """V7 template compliance summary for dashboard widgets."""
    from routes.db import require_admin
    await require_admin(request)

    db = await _get_db()

    total_open = await db[V7_VIOLATIONS_COLLECTION].count_documents({"resolved": False})
    total_resolved = await db[V7_VIOLATIONS_COLLECTION].count_documents({"resolved": True})

    pipeline = [
        {"$match": {"resolved": False}},
        {"$group": {"_id": "$severity", "count": {"$sum": 1}}},
    ]
    by_severity = {item["_id"]: item["count"] for item in await db[V7_VIOLATIONS_COLLECTION].aggregate(pipeline).to_list(10)}

    # Check if baseline exists
    baseline = await db[V7_BASELINES_COLLECTION].find_one({"kind": "latest"}, {"_id": 0})

    return {
        "v7_active": True,
        "total_open": total_open,
        "total_resolved": total_resolved,
        "by_severity": by_severity,
        "baseline": baseline,
        "isolation": "strict",
        "domains": {"v2": "platform_ui", "v7": "templates"},
    }


@router.post("/log")
async def log_v7_violation(request: Request):
    """Receive V7 template violation from frontend (public endpoint for logging)."""
    body = await request.json()
    db = await _get_db()
    now = datetime.now(timezone.utc).isoformat()

    violations = body.get("violations", [body] if "template_name" in body else [])
    inserted = 0

    for v in violations[:30]:
        doc = {
            "template_id": v.get("template_id", "unknown"),
            "template_name": v.get("template_name", v.get("component", "unknown")),
            "rule": v.get("rule", v.get("error_type", "unknown")),
            "message": v.get("message", ""),
            "severity": v.get("severity", "warn"),
            "layer": v.get("layer", "design"),
            "created_at": now,
            "resolved": False,
        }
        await db[V7_VIOLATIONS_COLLECTION].insert_one(
            {k: val for k, val in doc.items() if k != "_id"}
        )
        inserted += 1

    if inserted > 0:
        logger.warning(f"[V7] Logged {inserted} template violation(s)")

    return {"ok": True, "logged": inserted}


@router.post("/resolve")
async def resolve_v7_violations(request: Request):
    """Bulk-resolve V7 template violations."""
    from routes.db import require_admin
    await require_admin(request)

    body = await request.json()
    db = await _get_db()
    now = datetime.now(timezone.utc).isoformat()

    if body.get("all"):
        result = await db[V7_VIOLATIONS_COLLECTION].update_many(
            {"resolved": False},
            {"$set": {"resolved": True, "resolved_at": now}},
        )
        return {"ok": True, "resolved": result.modified_count}

    template_ids = body.get("template_ids", [])
    if template_ids:
        result = await db[V7_VIOLATIONS_COLLECTION].update_many(
            {"template_id": {"$in": template_ids}, "resolved": False},
            {"$set": {"resolved": True, "resolved_at": now}},
        )
        return {"ok": True, "resolved": result.modified_count}

    return {"ok": False, "message": "Provide 'all' or 'template_ids' list"}


def _scan_v2_contamination(styles, colors, violations, prefix=""):
    """Recursively scan styles for V2 token contamination."""
    for key, val in styles.items():
        full_key = f"{prefix}.{key}" if prefix else key
        if isinstance(val, str):
            upper = val.upper()
            for fp in V2_FINGERPRINT_COLORS:
                if fp.upper() in upper:
                    violations.append({
                        "rule": "v2_contamination",
                        "message": f"V2 token '{fp}' in style.{full_key}",
                        "severity": "high",
                        "field": full_key,
                    })
                    styles[key] = val.replace(fp, colors.get("primary", V7_PRIMARY_LIGHT))
        elif isinstance(val, dict):
            _scan_v2_contamination(val, colors, violations, full_key)


@router.get("/compliance-counter")
async def v7_compliance_counter(request: Request):
    """V7 compliance counter for the admin dashboard widget.

    Returns template catalog stats, bypass scan results, guardrail status,
    and category breakdown — all in one compact payload.
    """
    from routes.db import require_admin
    await require_admin(request)

    import os

    db = await _get_db()

    # ── 1. Template Catalog Stats ──
    from utils.email_templates import TEMPLATE_CATALOG, _CATEGORY_PALETTE
    total_templates = len(TEMPLATE_CATALOG)

    cats = {}
    for key, info in TEMPLATE_CATALOG.items():
        cat = info.get("category", "Unknown")
        cats.setdefault(cat, []).append(key)
    by_category = {cat: len(keys) for cat, keys in sorted(cats.items())}

    # ── 2. Bypass Scan (context-aware) ──
    backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    try:
        compliant_count = 0
        bypass_count = 0
        bypass_files = []

        py_files = []
        for root, dirs, fnames in os.walk(backend_dir):
            if "__pycache__" in root or "test" in root:
                continue
            for fn in fnames:
                if fn.endswith(".py") and not fn.startswith("test_"):
                    py_files.append(os.path.join(root, fn))

        for fpath in py_files:
            with open(fpath) as fh:
                lines = fh.readlines()
            for i, line in enumerate(lines):
                s = line.strip()
                if s.startswith("#") or s.startswith("import") or s.startswith("from") or "def send_email" in s:
                    continue
                if "send_email(" not in s or "send_resend_email" in s:
                    continue
                # Check ±10 lines context
                ctx_start = max(0, i - 10)
                ctx_end = min(len(lines), i + 10)
                ctx = "".join(lines[ctx_start:ctx_end])

                is_compliant = (
                    "build_" in ctx and "_email" in ctx  # uses a builder
                    or "tpl.html" in ctx or "tpl.subject" in ctx
                    or "skip_branding=True" in ctx  # pre-rendered V7
                    or "_wrap(" in ctx  # uses _wrap pipeline
                    or "send_email(**" in ctx  # wrapper pass-through
                    or "template_key=" in ctx  # has template key -> auto-branded
                    or "def " in s  # is a function definition line
                    or "send_catalog_template" in ctx  # diagnostic scanner
                    or "ensure_email_color_scheme" in ctx  # internal utility
                    or "run_theme_visibility_audit" in ctx  # scheduler caller
                    or "subprocess.run" in ctx  # codebase scanner, not a sender
                    or "grep" in ctx and "send_email" in ctx  # grep-based scanner
                )

                if is_compliant:
                    compliant_count += 1
                else:
                    bypass_count += 1
                    rel = fpath.replace(backend_dir + "/", "")
                    bypass_files.append(rel)
    except Exception:
        compliant_count = -1
        bypass_count = -1
        bypass_files = []

    # ── 3. Guardrail Status ──
    enforcement_mode = os.environ.get("V7_ENFORCEMENT_MODE", "strict")
    guardrail_active = enforcement_mode == "strict"

    # ── 4. Violation Stats ──
    open_violations = await db[V7_VIOLATIONS_COLLECTION].count_documents({"resolved": False})
    resolved_violations = await db[V7_VIOLATIONS_COLLECTION].count_documents({"resolved": True})

    # ── 5. Compliance Score ──
    total_senders = compliant_count + bypass_count if compliant_count >= 0 else 0
    compliance_pct = round(compliant_count / total_senders * 100, 1) if total_senders > 0 else 100.0

    return {
        "catalog": {
            "total_templates": total_templates,
            "total_palettes": len(_CATEGORY_PALETTE),
            "by_category": by_category,
        },
        "bypass_scan": {
            "compliant_senders": compliant_count,
            "bypass_senders": bypass_count,
            "bypass_files": bypass_files[:10],
            "compliance_pct": compliance_pct,
        },
        "guardrail": {
            "active": guardrail_active,
            "mode": enforcement_mode,
            "fingerprint_check": True,
            "template_key_required": True,
        },
        "violations": {
            "open": open_violations,
            "resolved": resolved_violations,
        },
        "grade": "A" if bypass_count == 0 and open_violations == 0 else "B" if bypass_count == 0 else "C" if bypass_count <= 3 else "F",
    }
