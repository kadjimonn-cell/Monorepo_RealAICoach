from pathlib import Path


REFERRALS_PATH = Path('/app/backend/routes/referrals.py')
SUPPORT_PATH = Path('/app/backend/routes/support.py')


def test_referrals_admin_lists_accept_page_and_page_size() -> None:
    source = REFERRALS_PATH.read_text(encoding='utf-8')
    assert 'async def admin_list_challenges(' in source
    assert 'page: int = Query(1, ge=1)' in source
    assert 'page_size: int = Query(20, ge=1, le=100)' in source
    assert 'async def admin_fraud_alerts(' in source
    assert 'page_size: int = Query(25, ge=1, le=200)' in source


def test_support_admin_lists_accept_page_and_page_size() -> None:
    source = SUPPORT_PATH.read_text(encoding='utf-8')
    assert 'async def admin_list_faqs(' in source
    assert 'page_size: int = Query(25, ge=1, le=200)' in source
    assert 'async def get_admin_submissions(' in source
    assert 'page_size: int = Query(50, ge=1, le=200)' in source


def test_pagination_envelope_keys_present() -> None:
    referrals_source = REFERRALS_PATH.read_text(encoding='utf-8')
    support_source = SUPPORT_PATH.read_text(encoding='utf-8')
    for marker in ['"data":', '"total_count":', '"page":', '"page_size":']:
        assert marker in referrals_source
        assert marker in support_source
