"""
Backend tests for the LLM circuit breaker feature in routes/auto_scaling.py
plus light regression coverage for scaling + health endpoints.

Scope (per iteration-10 review request):
- /api/admin/scaling/status returns 200 with llm_circuit_breaker field
  (paused=False, consecutive_failure_count=0) after re-arm
- /api/admin/scaling/rearm returns 200 with admin session cookie AND
  X-Requested-With: XMLHttpRequest header (CSRF middleware requirement)
- /api/admin/scaling/rearm returns 403 without admin session
- /api/admin/scaling/rearm returns 403 without X-Requested-With (CSRF)
- Regression: /api/admin/scaling/rules, /history, /ai-history for admin
- Regression: /api/health (through ingress) and /health on backend port
  (local, since root /health is not exposed by preview ingress)
- Mongo llm_usage_log has entries with feature='auto_scaling_eval'
"""
import os
import time
import pytest
import requests
from pathlib import Path

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL")
if not BASE_URL:
    # Fallback: read from /app/frontend/.env
    for line in Path("/app/frontend/.env").read_text().splitlines():
        if line.startswith("REACT_APP_BACKEND_URL="):
            BASE_URL = line.split("=", 1)[1].strip().strip('"')
            break
assert BASE_URL, "REACT_APP_BACKEND_URL not set"
BASE_URL = BASE_URL.rstrip("/")

# Local backend URL for probes that are NOT exposed via /api/* ingress.
LOCAL_BACKEND = "http://localhost:8001"

ADMIN_EMAIL = "admin@realaicoach.app"
ADMIN_PASSWORD = "NewAdminPass2026!"


# ---------- fixtures ----------

@pytest.fixture(scope="session")
def admin_session() -> requests.Session:
    s = requests.Session()
    r = s.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
        headers={"X-Requested-With": "XMLHttpRequest"},
        timeout=20,
    )
    assert r.status_code == 200, f"admin login failed: {r.status_code} {r.text[:300]}"
    assert "session_token" in s.cookies, f"session_token cookie not set: {dict(s.cookies)}"
    return s


@pytest.fixture(scope="session")
def anon_session() -> requests.Session:
    return requests.Session()


# ---------- helpers ----------

def _rearm(session: requests.Session) -> requests.Response:
    return session.post(
        f"{BASE_URL}/api/admin/scaling/rearm",
        headers={"X-Requested-With": "XMLHttpRequest"},
        timeout=20,
    )


# ---------- HEALTH ----------

class TestHealth:
    def test_api_health_via_ingress(self):
        r = requests.get(f"{BASE_URL}/api/health", timeout=15)
        assert r.status_code == 200
        body = r.json()
        assert body.get("status") == "healthy"

    def test_root_health_on_backend_port(self):
        """Root /health is a readiness probe consumed by k8s, not the /api ingress.
        We assert it responds 200 on the backend port directly."""
        r = requests.get(f"{LOCAL_BACKEND}/health", timeout=10)
        assert r.status_code == 200


# ---------- CIRCUIT BREAKER ----------

class TestCircuitBreaker:
    def test_rearm_first_to_normalize_state(self, admin_session):
        """Ensure breaker starts paused=False, count=0 for the rest of the suite."""
        r = _rearm(admin_session)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body.get("message") == "Auto-scaling LLM circuit breaker re-armed"
        assert isinstance(body.get("scheduler_resumed"), bool)

    def test_scaling_status_contains_breaker_fields(self, admin_session):
        r = admin_session.get(f"{BASE_URL}/api/admin/scaling/status", timeout=20)
        assert r.status_code == 200, r.text
        body = r.json()
        assert "llm_circuit_breaker" in body, f"missing llm_circuit_breaker in {list(body.keys())}"
        breaker = body["llm_circuit_breaker"]
        assert breaker.get("paused") is False, f"expected paused=False, got {breaker}"
        assert breaker.get("consecutive_failure_count") == 0, f"expected count=0, got {breaker}"

    def test_rearm_success_with_admin_and_csrf(self, admin_session):
        r = _rearm(admin_session)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body.get("message") == "Auto-scaling LLM circuit breaker re-armed"
        assert "scheduler_resumed" in body
        assert isinstance(body["scheduler_resumed"], bool)

    def test_rearm_without_session_returns_403(self, anon_session):
        r = anon_session.post(
            f"{BASE_URL}/api/admin/scaling/rearm",
            headers={"X-Requested-With": "XMLHttpRequest"},
            timeout=15,
        )
        assert r.status_code == 403, f"expected 403 anon, got {r.status_code}: {r.text[:300]}"

    def test_rearm_without_csrf_header_returns_403(self, admin_session):
        r = admin_session.post(f"{BASE_URL}/api/admin/scaling/rearm", timeout=15)
        # CSRF middleware should block state-changing requests missing X-Requested-With
        assert r.status_code == 403, f"expected 403 CSRF, got {r.status_code}: {r.text[:300]}"
        # Body should mention CSRF (not strict — some middleware returns generic 403)
        txt = r.text.lower()
        assert "csrf" in txt or "forbidden" in txt or "x-requested-with" in txt, \
            f"unexpected 403 body: {r.text[:300]}"


