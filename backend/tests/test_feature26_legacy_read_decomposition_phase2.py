from pathlib import Path


def _read(path: str) -> str:
    return Path(path).read_text(encoding="utf-8")


def test_jobs_routes_import_phase2_pipeline_read_service() -> None:
    source = _read('/app/backend/routes/jobs.py')
    assert 'from .jobs_pipeline_read_service import (' in source


def test_jobs_routes_delegate_advanced_employer_read_surfaces_to_phase2_service() -> None:
    source = _read('/app/backend/routes/jobs.py')
    expected = [
        'return await get_employer_pipeline_board_read(',
        'return await get_employer_pipeline_timeline_read(',
        'return await list_employer_offers_read(',
        'return await get_employer_sla_alerts_read(',
        'return await get_employer_sla_auto_triggers_read(',
        'return await get_employer_kpi_header_read(',
        'return await get_recruiter_copilot_suggestions_read(',
        'return await get_interview_scorecards_read(',
        'return await suggest_auto_scheduler_slots_read(',
        'return await get_communication_sequence_read(',
        'return await get_employer_hiring_forecast_read(',
        'return await get_talent_rediscovery_candidates_read(',
        'return await export_pipeline_audit_csv_read(',
        'return await export_pipeline_audit_pdf_read(',
        'return await get_pipeline_audit_download_history_read(',
    ]
    for marker in expected:
        assert marker in source


def test_phase2_pipeline_service_module_exists_with_core_handlers() -> None:
    service = _read('/app/backend/routes/jobs_pipeline_read_service.py')
    assert 'async def get_employer_pipeline_board_read' in service
    assert 'async def get_employer_pipeline_timeline_read' in service
    assert 'async def get_employer_kpi_header_read' in service
    assert 'async def get_employer_hiring_forecast_read' in service
    assert 'async def export_pipeline_audit_csv_read' in service
    assert 'async def export_pipeline_audit_pdf_read' in service
