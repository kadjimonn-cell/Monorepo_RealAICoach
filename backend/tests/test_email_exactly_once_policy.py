"""
Iteration 850 — Backend E2E regression suite for the global exactly-once email
enforcement policy.

Policy: "The same email should never be sent twice to the same users. Every
email sent should always be unique."

Implementation layers under test (utils/email_service.py):
  1) Explicit dedupe_key path      -> permanent idempotency (email_delivery_idempotency)
  2) No dedupe_key, identical body -> global content-hash TTL dedupe (email_send_dedupe)
  3) After TTL dedupe cleared      -> permanent notification cap
                                     (email_notification_send_caps, max=1 default)
  4) Admin-approved override doc   -> email_notification_template_policies

Provider (_send_via_resend_with_throttle) is monkeypatched — no real Resend
emails leave the box.
"""

import asyncio
import os
import sys
import time
import uuid

import pytest
import requests

sys.path.insert(0, "/app/backend")

# Load backend/.env so MONGO_URL / DB_NAME etc are available to test process.
from dotenv import load_dotenv  # noqa: E402
load_dotenv("/app/backend/.env")

BASE_URL = "http://localhost:8001"

# ── Fresh-loop / fresh-Motor helper (adapted from iteration_849 pattern) ──


def _run(coro_factory):
    """Run an async scenario on a fresh event loop with a fresh Motor client.

    Motor is loop-bound; every test needs a fresh client re-bound to the
    fresh loop so async db reads inside `send_email` don't cross loops.
    """
    from motor.motor_asyncio import AsyncIOMotorClient

    loop = asyncio.new_event_loop()
    try:
        asyncio.set_event_loop(loop)
        client = AsyncIOMotorClient(os.environ["MONGO_URL"], io_loop=loop)
        fresh_db = client[os.environ["DB_NAME"]]

        # Patch every module that holds a `db` reference so its DB reads use
        # the fresh loop-bound client.
        patched = []
        for mod_name in ("routes.db", "utils.email_service"):
            mod = sys.modules.get(mod_name)
            if mod is not None and hasattr(mod, "db"):
                patched.append((mod, mod.db))
                mod.db = fresh_db

        try:
            try:
                coro = coro_factory(fresh_db)
            except TypeError:
                coro = coro_factory()
            return loop.run_until_complete(coro)
        finally:
            for mod, orig in patched:
                mod.db = orig
            client.close()
    finally:
        loop.close()


# ── Test content helpers ──

_V7_WRAPPED_TEMPLATE = (
    '<html><body>'
    '<div class="em-outer" style="background:#fff">'
    '<div class="em-inner">'
    '<h1>RealAICoach Exactly-Once Probe</h1>'
    '<p>{body}</p>'
    '</div></div></body></html>'
)


def _v7(body: str) -> str:
    return _V7_WRAPPED_TEMPLATE.replace("{body}", body)


def _unique_recipient() -> str:
    # realaicoach.app avoids the AUTH_EMAIL_TEST_ALLOWLIST_DOMAINS path and
    # is not blocked by _is_valid_recipient_email.  Using unique local-part
    # per run so cap collections start empty.
    return f"e2e.policy.{int(time.time()*1000)}.{uuid.uuid4().hex[:6]}@realaicoach.app"


# ── Cleanup helper ──

async def _cleanup(db, *, recipient: str, template_key: str, dedupe_seeds: list):
    """Remove test rows we created so re-runs are idempotent."""
    from utils.email_service import canonicalize_recipient_email

    canonical = canonicalize_recipient_email(recipient)
    await db.email_send_dedupe.delete_many({
        "dedupe_key": {"$regex": f".*{canonical}.*"}
    })
    await db.email_notification_send_caps.delete_many({
        "canonical_recipient": canonical
    })
    await db.email_delivery_idempotency.delete_many({
        "canonical_recipient": canonical
    })
    for seed in dedupe_seeds or []:
        await db.email_delivery_idempotency.delete_many({
            "dedupe_seed": str(seed).lower()
        })


# ═══════════════════════════════════════════════════════════════════════
# TEST 1 — Env + module constant
# ═══════════════════════════════════════════════════════════════════════

def test_env_and_module_constant_equal_1():
    with open("/app/backend/.env", "r") as f:
        env_body = f.read()
    assert "EMAIL_NOTIFICATION_MAX_PER_FINGERPRINT=1" in env_body, \
        ".env must pin the notification cap to 1"

    import utils.email_service as es
    assert es._EMAIL_NOTIFICATION_MAX_PER_FINGERPRINT == 1, \
        "Module constant must equal 1"


# ═══════════════════════════════════════════════════════════════════════
# TEST 2 — Backend health check
# ═══════════════════════════════════════════════════════════════════════

def test_backend_health_ok():
    r = requests.get(f"{BASE_URL}/api/health", timeout=5)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body.get("status") == "healthy"


# ═══════════════════════════════════════════════════════════════════════
# TEST 3 — Exactly-once: identical send twice → 2nd suppressed by dedupe
# ═══════════════════════════════════════════════════════════════════════

