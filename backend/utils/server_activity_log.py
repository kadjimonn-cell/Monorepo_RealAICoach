"""Shared activity-log helpers for server routes."""

from __future__ import annotations

import csv
import io
from datetime import datetime, timezone

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from services.pdf_v15_theme import draw_page_chrome
from utils.pdf_v15_export import enforce_pdf_v15_enterprise
from utils.pdf_v15_filename import build_pdf_v15_filename


def build_security_event_query(*, event_type: str = None, risk_level: str = None, user_id: str = None, date_from: str = None, date_to: str = None) -> dict:
    query: dict = {}
    if event_type:
        query["event_type"] = event_type
    if risk_level:
        query["risk_level"] = risk_level
    if user_id:
        query["user_id"] = user_id
    if date_from:
        query.setdefault("timestamp", {})["$gte"] = date_from
    if date_to:
        query.setdefault("timestamp", {})["$lte"] = date_to
    return query


async def _fetch_user_map(db, user_ids: list[str], include_name: bool = True) -> dict:
    if not user_ids:
        return {}
    projection = {"_id": 0, "user_id": 1, "email": 1}
    if include_name:
        projection["name"] = 1
    user_docs = await db.users.find({"user_id": {"$in": user_ids}}, projection).to_list(500)
    return {
        row["user_id"]: {"email": row.get("email", ""), "name": row.get("name", "")}
        for row in user_docs
    }


async def fetch_admin_activity_log_payload(
    db,
    *,
    page: int,
    per_page: int,
    event_type: str = None,
    risk_level: str = None,
    user_id: str = None,
    date_from: str = None,
    date_to: str = None,
) -> dict:
    query = build_security_event_query(
        event_type=event_type,
        risk_level=risk_level,
        user_id=user_id,
        date_from=date_from,
        date_to=date_to,
    )
    total = await db.security_events.count_documents(query)
    skip = (page - 1) * per_page
    events = (
        await db.security_events.find(query, {"_id": 0})
        .sort("timestamp", -1)
        .skip(skip)
        .limit(per_page)
        .to_list(per_page)
    )
    user_map = await _fetch_user_map(db, list({e.get("user_id") for e in events if e.get("user_id")}))
    for event in events:
        info = user_map.get(event.get("user_id", ""), {})
        event["user_email"] = info.get("email", "")
        event["user_name"] = info.get("name", "")
    event_types = await db.security_events.distinct("event_type")
    risk_levels = await db.security_events.distinct("risk_level")
    return {
        "events": events,
        "total": total,
        "page": page,
        "per_page": per_page,
        "pages": (total + per_page - 1) // per_page,
        "filters": {"event_types": sorted(event_types), "risk_levels": sorted(risk_levels)},
    }


async def render_activity_log_csv(db, *, event_type: str = None, risk_level: str = None, user_id: str = None, date_from: str = None, date_to: str = None) -> tuple[str, bytes]:
    query = build_security_event_query(
        event_type=event_type,
        risk_level=risk_level,
        user_id=user_id,
        date_from=date_from,
        date_to=date_to,
    )
    events = await db.security_events.find(query, {"_id": 0}).sort("timestamp", -1).to_list(10000)
    user_map = await _fetch_user_map(db, list({e.get("user_id") for e in events if e.get("user_id")}), include_name=False)

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Timestamp", "Event Type", "Risk Level", "User ID", "User Email", "IP Address", "Details"])
    for event in events:
        writer.writerow(
            [
                event.get("timestamp", ""),
                event.get("event_type", ""),
                event.get("risk_level", ""),
                event.get("user_id", ""),
                user_map.get(event.get("user_id", ""), {}).get("email", ""),
                event.get("ip_address", ""),
                str(event.get("details", {})),
            ]
        )
    filename = f"activity-log-{datetime.now(timezone.utc).strftime('%Y%m%d')}.csv"
    return filename, output.getvalue().encode("utf-8")


async def render_activity_log_pdf(db, *, event_type: str = None, risk_level: str = None, user_id: str = None, date_from: str = None, date_to: str = None) -> tuple[str, bytes]:
    query = build_security_event_query(
        event_type=event_type,
        risk_level=risk_level,
        user_id=user_id,
        date_from=date_from,
        date_to=date_to,
    )
    events = await db.security_events.find(query, {"_id": 0}).sort("timestamp", -1).to_list(5000)
    user_map = await _fetch_user_map(db, list({e.get("user_id") for e in events if e.get("user_id")}))

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=landscape(A4), leftMargin=30, rightMargin=30, topMargin=110, bottomMargin=30)
    styles = getSampleStyleSheet()
    story = [
        Paragraph(
            f"<b>Security Activity Log</b> — Exported {datetime.now(timezone.utc).strftime('%b %d, %Y %H:%M UTC')}",
            styles["Title"],
        ),
        Paragraph(f"Total events: {len(events)}", styles["Normal"]),
        Spacer(1, 12),
    ]
    rows = [["Time", "Event", "Risk", "User", "IP"]]
    for event in events[:2000]:
        ts = str(event.get("timestamp", ""))[:19].replace("T", " ")
        uid = event.get("user_id") or ""
        user_info = user_map.get(uid, {})
        rows.append(
            [
                ts,
                event.get("event_type", "").replace("_", " ").title(),
                event.get("risk_level", ""),
                user_info.get("email") or uid[:16] if uid else "—",
                event.get("ip_address", "—") or "—",
            ]
        )
    table = Table(rows, colWidths=[120, 140, 60, 180, 110], repeatRows=1)
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1e293b")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTSIZE", (0, 0), (-1, 0), 9),
                ("FONTSIZE", (0, 1), (-1, -1), 8),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#e2e8f0")),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f8fafc")]),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    story.append(table)

    def _draw_pdf_v15_chrome(canv, build_doc):
        draw_page_chrome(
            canv,
            width=float(build_doc.pagesize[0]),
            height=float(build_doc.pagesize[1]),
            margin_x=30,
            page_no=canv.getPageNumber(),
            title="Security Activity Log",
            subtitle="Enterprise security telemetry export",
            right_primary=f"Events: {len(events)}",
            right_secondary=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
            badge_text="SECURITY OPERATIONS AUDIT",
            badge_status="INFO",
            footer_text="RealAICoach Security Center • Enterprise profile",
        )

    doc.build(story, onFirstPage=_draw_pdf_v15_chrome, onLaterPages=_draw_pdf_v15_chrome)
    filename = build_pdf_v15_filename("activity-log", datetime.now(timezone.utc).strftime("%Y%m%d"))
    return filename, enforce_pdf_v15_enterprise(buf.getvalue(), "security_activity_log_export")