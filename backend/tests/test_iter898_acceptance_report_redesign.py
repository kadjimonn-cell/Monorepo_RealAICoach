"""Iteration 898 - Acceptance Report PDF redesign functional/structural verification.

Covers:
  1. Empty-state end-to-end: generate_acceptance_reports() with no /tmp artifacts must produce PDF+MD+JSON.
  2. PDF is PDF 1.4, opens with pymupdf, single page in empty-artifact state.
  3. Empty-state text markers: "No scenario artifacts", "Communication Policy Compliance Matrix",
     "Tamper-Evident Integrity", "PASS Criteria".
  4. Populated-state: seed 3 artifacts (1 forced FAIL), regenerate, verify counts + provider strings + PASS/FAIL.
  5. Report integrity 64-char hex + tamper_signature present in PDF and JSON.
  6. Nightly scheduler wrapper import (scheduler_jobs.audit_gates) still resolves.
  7. Backend regression: GET /api/health -> 200, POST /api/auth/login (admin) -> 200.
"""
from __future__ import annotations

import asyncio
import json
import os
import re
import sys
from pathlib import Path

import pytest
import requests

# Make backend modules importable
BACKEND_DIR = Path("/app/backend")
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

# Load backend .env for MONGO_URL / DB_NAME (Motor client used by the generator via db)
from dotenv import load_dotenv  # noqa: E402
load_dotenv(BACKEND_DIR / ".env")

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL") or "https://coach-web-preview.preview.emergentagent.com"
BASE_URL = BASE_URL.rstrip("/")

ARTIFACT_FILES = [
    "/tmp/fedapay_togo_basic_yearly_card_test.json",
    "/tmp/fedapay_abidjan_premium_monthly_test.json",
    "/tmp/fedapay_abidjan_basic_monthly_test.json",
    "/tmp/fedapay_togo_basic_monthly_card_test.json",
    "/tmp/iap_google_quebec_premium_monthly_test_after_fix.json",
    "/tmp/stripe_paris_basic_monthly_test.json",
    "/tmp/stripe_miami_basic_monthly_test.json",
    "/tmp/paypal_london_basic_monthly_test.json",
    "/tmp/paypal_sanantonio_premium_monthly_test.json",
    "/tmp/paypal_paris_basic_monthly_test.json",
]

PDF_MEMORY = Path("/app/memory/ACCEPTANCE_REPORT.pdf")
MD_MEMORY = Path("/app/memory/ACCEPTANCE_REPORT.md")
JSON_TMP = Path("/tmp/cross_provider_acceptance_report.json")


def _cleanup_artifacts():
    for p in ARTIFACT_FILES:
        try:
            Path(p).unlink()
        except FileNotFoundError:
            pass


def _run_generate():
    """Invoke generate_acceptance_reports with a real Motor db, cwd=/app/backend."""
    prev_cwd = os.getcwd()
    os.chdir(str(BACKEND_DIR))
    try:
        from motor.motor_asyncio import AsyncIOMotorClient
        from utils.acceptance_report_generator import generate_acceptance_reports

        mongo_url = os.environ["MONGO_URL"]
        db_name = os.environ["DB_NAME"]

        async def _main():
            client = AsyncIOMotorClient(mongo_url)
            try:
                db = client[db_name]
                return await generate_acceptance_reports(db)
            finally:
                client.close()

        return asyncio.run(_main())
    finally:
        os.chdir(prev_cwd)


def _pdf_text(pdf_path: Path) -> str:
    import fitz  # pymupdf
    doc = fitz.open(str(pdf_path))
    try:
        return "\n".join(page.get_text() for page in doc), doc.page_count
    finally:
        doc.close()


def _pdf_text_only(pdf_path: Path) -> str:
    text, _ = _pdf_text(pdf_path)
    return text


def _pdf_page_count(pdf_path: Path) -> int:
    _, n = _pdf_text(pdf_path)
    return n


# ---------------------------------------------------------------------------
# 1-3 Empty state
# ---------------------------------------------------------------------------

