from pathlib import Path


def test_hiring_v2_write_adapter_routes_present() -> None:
    source = Path('/app/backend/routes/hiring_v2.py').read_text(encoding='utf-8')
    for route in [
        '@router.post("/employer/offers/build")',
        '@router.post("/employer/offers/{offer_id}/submit-approval")',
        '@router.post("/employer/offers/{offer_id}/approve")',
        '@router.post("/employer/offers/{offer_id}/send")',
        '@router.post("/employer/pipeline/bulk-action")',
        '@router.post("/employer/pipeline/{application_id}/copilot-execute")',
    ]:
        assert route in source


def test_hiring_v2_premium_commercial_routes_present() -> None:
    source = Path('/app/backend/routes/hiring_v2.py').read_text(encoding='utf-8')
    for route in [
        '@router.post("/candidate/priority-apply/{application_id}")',
        '@router.post("/candidate/boost-profile")',
        '@router.get("/employer/shortlist/explainability")',
        '@router.get("/employer/premium-analytics/events")',
    ]:
        assert route in source
