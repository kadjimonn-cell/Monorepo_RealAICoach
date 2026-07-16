from typing import Any, Dict, List


TIER_NAMES = ["core", "feature", "experimental"]

TIER_POLICIES = {
    "core": {
        "label": "Core Engine (Protected)",
        "description": "Mission-critical modules. Full pipeline + admin approval + auto-rollback on regression.",
        "required_gates": ["tests", "coverage", "validation", "performance", "e2e", "visual", "deployment"],
        "require_admin_approval": True,
        "require_baseline_lock": True,
        "auto_rollback_on_regression": True,
        "allow_skip_gates": False,
        "isolation_level": "none",
    },
    "feature": {
        "label": "Feature Modules (Flexible)",
        "description": "Standard product modules. Standard pipeline gates, faster iteration.",
        "required_gates": ["tests", "coverage", "performance"],
        "require_admin_approval": False,
        "require_baseline_lock": False,
        "auto_rollback_on_regression": False,
        "allow_skip_gates": False,
        "isolation_level": "none",
    },
    "experimental": {
        "label": "Experimental Zone (Isolated)",
        "description": "Sandbox modules. Minimal gates, fully isolated — failures cannot propagate.",
        "required_gates": ["tests"],
        "require_admin_approval": False,
        "require_baseline_lock": False,
        "auto_rollback_on_regression": False,
        "allow_skip_gates": True,
        "isolation_level": "full",
    },
}

DEFAULT_MODULE_REGISTRY = {
    "routes/auth.py": "core",
    "routes/payments.py": "core",
    "routes/autonomous_engine.py": "core",
    "utils/email_service.py": "core",
    "routes/admin.py": "core",
    "routes/webhook.py": "core",
    "routes/learning_hub.py": "feature",
    "routes/ai_features.py": "feature",
    "routes/analytics.py": "feature",
    "routes/email_notifications.py": "feature",
    "routes/newsletter.py": "feature",
    "routes/mini_apps.py": "feature",
    "routes/auto_scaling.py": "feature",
    "routes/sandbox.py": "experimental",
    "routes/beta_features.py": "experimental",
    "routes/ab_tests.py": "experimental",
}


def group_registry_by_tier(registry: Dict[str, str]) -> Dict[str, List[str]]:
    by_tier: Dict[str, List[str]] = {tier: [] for tier in TIER_NAMES}
    for module, tier in registry.items():
        if tier in by_tier:
            by_tier[tier].append(module)
        else:
            by_tier.setdefault("experimental", []).append(module)
    return by_tier


def tier_policy_summary() -> Dict[str, Dict[str, Any]]:
    return {
        tier: {
            "label": policy["label"],
            "gates": len(policy["required_gates"]),
            "admin_approval": policy["require_admin_approval"],
            "auto_rollback": policy["auto_rollback_on_regression"],
            "isolation": policy["isolation_level"],
        }
        for tier, policy in TIER_POLICIES.items()
    }


def build_tier_validation_checks(policy: Dict[str, Any], baseline: Dict[str, Any], similar_failures: List[dict]) -> Dict[str, Any]:
    checks: Dict[str, Any] = {
        "required_gates": policy["required_gates"],
        "gates_count": len(policy["required_gates"]),
        "auto_rollback_on_regression": policy["auto_rollback_on_regression"],
        "isolation_level": policy["isolation_level"],
        "known_failures": len(similar_failures),
    }

    if policy["require_admin_approval"]:
        checks["admin_approval_required"] = True

    if policy["require_baseline_lock"]:
        checks["baseline_locked"] = bool(baseline.get("locked", False))
        checks["baseline_status"] = baseline.get("status", "UNKNOWN")

    if policy["isolation_level"] == "full":
        checks["isolated"] = True
        checks["propagation_blocked"] = True

    if similar_failures:
        checks["recent_failure"] = similar_failures[0].get("error_signature", "")[:100]
        rec = next((f.get("fix_applied") for f in similar_failures if f.get("fix_confirmed")), None)
        if rec:
            checks["recommended_fix"] = str(rec)[:200]

    return checks
