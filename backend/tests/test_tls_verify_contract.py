import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from utils.http_tls import get_httpx_verify


TLS_CRITICAL_FILES = [
    "/app/backend/scheduler.py",
    "/app/backend/services/mobile_indexing_analyzer.py",
    "/app/backend/services/global_performance_analyzer.py",
    "/app/backend/services/lighthouse_auditor.py",
    "/app/backend/services/gtec_auto_remediation.py",
    "/app/backend/services/responsiveness_auditor.py",
    "/app/backend/services/gtec_scan_v2.py",
    "/app/backend/routes/security_engine.py",
]


def test_tls_critical_files_do_not_disable_certificate_verification() -> None:
    for file_path in TLS_CRITICAL_FILES:
        source = Path(file_path).read_text(encoding="utf-8")
        assert "verify=False" not in source
        assert "verify = False" not in source


def test_httpx_verify_defaults_to_strict_tls(monkeypatch) -> None:
    monkeypatch.delenv("HTTPX_CA_BUNDLE", raising=False)
    assert get_httpx_verify() is True


def test_httpx_verify_uses_ca_bundle_when_configured(monkeypatch) -> None:
    monkeypatch.setenv("HTTPX_CA_BUNDLE", "/tmp/internal-ca.pem")
    assert get_httpx_verify() == "/tmp/internal-ca.pem"