# ---------- SCALING REGRESSION ----------

class TestScalingRegression:
    def test_scaling_rules(self, admin_session):
        r = admin_session.get(f"{BASE_URL}/api/admin/scaling/rules", timeout=20)
        assert r.status_code == 200, r.text
        # Response should be a list or dict; just validate JSON
        r.json()

    def test_scaling_history(self, admin_session):
        r = admin_session.get(f"{BASE_URL}/api/admin/scaling/history", timeout=20)
        assert r.status_code == 200, r.text
        r.json()

    def test_scaling_ai_history(self, admin_session):
        r = admin_session.get(f"{BASE_URL}/api/admin/scaling/ai-history", timeout=20)
        assert r.status_code == 200, r.text
        r.json()


# ---------- LLM USAGE LOG (Mongo direct) ----------

class TestLLMUsageLog:
    """Verify auto_scaling_eval logs LLM calls to db.llm_usage_log via services/llm_usage_logger.py.
    Job runs every 60s. We check for existing entries; if none yet, we wait one interval + margin.
    """

    def _get_db(self):
        pymongo = pytest.importorskip("pymongo")
        env_path = Path("/app/backend/.env")
        env = {}
        for line in env_path.read_text().splitlines():
            if "=" in line and not line.strip().startswith("#"):
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip().strip('"')
        mongo_url = env.get("MONGO_URL") or "mongodb://localhost:27017"
        db_name = env.get("DB_NAME") or "realtalk_db"
        client = pymongo.MongoClient(mongo_url, serverSelectionTimeoutMS=5000)
        return client[db_name]

    def test_llm_usage_log_has_auto_scaling_eval_entries(self):
        db = self._get_db()
        coll = db["llm_usage_log"]
        # Immediate check
        count = coll.count_documents({"feature": "auto_scaling_eval"})
        if count == 0:
            # Wait one job interval (60s) + margin for a fresh LLM call to be logged
            for _ in range(8):  # up to ~80s
                time.sleep(10)
                count = coll.count_documents({"feature": "auto_scaling_eval"})
                if count > 0:
                    break
        assert count > 0, "no auto_scaling_eval entries found in llm_usage_log after ~80s wait"

        # Inspect one recent entry — should have model field populated (gpt-4o per feature spec)
        sample = coll.find_one({"feature": "auto_scaling_eval"}, sort=[("_id", -1)])
        assert sample is not None
        # Model may be present as "model" or "model_name"; require presence of at least one
        has_model = ("model" in sample) or ("model_name" in sample)
        assert has_model, f"sample missing model field: keys={list(sample.keys())}"


# ---------- TEARDOWN: leave breaker rearmed (paused=False) ----------

def teardown_module(module):
    """Per review-request instruction: leave breaker in paused=False state."""
    try:
        s = requests.Session()
        r = s.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
            headers={"X-Requested-With": "XMLHttpRequest"},
            timeout=20,
        )
        if r.status_code == 200:
            s.post(
                f"{BASE_URL}/api/admin/scaling/rearm",
                headers={"X-Requested-With": "XMLHttpRequest"},
                timeout=15,
            )
    except Exception:
        pass