class TestEmptyStateGeneration:
    def test_00_no_artifacts_present(self):
        _cleanup_artifacts()
        for p in ARTIFACT_FILES:
            assert not Path(p).exists(), f"Pre-existing artifact should not exist: {p}"

    def test_01_generator_returns_paths(self):
        _cleanup_artifacts()
        result = _run_generate()
        assert isinstance(result, dict)
        for key in ("json", "markdown", "pdf", "pdf_export", "generated_at", "version", "total", "passed", "failed"):
            assert key in result, f"Missing key {key} in generator result"
        assert result["total"] == 0
        assert result["passed"] == 0
        assert result["failed"] == 0
        assert Path(result["json"]).exists()
        assert Path(result["markdown"]).exists()
        assert Path(result["pdf"]).exists()

    def test_02_pdf_files_exist_and_are_pdf_1_4(self):
        for p in (PDF_MEMORY, Path("/tmp/cross_provider_acceptance_report.pdf")):
            assert p.exists(), f"Expected PDF at {p}"
            head = p.read_bytes()[:8]
            assert head.startswith(b"%PDF-1.4"), f"{p} does not start with %PDF-1.4 (got {head!r})"

    def test_03_pdf_opens_and_is_single_page(self):
        pages = _pdf_page_count(PDF_MEMORY)
        assert pages == 1, f"Expected single-page empty-state PDF, got {pages}"

    def test_04_empty_state_text_markers(self):
        text = _pdf_text_only(PDF_MEMORY)
        for marker in (
            "No scenario artifacts captured for this run",
            "Communication Policy Compliance Matrix",
            "Tamper-Evident Integrity",
            "PASS Criteria",
        ):
            assert marker in text, f"Marker missing from empty-state PDF: {marker!r}"

    def test_05_report_integrity_and_tamper_signature_present(self):
        # PDF text
        text = _pdf_text_only(PDF_MEMORY)
        hex64 = re.findall(r"\b[0-9a-f]{64}\b", text)
        assert len(hex64) >= 2, f"Expected at least 2 64-char hex tokens (integrity + tamper), found {len(hex64)}"

        # JSON output
        j = json.loads(JSON_TMP.read_text())
        assert re.fullmatch(r"[0-9a-f]{64}", j.get("report_integrity_hash", "")), "JSON report_integrity_hash invalid"
        assert re.fullmatch(r"[0-9a-f]{64}", j.get("tamper_signature", "")), "JSON tamper_signature invalid"


# ---------------------------------------------------------------------------
# 4 Populated state
# ---------------------------------------------------------------------------

def _seed_artifact(path: str, provider: str, gateway: str, name: str, location: str,
                   plan: str, duration: str, tx_id: str, receipt: str,
                   user_receipt_sent: bool = True) -> None:
    payload = {
        "summary": {
            "scenario": {
                "name": name,
                "home_address": location,
                "plan": plan,
                "duration": duration,
                "gateway": gateway,
            },
            "transaction": {
                "transaction_id": tx_id,
                "payment_status": "succeeded",
                "provider": provider,
                "notification_sent": True,
                "user_receipt_sent": user_receipt_sent,
                "admin_receipt_sent": True,
                "receipt_number": receipt,
                "notification_dispatch_count": 1,
            },
            "counts": {
                "user_in_app_count": 1,
                "admin_alert_count": 1,
            },
            "audit_event_types": [
                "user_in_app_notification_created",
                "admin_in_app_alert_created",
                "user_receipt_email_sent",
                "admin_receipt_email_sent",
            ],
        }
    }
    Path(path).write_text(json.dumps(payload))


