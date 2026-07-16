"""Employer Console audit export helpers."""

from __future__ import annotations

import csv
import hashlib
import hmac
import io
import os
from datetime import datetime, timezone
from datetime import timedelta
from typing import Any, Dict, List, Optional, Tuple

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from .db import db
from utils.pdf_v15_export import enforce_pdf_v15_enterprise

_SIGNING_SECRET = str(os.environ.get("JWT_SECRET") or "").strip()
if len(_SIGNING_SECRET) < 32:
    raise RuntimeError("JWT_SECRET missing/weak: employer export signing disabled")


def _normalize_timestamp(value: Any) -> str:
    raw = str(value or "").strip()
    if not raw:
        return datetime.now(timezone.utc).isoformat()
    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).isoformat()
    except Exception:
        return raw


def _compact_text(value: Any, fallback: str) -> str:
    text = str(value or "").strip()
    return text or fallback


def _parse_dt(value: Optional[str]) -> Optional[datetime]:
    raw = str(value or "").strip()
    if not raw:
        return None
    if len(raw) == 10:
        raw = f"{raw}T00:00:00+00:00"
    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return None


def resolve_audit_date_range(
    range_key: str = "30d",
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
) -> Tuple[Optional[datetime], Optional[datetime], str]:
    now = datetime.now(timezone.utc)
    normalized = str(range_key or "30d").strip().lower()

    start_dt = _parse_dt(start_date)
    end_dt = _parse_dt(end_date)
    if end_dt and len(str(end_date or "").strip()) == 10:
        end_dt = end_dt + timedelta(days=1) - timedelta(seconds=1)

    if start_dt or end_dt:
        return start_dt, end_dt, "Custom Range"
    if normalized == "90d":
        return now - timedelta(days=90), now, "Last 90 days"
    if normalized in {"all", "all_time"}:
        return None, None, "All time"
    return now - timedelta(days=30), now, "Last 30 days"


def filter_audit_rows_by_range(
    rows: List[Dict[str, Any]],
    start_dt: Optional[datetime],
    end_dt: Optional[datetime],
) -> List[Dict[str, Any]]:
    if not start_dt and not end_dt:
        return rows
    filtered: List[Dict[str, Any]] = []
    for row in rows:
        row_dt = _parse_dt(str(row.get("timestamp") or ""))
        if start_dt and (not row_dt or row_dt < start_dt):
            continue
        if end_dt and row_dt and row_dt > end_dt:
            continue
        filtered.append(row)
    return filtered


def build_audit_download_signature(
    *,
    application_id: str,
    exporter_user_id: str,
    export_format: str,
    range_label: str,
    row_count: int,
    created_at: str,
) -> Dict[str, str]:
    signature_id = hashlib.sha1(
        f"{application_id}:{exporter_user_id}:{created_at}:{export_format}".encode("utf-8")
    ).hexdigest()[:16]
    payload = "|".join(
        [application_id, exporter_user_id, export_format, range_label, str(row_count), created_at, signature_id]
    )
    signature = hmac.new(
        _SIGNING_SECRET.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256
    ).hexdigest()
    return {"signature_id": signature_id, "signature": signature}


