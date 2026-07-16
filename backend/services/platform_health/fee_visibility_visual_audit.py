import glob
import io
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

import numpy as np
import requests
from PIL import Image


BASELINE_REFERENCE_IMAGES: List[Dict[str, str]] = [
    {
        "key": "preview_mobile_reference_1",
        "label": "In-App Preview Mobile Reference 1",
        "url": "https://customer-assets.emergentagent.com/job_575307e2-6e4d-49f4-9bb7-6f8d6e7bf580/artifacts/r0vhrosl_image.png",
        "target_family": "platform_mobile",
    },
    {
        "key": "preview_mobile_reference_2",
        "label": "In-App Preview Mobile Reference 2",
        "url": "https://customer-assets.emergentagent.com/job_575307e2-6e4d-49f4-9bb7-6f8d6e7bf580/artifacts/7zgwsxsd_image.png",
        "target_family": "platform_mobile",
    },
    {
        "key": "preview_mobile_reference_3",
        "label": "In-App Preview Mobile Reference 3",
        "url": "https://customer-assets.emergentagent.com/job_575307e2-6e4d-49f4-9bb7-6f8d6e7bf580/artifacts/eogcmbmh_image.png",
        "target_family": "platform_mobile",
    },
    {
        "key": "preview_mobile_reference_4",
        "label": "In-App Preview Mobile Reference 4",
        "url": "https://customer-assets.emergentagent.com/job_575307e2-6e4d-49f4-9bb7-6f8d6e7bf580/artifacts/gsft95y3_image.png",
        "target_family": "platform_mobile",
    },
    {
        "key": "preview_mobile_reference_5",
        "label": "In-App Preview Mobile Reference 5",
        "url": "https://customer-assets.emergentagent.com/job_575307e2-6e4d-49f4-9bb7-6f8d6e7bf580/artifacts/rsl38xmz_image.png",
        "target_family": "platform_mobile",
    },
]


TARGET_SCREENSHOT_PATTERNS: Dict[str, List[str]] = {
    "platform_mobile": [
        "/root/.emergent/automation_output/**/*preview-mobile*.jpeg",
        "/root/.emergent/automation_output/**/*preview-mobile*.png",
        "/root/.emergent/automation_output/**/*responsive-mobile*.jpeg",
        "/root/.emergent/automation_output/**/*responsive-mobile*.png",
        "/root/.emergent/automation_output/**/*mobile-money*.jpeg",
        "/root/.emergent/automation_output/**/*mobile-money*.png",
        "/root/.emergent/automation_output/**/*plans*.jpeg",
        "/root/.emergent/automation_output/**/*plans*.png",
        "/tmp/*preview-mobile*.png",
        "/tmp/*mobile*.png",
        "/tmp/*plans*.png",
        "/tmp/*mobile*.jpeg",
    ],
    "mobile_money": [
        "/root/.emergent/automation_output/**/*mobile_money*admin*.jpeg",
        "/root/.emergent/automation_output/**/*mobile_money*mobile*.jpeg",
        "/root/.emergent/automation_output/**/*mobile_money*.jpeg",
    ],
}


def _download_image_bytes(url: str) -> bytes:
    response = requests.get(url, timeout=25)
    if response.status_code != 200:
        raise RuntimeError(f"baseline_download_failed:{response.status_code}")
    return response.content


def _latest_candidate_paths(family: str) -> List[Path]:
    patterns = TARGET_SCREENSHOT_PATTERNS.get(family, [])
    candidates: List[Path] = []
    for pattern in patterns:
        for match in glob.glob(pattern, recursive=True):
            p = Path(match)
            if p.is_file():
                candidates.append(p)
    unique = {str(path.resolve()): path for path in candidates}
    return sorted(unique.values(), key=lambda p: p.stat().st_mtime, reverse=True)


def _open_image_bytes(payload: bytes) -> Image.Image:
    return Image.open(io.BytesIO(payload)).convert("RGB")


def _open_image_path(path: Path) -> Image.Image:
    return Image.open(path).convert("RGB")


