from pathlib import Path


def test_hiring_v2_candidate_write_endpoints_present() -> None:
    source = Path('/app/backend/routes/hiring_v2.py').read_text(encoding='utf-8')
    for route in [
        '@router.post("/candidate/apply")',
        '@router.post("/candidate/save/{job_id}")',
        '@router.post("/candidate/profile/update")',
        '@router.post("/candidate/resume/upload")',
        '@router.get("/candidate/recommendations")',
    ]:
        assert route in source


def test_apply_jobs_tab_uses_hiring_v2_candidate_writes() -> None:
    source = Path('/app/frontend/src/components/jobs/ApplyJobsTab.tsx').read_text(encoding='utf-8')
    assert "api.post('/hiring/v2/candidate/apply'" in source
    assert "api.post(`/hiring/v2/candidate/save/${jobId}`)" in source