async def collect_application_audit_rows(application_id: str) -> List[Dict[str, Any]]:
    base_events = await db.job_application_timeline_events.find(
        {"application_id": application_id},
        {"_id": 0},
    ).sort("created_at", -1).to_list(500)

    interviews = await db.interview_bookings.find(
        {"application_id": application_id},
        {
            "_id": 0,
            "interview_id": 1,
            "status": 1,
            "interview_type": 1,
            "scheduled_start": 1,
            "scheduled_end": 1,
            "timezone": 1,
            "candidate_name": 1,
            "employer_name": 1,
            "created_at": 1,
            "updated_at": 1,
        },
    ).sort("scheduled_start", -1).to_list(100)
    interview_ids = [row.get("interview_id") for row in interviews if row.get("interview_id")]
    interview_activity = await db.interview_activity_log.find(
        {"interview_id": {"$in": interview_ids}},
        {"_id": 0},
    ).sort("timestamp", -1).to_list(400) if interview_ids else []

    offers = await db.employer_offer_letters.find(
        {"application_id": application_id},
        {"_id": 0, "offer_id": 1, "status": 1, "approval_status": 1, "decision": 1, "created_at": 1, "sent_at": 1, "signed_at": 1},
    ).sort("created_at", -1).to_list(100)

    scorecards = await db.interview_scorecards.find(
        {"application_id": application_id},
        {"_id": 0, "scorecard_id": 1, "reviewer_name": 1, "recommendation": 1, "overall_score": 1, "created_at": 1},
    ).sort("created_at", -1).to_list(100)

    sequences = await db.employer_candidate_communication_sequences.find(
        {"application_id": application_id},
        {"_id": 0, "sequence_id": 1, "history": 1},
    ).to_list(20)

    rows: List[Dict[str, Any]] = []
    for event in base_events:
        rows.append(
            {
                "timestamp": _normalize_timestamp(event.get("created_at")),
                "source": "timeline",
                "event_type": _compact_text(event.get("event_type"), "timeline_event"),
                "title": _compact_text(event.get("title"), "Timeline Event"),
                "description": _compact_text(event.get("description"), "No description"),
                "status": _compact_text(event.get("status"), "n/a"),
                "actor_user_id": _compact_text(event.get("actor_user_id"), "system"),
            }
        )

    for interview in interviews:
        rows.append(
            {
                "timestamp": _normalize_timestamp(interview.get("updated_at") or interview.get("created_at") or interview.get("scheduled_start")),
                "source": "interview",
                "event_type": "interview_snapshot",
                "title": f"Interview {str(interview.get('status') or 'scheduled').title()}",
                "description": (
                    f"{str(interview.get('interview_type') or 'interview').title()} interview at "
                    f"{_compact_text(interview.get('scheduled_start'), 'TBD')} {str(interview.get('timezone') or 'UTC').strip()}"
                ),
                "status": _compact_text(interview.get("status"), "scheduled"),
                "actor_user_id": _compact_text(interview.get("employer_name"), "system"),
            }
        )

    for activity in interview_activity:
        rows.append(
            {
                "timestamp": _normalize_timestamp(activity.get("timestamp")),
                "source": "interview-activity",
                "event_type": _compact_text(activity.get("action"), "interview_activity"),
                "title": f"Interview Activity · {_compact_text(activity.get('action'), 'updated').replace('_', ' ').title()}",
                "description": _compact_text(activity.get("details"), "No details"),
                "status": "n/a",
                "actor_user_id": _compact_text(activity.get("actor_id"), "system"),
            }
        )

    for offer in offers:
        rows.append(
            {
                "timestamp": _normalize_timestamp(offer.get("signed_at") or offer.get("sent_at") or offer.get("created_at")),
                "source": "offer",
                "event_type": "offer_update",
                "title": f"Offer {str(offer.get('status') or 'draft').title()}",
                "description": (
                    f"Approval: {_compact_text(offer.get('approval_status'), 'n/a')} · "
                    f"Decision: {_compact_text(offer.get('decision'), 'pending')}"
                ),
                "status": _compact_text(offer.get("status"), "draft"),
                "actor_user_id": "offer_workflow",
            }
        )

    for scorecard in scorecards:
        rows.append(
            {
                "timestamp": _normalize_timestamp(scorecard.get("created_at")),
                "source": "scorecard",
                "event_type": "scorecard_submitted",
                "title": "Structured Interview Scorecard Submitted",
                "description": (
                    f"Reviewer: {_compact_text(scorecard.get('reviewer_name'), 'Unknown')} · "
                    f"Recommendation: {_compact_text(scorecard.get('recommendation'), 'n/a')} · "
                    f"Score: {_compact_text(scorecard.get('overall_score'), 'n/a')}"
                ),
                "status": _compact_text(scorecard.get("recommendation"), "n/a"),
                "actor_user_id": _compact_text(scorecard.get("reviewer_name"), "reviewer"),
            }
        )

    for sequence in sequences:
        for history in sequence.get("history") or []:
            rows.append(
                {
                    "timestamp": _normalize_timestamp(history.get("sent_at")),
                    "source": "sequence",
                    "event_type": _compact_text(history.get("step_key"), "sequence_step"),
                    "title": _compact_text(history.get("title"), "Communication Step Sent"),
                    "description": _compact_text(history.get("message"), "No message"),
                    "status": "sent",
                    "actor_user_id": "communication_sequence",
                }
            )

    rows.sort(key=lambda row: str(row.get("timestamp") or ""), reverse=True)
    return rows


def render_application_audit_csv(rows: List[Dict[str, Any]]) -> bytes:
    out = io.StringIO()
    writer = csv.DictWriter(
        out,
        fieldnames=["timestamp", "source", "event_type", "title", "description", "status", "actor_user_id"],
    )
    writer.writeheader()
    for row in rows:
        writer.writerow({key: row.get(key, "") for key in writer.fieldnames})
    return out.getvalue().encode("utf-8")


def render_application_audit_pdf(
    *,
    rows: List[Dict[str, Any]],
    candidate_name: str,
    job_title: str,
    exported_by: str,
) -> bytes:
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=landscape(A4), leftMargin=20, rightMargin=20, topMargin=20, bottomMargin=20)
    styles = getSampleStyleSheet()
    story = [
        Paragraph("Hiring Action Audit Export", styles["Title"]),
        Spacer(1, 8),
        Paragraph(f"Candidate: {candidate_name}", styles["Normal"]),
        Paragraph(f"Role: {job_title}", styles["Normal"]),
        Paragraph(f"Exported by: {exported_by}", styles["Normal"]),
        Paragraph(f"Generated at: {datetime.now(timezone.utc).isoformat()}", styles["Normal"]),
        Spacer(1, 12),
    ]

    table_rows = [["Timestamp", "Source", "Title", "Description", "Status", "Actor"]]
    for row in rows[:40]:
        table_rows.append(
            [
                str(row.get("timestamp") or "")[:19],
                str(row.get("source") or ""),
                str(row.get("title") or "")[:42],
                str(row.get("description") or "")[:78],
                str(row.get("status") or ""),
                str(row.get("actor_user_id") or "")[:24],
            ]
        )

    table = Table(table_rows, repeatRows=1, colWidths=[110, 78, 150, 270, 70, 100])
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0F172A")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E1")),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.HexColor("#F8FAFC"), colors.white]),
                ("FONTSIZE", (0, 0), (-1, -1), 8),
                ("LEADING", (0, 0), (-1, -1), 10),
            ]
        )
    )
    story.append(table)
    doc.build(story)
    return enforce_pdf_v15_enterprise(buf.getvalue(), "employer_hiring_audit_export")