def _diff_ratio(reference: Image.Image, candidate: Image.Image) -> float:
    target_size = reference.size
    ref = reference.resize(target_size).convert("RGB")
    cand = candidate.resize(target_size).convert("RGB")

    ref_arr = np.asarray(ref, dtype=np.uint8)
    cand_arr = np.asarray(cand, dtype=np.uint8)

    # Ignore red annotation overlays from user-provided reference screenshots.
    red_mask = (
        (ref_arr[:, :, 0] >= 170)
        & (ref_arr[:, :, 1] <= 110)
        & (ref_arr[:, :, 2] <= 110)
        & ((ref_arr[:, :, 0].astype(np.int16) - ref_arr[:, :, 1].astype(np.int16)) >= 50)
        & ((ref_arr[:, :, 0].astype(np.int16) - ref_arr[:, :, 2].astype(np.int16)) >= 50)
    )
    ref_arr = ref_arr.copy()
    ref_arr[red_mask] = cand_arr[red_mask]

    abs_diff = np.abs(ref_arr.astype(np.int16) - cand_arr.astype(np.int16))
    ratio = float(abs_diff.mean()) / 255.0
    return round(max(0.0, min(1.0, ratio)), 6)


def build_fee_visibility_visual_audit(
    *,
    triggered_by: str,
    actor_id: str,
    actor_email: str,
    diff_threshold: float = 0.12,
) -> Dict[str, Any]:
    now_iso = datetime.now(timezone.utc).isoformat()
    comparisons: List[Dict[str, Any]] = []
    pass_count = 0
    fail_count = 0
    missing_count = 0
    drift_count = 0

    for baseline in BASELINE_REFERENCE_IMAGES:
        family = baseline.get("target_family", "payment")
        candidates = _latest_candidate_paths(family)
        candidate_paths = [str(path) for path in candidates[:8]]
        record: Dict[str, Any] = {
            "baseline_key": baseline.get("key"),
            "label": baseline.get("label"),
            "baseline_url": baseline.get("url"),
            "target_family": family,
            "candidate_paths": candidate_paths,
        }

        if not candidates:
            record.update({
                "status": "missing",
                "reason": "no_runtime_screenshots",
                "best_diff_ratio": None,
                "best_candidate_path": "",
            })
            missing_count += 1
            comparisons.append(record)
            continue

        try:
            baseline_image = _open_image_bytes(_download_image_bytes(str(baseline.get("url") or "")))
        except Exception as exc:
            record.update({
                "status": "missing",
                "reason": f"baseline_unavailable:{str(exc)[:120]}",
                "best_diff_ratio": None,
                "best_candidate_path": "",
            })
            missing_count += 1
            comparisons.append(record)
            continue

        best_path = ""
        best_ratio = 1.0
        for candidate_path in candidates[:8]:
            try:
                candidate_image = _open_image_path(candidate_path)
                ratio = _diff_ratio(baseline_image, candidate_image)
                if ratio < best_ratio:
                    best_ratio = ratio
                    best_path = str(candidate_path)
            except Exception:
                continue

        if not best_path:
            record.update({
                "status": "missing",
                "reason": "candidate_read_failed",
                "best_diff_ratio": None,
                "best_candidate_path": "",
            })
            missing_count += 1
            comparisons.append(record)
            continue

        passed = bool(best_ratio <= float(diff_threshold))
        status = "pass" if passed else "fail"
        if passed:
            pass_count += 1
        else:
            fail_count += 1
            drift_count += 1

        record.update({
            "status": status,
            "best_diff_ratio": round(float(best_ratio), 6),
            "best_candidate_path": best_path,
            "score_percent": round(max(0.0, (1.0 - float(best_ratio)) * 100.0), 2),
            "reason": "within_threshold" if passed else "pixel_drift_detected",
        })
        comparisons.append(record)

    total = len(comparisons)
    overall_status = "pass" if total > 0 and fail_count == 0 and missing_count == 0 else "fail"
    severity = "low" if overall_status == "pass" else "medium" if drift_count <= 1 else "high"

    return {
        "audit_id": f"fee_visibility_visual_audit_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}",
        "created_at": now_iso,
        "created_by": actor_id,
        "created_by_email": actor_email,
        "triggered_by": str(triggered_by or "manual:admin")[:120],
        "overall_status": overall_status,
        "severity": severity,
        "diff_threshold": float(diff_threshold),
        "baseline_count": total,
        "pass_count": pass_count,
        "fail_count": fail_count,
        "missing_count": missing_count,
        "drift_count": drift_count,
        "comparisons": comparisons,
        "recommendation": "Investigate fee-visibility UI drift before release." if overall_status != "pass" else "No drift detected against current baseline pack.",
    }
