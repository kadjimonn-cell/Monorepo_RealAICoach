from pathlib import Path


def test_jobs_portal_summary_endpoint_exists():
    source = Path("/app/backend/routes/jobs.py").read_text(encoding="utf-8")
    assert '@router.get("/portal-summary")' in source
    assert 'async def get_jobs_portal_summary' in source


def test_jobs_portal_summary_exposes_canonical_fields():
    source = Path("/app/backend/routes/jobs.py").read_text(encoding="utf-8")
    for field in [
        '"open_roles"',
        '"candidate_applications"',
        '"interview_applications"',
        '"offer_applications"',
        '"saved_jobs"',
        '"employer_jobs"',
        '"last_sync_at"',
        '"candidate"',
        '"employer"',
    ]:
        assert field in source


def test_job_platform_frontend_uses_canonical_summary_api():
    route_source = Path("/app/frontend/app/job-platform.tsx").read_text(encoding="utf-8")
    hook_source = Path("/app/frontend/src/hooks/useJobsPortalSummary.ts").read_text(encoding="utf-8")
    assert "api.get('/jobs/portal-summary'" in hook_source
    assert "useJobsPortalSummary" in route_source
    assert "/employers/my-jobs" not in route_source
