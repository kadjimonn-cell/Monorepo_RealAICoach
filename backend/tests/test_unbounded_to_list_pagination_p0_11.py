from pathlib import Path
import re


TARGET_FILES = [
    "/app/backend/routes/admin_payment_analytics.py",
    "/app/backend/routes/referrals.py",
    "/app/backend/routes/payments_admin_maintenance_routes.py",
    "/app/backend/utils/access_governance.py",
    "/app/backend/routes/payments.py",
    "/app/backend/routes/support.py",
    "/app/backend/scheduler_jobs.py",
    "/app/backend/routes/ab_testing.py",
    "/app/backend/routes/advanced_admin.py",
]


def test_targeted_hotspots_no_longer_use_to_list_50000() -> None:
    for file_path in TARGET_FILES:
        source = Path(file_path).read_text(encoding="utf-8")
        assert "to_list(50000)" not in source, f"Found unbounded query in {file_path}"


def test_targeted_hotspots_use_pagination_helper() -> None:
    helper_marker = "iter_find_paginated"
    for file_path in TARGET_FILES:
        source = Path(file_path).read_text(encoding="utf-8")
        assert helper_marker in source, f"Pagination helper missing in {file_path}"


def test_targeted_hotspots_do_not_use_large_to_list_batches() -> None:
    large_batch_pattern = re.compile(r"to_list\(\s*(\d+)\s*\)")
    threshold = 5000
    for file_path in TARGET_FILES:
        source = Path(file_path).read_text(encoding="utf-8")
        matches = [
            int(m.group(1))
            for m in large_batch_pattern.finditer(source)
            if int(m.group(1)) >= threshold
        ]
        assert not matches, f"Found large to_list batch sizes {matches} in {file_path}"