def test_exactly_once_identical_send_suppressed_by_dedupe():
    import utils.email_service as es

    recipient = _unique_recipient()
    template_key = "e2e_exactly_once_probe"
    subject = "E2E exactly-once probe — identical"
    content = _v7("Identical body for dedupe test.")

    provider_calls = {"n": 0, "params": []}

    async def fake_send(params):
        provider_calls["n"] += 1
        provider_calls["params"].append(params)
        return {"id": f"test-{provider_calls['n']}"}

    async def scenario(db):
        orig = es._send_via_resend_with_throttle
        es._send_via_resend_with_throttle = fake_send
        try:
            r1 = await es.send_email(
                recipient_email=recipient,
                subject=subject,
                content=content,
                template_key=template_key,
            )
            r2 = await es.send_email(
                recipient_email=recipient,
                subject=subject,
                content=content,
                template_key=template_key,
            )
            return r1, r2
        finally:
            es._send_via_resend_with_throttle = orig
            await _cleanup(db, recipient=recipient, template_key=template_key,
                           dedupe_seeds=[])

    r1, r2 = _run(scenario)

    # 1st send OK, provider invoked once
    assert r1.get("success") is True, f"1st send should succeed: {r1}"
    assert not r1.get("skipped"), f"1st send must not be skipped: {r1}"
    assert provider_calls["n"] == 1, f"Provider must be invoked exactly once, got {provider_calls['n']}"

    # 2nd send suppressed by content-hash dedupe
    assert r2.get("skipped") is True, f"2nd send must be skipped: {r2}"
    assert "email-dedupe: duplicate suppressed" in str(r2.get("error") or ""), \
        f"2nd send must indicate dedupe suppression: {r2}"
    assert provider_calls["n"] == 1, \
        f"Provider must NOT be invoked twice — was {provider_calls['n']}"


# ═══════════════════════════════════════════════════════════════════════
# TEST 4 — Bypass-resistance: delete TTL dedupe rows, cap still blocks
# ═══════════════════════════════════════════════════════════════════════

def test_bypass_resistance_cap_blocks_after_dedupe_cleared():
    import utils.email_service as es

    recipient = _unique_recipient()
    template_key = "e2e_exactly_once_probe"
    subject = "E2E bypass-resistance probe"
    content = _v7("Body for bypass-resistance test.")

    provider_calls = {"n": 0}

    async def fake_send(params):
        provider_calls["n"] += 1
        return {"id": f"test-{provider_calls['n']}"}

    async def scenario(db):
        # Ensure clean cap so the FIRST call succeeds.
        from utils.email_service import canonicalize_recipient_email
        canonical = canonicalize_recipient_email(recipient)
        await db.email_notification_send_caps.delete_many({"canonical_recipient": canonical})

        orig = es._send_via_resend_with_throttle
        es._send_via_resend_with_throttle = fake_send
        try:
            # 1st call succeeds -> provider invoked, cap incremented to 1
            r1 = await es.send_email(
                recipient_email=recipient,
                subject=subject,
                content=content,
                template_key=template_key,
            )

            # Simulate manual bypass: nuke the TTL dedupe layer rows
            await db.email_send_dedupe.delete_many({})

            # 2nd call — dedupe layer is gone, but PERMANENT cap max=1
            # should now block the send.
            r2 = await es.send_email(
                recipient_email=recipient,
                subject=subject,
                content=content,
                template_key=template_key,
            )

            # Fetch the cap row for evidence
            cap_row = await db.email_notification_send_caps.find_one(
                {"canonical_recipient": canonical}, {"_id": 0}
            )
            return r1, r2, cap_row
        finally:
            es._send_via_resend_with_throttle = orig
            await _cleanup(db, recipient=recipient, template_key=template_key,
                           dedupe_seeds=[])

    r1, r2, cap_row = _run(scenario)

    assert r1.get("success") is True and not r1.get("skipped"), f"1st send should send: {r1}"
    assert provider_calls["n"] == 1, f"Provider invoked once for 1st send only, got {provider_calls['n']}"

    assert r2.get("skipped") is True, f"2nd send after dedupe-bypass must be skipped: {r2}"
    assert "email-cap-guardrail: max sends reached" in str(r2.get("error") or ""), \
        f"2nd send must be blocked by cap guardrail (not dedupe): {r2}"
    assert r2.get("cap_max") == 1, f"Cap max must equal 1, got {r2.get('cap_max')}"
    assert provider_calls["n"] == 1, \
        f"Provider must NOT be invoked twice — was {provider_calls['n']}"
    assert cap_row is not None and int(cap_row.get("send_count", 0)) >= 1


# ═══════════════════════════════════════════════════════════════════════
# TEST 5 — Unique content passes: different fingerprint = different send
# ═══════════════════════════════════════════════════════════════════════