class TestPopulatedState:
    def test_10_seed_and_regenerate(self):
        _cleanup_artifacts()
        # 2 PASS, 1 FAIL (user_receipt_sent=false on the third)
        _seed_artifact(
            "/tmp/stripe_paris_basic_monthly_test.json",
            provider="stripe", gateway="Stripe",
            name="Alice Paris", location="12 Rue Test, Paris, France",
            plan="Basic", duration="1 month",
            tx_id="TEST_TX_STRIPE_001", receipt="RCT-TEST-STRIPE-001",
            user_receipt_sent=True,
        )
        _seed_artifact(
            "/tmp/paypal_london_basic_monthly_test.json",
            provider="paypal", gateway="PayPal",
            name="Bob London", location="221B Baker St, London, UK",
            plan="Basic", duration="1 month",
            tx_id="TEST_TX_PAYPAL_001", receipt="RCT-TEST-PAYPAL-001",
            user_receipt_sent=True,
        )
        _seed_artifact(
            "/tmp/fedapay_abidjan_basic_monthly_test.json",
            provider="fedapay", gateway="FedaPay",
            name="Charlie Abidjan", location="42 Marché Rd, Abidjan, CI",
            plan="Basic", duration="1 month",
            tx_id="TEST_TX_FEDAPAY_001", receipt="RCT-TEST-FEDAPAY-001",
            user_receipt_sent=False,  # forces FAIL
        )

        result = _run_generate()
        assert result["total"] == 3, f"Expected 3 scenarios, got {result['total']}"
        assert result["passed"] == 2, f"Expected 2 passed, got {result['passed']}"
        assert result["failed"] == 1, f"Expected 1 failed, got {result['failed']}"

    def test_11_populated_pdf_content(self):
        text = _pdf_text_only(PDF_MEMORY)

        # Providers
        for provider_str in ("Stripe", "PayPal", "FedaPay"):
            assert provider_str in text, f"Provider {provider_str!r} missing from populated PDF"

        # Both PASS and FAIL statuses present
        assert "PASS" in text, "Expected 'PASS' status text in populated PDF"
        assert "FAIL" in text, "Expected 'FAIL' status text in populated PDF"

        # Scenario counts (KPI 3 and 2 and 1)
        # These will appear as standalone tokens on cards
        assert "3" in text and "2" in text and "1" in text

        # JSON reflects the seeded data
        j = json.loads(JSON_TMP.read_text())
        assert j["total_scenarios"] == 3
        assert j["passed"] == 2
        assert j["failed"] == 1
        providers = {r.get("provider") for r in j["rows"]}
        assert providers == {"Stripe", "PayPal", "FedaPay"}, f"Unexpected providers: {providers}"
        # Confirm the failing row is the fedapay one
        fedapay_row = next(r for r in j["rows"] if r["provider"] == "FedaPay")
        assert fedapay_row["rule_1111_pass"] is False

    def test_12_populated_pdf_still_pdf14_and_valid(self):
        head = PDF_MEMORY.read_bytes()[:8]
        assert head.startswith(b"%PDF-1.4")
        # opens
        _ = _pdf_page_count(PDF_MEMORY)

    def test_13_cleanup_and_restore_empty_state(self):
        _cleanup_artifacts()
        result = _run_generate()
        assert result["total"] == 0
        assert result["passed"] == 0
        assert result["failed"] == 0
        text = _pdf_text_only(PDF_MEMORY)
        assert "No scenario artifacts captured for this run" in text


# ---------------------------------------------------------------------------
# 6 Nightly scheduler import
# ---------------------------------------------------------------------------

class TestSchedulerImport:
    def test_20_scheduler_wrapper_importable(self):
        prev_cwd = os.getcwd()
        os.chdir(str(BACKEND_DIR))
        try:
            from scheduler_jobs.audit_gates import scheduled_acceptance_report_refresh  # noqa: F401
            from utils.acceptance_report_generator import generate_acceptance_reports  # noqa: F401
            assert callable(scheduled_acceptance_report_refresh)
            assert callable(generate_acceptance_reports)
        finally:
            os.chdir(prev_cwd)


# ---------------------------------------------------------------------------
# 7 Backend regression
# ---------------------------------------------------------------------------

class TestBackendRegression:
    def test_30_health(self):
        r = requests.get(f"{BASE_URL}/api/health", timeout=15)
        assert r.status_code == 200, f"/api/health returned {r.status_code}: {r.text[:200]}"

    def test_31_admin_login(self):
        r = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": "admin@realaicoach.app", "password": "NewAdminPass2026!"},
            headers={"Content-Type": "application/json"},
            timeout=20,
        )
        assert r.status_code == 200, f"admin login returned {r.status_code}: {r.text[:300]}"