def test_unique_content_passes_provider_invoked_again():
    import utils.email_service as es

    recipient = _unique_recipient()
    template_key = "e2e_exactly_once_probe"

    provider_calls = {"n": 0}

    async def fake_send(params):
        provider_calls["n"] += 1
        return {"id": f"test-{provider_calls['n']}"}

    async def scenario(db):
        orig = es._send_via_resend_with_throttle
        es._send_via_resend_with_throttle = fake_send
        try:
            r1 = await es.send_email(
                recipient_email=recipient,
                subject="Unique probe A",
                content=_v7("Body variant AAA."),
                template_key=template_key,
            )
            r2 = await es.send_email(
                recipient_email=recipient,
                subject="Unique probe B — different subject",
                content=_v7("Body variant BBB — genuinely different content."),
                template_key=template_key,
            )
            return r1, r2
        finally:
            es._send_via_resend_with_throttle = orig
            await _cleanup(db, recipient=recipient, template_key=template_key,
                           dedupe_seeds=[])

    r1, r2 = _run(scenario)

    assert r1.get("success") is True and not r1.get("skipped"), f"1st unique send: {r1}"
    assert r2.get("success") is True and not r2.get("skipped"), \
        f"2nd unique send with different fingerprint MUST send: {r2}"
    assert provider_calls["n"] == 2, \
        f"Provider invoked twice for two unique sends, got {provider_calls['n']}"


# ═══════════════════════════════════════════════════════════════════════
# TEST 6 — Explicit dedupe_key path (permanent idempotency)
# ═══════════════════════════════════════════════════════════════════════

def test_explicit_dedupe_key_permanent_idempotency():
    import utils.email_service as es

    recipient = _unique_recipient()
    template_key = "e2e_exactly_once_probe"
    dedupe_key = f"e2e-policy-test-{uuid.uuid4()}"

    provider_calls = {"n": 0}

    async def fake_send(params):
        provider_calls["n"] += 1
        return {"id": f"test-{provider_calls['n']}"}

    async def scenario(db):
        orig = es._send_via_resend_with_throttle
        es._send_via_resend_with_throttle = fake_send
        try:
            r1 = await es.send_email(
                recipient_email=recipient,
                subject="Idempotency probe",
                content=_v7("Body A."),
                template_key=template_key,
                dedupe_key=dedupe_key,
            )
            # Identical repeat with same dedupe_key — must be blocked by permanent idempotency
            r2 = await es.send_email(
                recipient_email=recipient,
                subject="Idempotency probe",
                content=_v7("Body A."),
                template_key=template_key,
                dedupe_key=dedupe_key,
            )
            return r1, r2
        finally:
            es._send_via_resend_with_throttle = orig
            await _cleanup(db, recipient=recipient, template_key=template_key,
                           dedupe_seeds=[dedupe_key])

    r1, r2 = _run(scenario)

    assert r1.get("success") is True and not r1.get("skipped"), f"1st idempotency send: {r1}"
    assert provider_calls["n"] == 1

    assert r2.get("skipped") is True, f"2nd idempotency send must be skipped: {r2}"
    assert "email-idempotency: duplicate suppressed" in str(r2.get("error") or ""), \
        f"2nd send must indicate idempotency suppression: {r2}"
    assert provider_calls["n"] == 1, \
        f"Provider must NOT be invoked twice, got {provider_calls['n']}"


# ═══════════════════════════════════════════════════════════════════════
# TEST 7 — Cap policy override respected
# ═══════════════════════════════════════════════════════════════════════

def test_cap_policy_override_respected():
    import utils.email_service as es

    override_key = "e2e_cap_override_test"
    unlisted_key = f"e2e_cap_unlisted_{uuid.uuid4().hex[:8]}"

    async def scenario(db):
        # Insert policy doc
        await db.email_notification_template_policies.delete_many(
            {"template_key": override_key}
        )
        await db.email_notification_template_policies.insert_one({
            "template_key": override_key,
            "active": True,
            "max_per_fingerprint": 2,
        })
        try:
            es.clear_template_cap_policy_cache()
            override_cap = await es._resolve_notification_cap_limit(override_key)
            unlisted_cap = await es._resolve_notification_cap_limit(unlisted_key)
            return override_cap, unlisted_cap
        finally:
            await db.email_notification_template_policies.delete_many(
                {"template_key": override_key}
            )
            es.clear_template_cap_policy_cache()

    override_cap, unlisted_cap = _run(scenario)

    assert override_cap == 2, \
        f"Template policy override must yield 2, got {override_cap}"
    assert unlisted_cap == 1, \
        f"Unlisted template must fall back to global default 1, got {unlisted_cap}"


# ═══════════════════════════════════════════════════════════════════════
# TEST 8 — clear_template_cap_policy_cache exists & callable
# ═══════════════════════════════════════════════════════════════════════

def test_clear_template_cap_policy_cache_symbol_is_callable():
    import utils.email_service as es
    assert callable(getattr(es, "clear_template_cap_policy_cache", None))
    # Both global clear and single-template clear must not raise.
    es.clear_template_cap_policy_cache()
    es.clear_template_cap_policy_cache("any_template")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
