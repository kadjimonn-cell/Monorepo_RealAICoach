"""Admin/reporting helpers for ID verification routes."""

from __future__ import annotations

import csv
import io
from datetime import datetime, timezone

from reportlab.lib import colors as rl_colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle


def manual_review_violation_query() -> dict:
    return {
        "$and": [
            {"status": "verified"},
            {"workflow_state": "APPROVED"},
            {"$or": [{"admin_reviewed_by": {"$exists": False}}, {"admin_reviewed_by": None}]},
        ]
    }


def _facet_count(data: dict, facet_key: str) -> int:
    bucket = data.get(facet_key)
    if not isinstance(bucket, list) or not bucket:
        return 0
    first = bucket[0]
    if not isinstance(first, dict):
        return 0
    try:
        return int(first.get("count") or 0)
    except Exception:
        return 0


async def build_admin_stats_payload(db) -> dict:
    pipeline = [{"$group": {"_id": "$status", "count": {"$sum": 1}}}]
    result = await db.afrikpay_kyc.aggregate(pipeline).to_list(10)
    stats = {r["_id"]: r["count"] for r in result}
    total = sum(stats.values())
    return {
        "total": total,
        "pending_review": stats.get("pending_review", 0),
        "verified": stats.get("verified", 0),
        "rejected": stats.get("rejected", 0),
        "submitted": stats.get("submitted", 0),
        "banned": stats.get("banned", 0),
    }


async def build_admin_dashboard_payload(db) -> dict:
    pipeline = [
        {
            "$facet": {
                "total": [{"$count": "count"}],
                "by_status": [{"$group": {"_id": "$status", "count": {"$sum": 1}}}],
                "by_country": [{"$group": {"_id": "$nationality", "count": {"$sum": 1}}}],
                "recent": [
                    {"$sort": {"submitted_at": -1}},
                    {"$limit": 50},
                    {
                        "$project": {
                            "_id": 0,
                            "kyc_id": 1,
                            "user_id": 1,
                            "full_name": 1,
                            "nationality": 1,
                            "status": 1,
                            "tier": 1,
                            "level": 1,
                            "submitted_at": 1,
                            "rejection_reason": 1,
                            "retry_available_date": 1,
                            "auto_verification": 1,
                            "ai_verification": 1,
                            "combined_score": 1,
                            "documents": 1,
                            "more_info_needed": 1,
                            "more_info_notes": 1,
                        }
                    },
                ],
            }
        }
    ]
    result = await db.afrikpay_kyc.aggregate(pipeline).to_list(1)
    data = result[0] if result else {}
    total = _facet_count(data, "total")
    status_map = {s["_id"]: s["count"] for s in data.get("by_status", [])}
    approved = status_map.get("verified", 0)
    rejected = status_map.get("rejected", 0)
    pending = status_map.get("pending_review", 0)
    country_breakdown = sorted(data.get("by_country", []), key=lambda x: -x["count"])
    recent_submissions = []
    for rec in data.get("recent", []):
        docs = rec.get("documents") or []
        doc_types = {str(d.get("type") or "").lower() for d in docs}
        uid = rec.get("user_id")
        recent_submissions.append(
            {
                **rec,
                "documents_count": len(docs),
                "document_types": sorted([d for d in doc_types if d]),
                "document_front_url": f"/api/id-checker/admin/document-file/{uid}/id_front" if "id_front" in doc_types else None,
                "document_back_url": f"/api/id-checker/admin/document-file/{uid}/id_back" if "id_back" in doc_types else None,
                "selfie_url": f"/api/id-checker/admin/document-file/{uid}/selfie" if "selfie" in doc_types else None,
                "ai_confidence": rec.get("ai_verification", {}).get("confidence_score") if rec.get("ai_verification") else None,
                "ai_risk_level": rec.get("ai_verification", {}).get("risk_level") if rec.get("ai_verification") else None,
            }
        )
    return {
        "overview": {
            "total_submissions": total,
            "approved": approved,
            "rejected": rejected,
            "pending_review": pending,
            "approval_rate": round((approved / total * 100), 1) if total else 0,
            "rejection_rate": round((rejected / total * 100), 1) if total else 0,
        },
        "country_breakdown": country_breakdown,
        "recent_submissions": recent_submissions,
    }


async def build_admin_super_dashboard_payload(db) -> dict:
    total_wallets = await db.afrikpay_wallets.count_documents({})
    active_wallets = await db.afrikpay_wallets.count_documents({"balance": {"$gt": 0}})
    bal = await db.afrikpay_wallets.aggregate([{"$group": {"_id": None, "total": {"$sum": "$balance"}}}]).to_list(1)
    total_balance = round(bal[0]["total"], 2) if bal else 0
    total_txs = await db.afrikpay_transactions.count_documents({})
    vol = await db.afrikpay_transactions.aggregate([
        {"$match": {"status": {"$in": ["completed", "pending_settlement"]}}},
        {"$group": {"_id": None, "total": {"$sum": "$amount"}}},
    ]).to_list(1)
    total_volume = round(vol[0]["total"], 2) if vol else 0
    type_breakdown = await db.afrikpay_transactions.aggregate([
        {"$group": {"_id": "$type", "count": {"$sum": 1}, "volume": {"$sum": "$amount"}}},
        {"$sort": {"count": -1}},
    ]).to_list(20)
    total_loans = await db.afrikpay_loans.count_documents({})
    active_loans = await db.afrikpay_loans.count_documents({"status": "active"})
    defaulted_loans = await db.afrikpay_loans.count_documents({"status": "defaulted"})
    lv = await db.afrikpay_loans.aggregate([{"$group": {"_id": None, "disbursed": {"$sum": "$amount"}, "collected": {"$sum": "$repaid_amount"}}}]).to_list(1)
    total_merchants = await db.afrikpay_merchants.count_documents({})
    mr = await db.afrikpay_merchants.aggregate([{"$group": {"_id": None, "total": {"$sum": "$total_revenue"}}}]).to_list(1)
    total_remittances = await db.afrikpay_remittances.count_documents({})
    rv = await db.afrikpay_remittances.aggregate([{"$group": {"_id": None, "total": {"$sum": "$send_amount"}, "fees": {"$sum": "$fee"}}}]).to_list(1)
    fraud_flagged = await db.afrikpay_fraud_flags.count_documents({})
    fraud_pending = await db.afrikpay_fraud_flags.count_documents({"status": "pending_review"})
    aml_flags = await db.afrikpay_aml_flags.count_documents({})
    aml_pending = await db.afrikpay_aml_flags.count_documents({"status": "pending_review"})
    kyc_total = await db.afrikpay_kyc.count_documents({})
    kyc_verified = await db.afrikpay_kyc.count_documents({"status": "verified"})
    ledger_blocks = await db.afrikpay_ledger.count_documents({})
    return {
        "wallets": {"total": total_wallets, "active": active_wallets, "total_balance": total_balance},
        "transactions": {
            "total": total_txs,
            "total_volume": total_volume,
            "type_breakdown": [{"type": t["_id"], "count": t["count"], "volume": round(t["volume"], 2)} for t in type_breakdown],
        },
        "loans": {
            "total": total_loans,
            "active": active_loans,
            "defaulted": defaulted_loans,
            "default_rate": round(defaulted_loans / max(total_loans, 1) * 100, 1),
            "total_disbursed": round(lv[0]["disbursed"], 2) if lv else 0,
            "total_collected": round(lv[0]["collected"], 2) if lv else 0,
        },
        "merchants": {"total": total_merchants, "total_revenue": round(mr[0]["total"], 2) if mr else 0},
        "remittances": {"total": total_remittances, "total_volume": round(rv[0]["total"], 2) if rv else 0, "total_fees": round(rv[0]["fees"], 2) if rv else 0},
        "fraud": {"total_flagged": fraud_flagged, "pending_review": fraud_pending},
        "aml": {"total_flags": aml_flags, "pending_review": aml_pending},
        "kyc": {"total_submissions": kyc_total, "verified": kyc_verified},
        "ledger": {"total_blocks": ledger_blocks},
    }


async def render_idv_export_csv(*, kyc_find_many) -> tuple[str, str]:
    records = await kyc_find_many({}, {"_id": 0}, sort=("submitted_at", -1), limit=1000)
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["KYC ID", "User ID", "Full Name", "Nationality", "ID Type", "Status", "Tier", "Level", "Score", "Submitted At", "Verified At", "Rejection Reason", "Retry Available"])
    for r in records:
        writer.writerow([
            r.get("kyc_id", ""),
            r.get("user_id", ""),
            r.get("full_name", ""),
            r.get("nationality", ""),
            r.get("id_type", ""),
            r.get("status", ""),
            r.get("tier", ""),
            r.get("level", ""),
            r.get("auto_verification", {}).get("score", ""),
            r.get("submitted_at", "")[:19] if r.get("submitted_at") else "",
            r.get("verified_at", "")[:19] if r.get("verified_at") else "",
            r.get("rejection_reason", ""),
            r.get("retry_available_date", "")[:10] if r.get("retry_available_date") else "",
        ])
    filename = f"id_checker_export_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M')}.csv"
    return filename, output.getvalue()


async def render_idv_export_pdf(*, db, enforce_pdf, build_pdf_filename):
    from services.pdf_v15_theme import PALETTE, draw_callout_card, draw_kv_card, draw_page_chrome

    pipeline = [{"$facet": {"total": [{"$count": "count"}], "by_status": [{"$group": {"_id": "$status", "count": {"$sum": 1}}}], "records": [{"$sort": {"submitted_at": -1}}, {"$limit": 100}, {"$project": {"_id": 0, "kyc_id": 1, "user_id": 1, "full_name": 1, "nationality": 1, "status": 1, "submitted_at": 1, "rejection_reason": 1}}]}}]
    result = await db.afrikpay_kyc.aggregate(pipeline).to_list(1)
    data = result[0] if result else {}
    total = _facet_count(data, "total")
    status_map = {s["_id"]: s["count"] for s in data.get("by_status", [])}
    records = data.get("records", [])
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=landscape(A4), topMargin=118, bottomMargin=30)
    styles = getSampleStyleSheet()
    elements = [Paragraph("RealAICoach - ID Checker Report", styles["Title"]), Paragraph(f"Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}", styles["Normal"]), Spacer(1, 20)]
    approval_rate = round(status_map.get("verified", 0) / total * 100, 1) if total else 0.0
    summary_data = [["Total Submissions", "Approved", "Rejected", "Pending Review", "Approval Rate"], [str(total), str(status_map.get("verified", 0)), str(status_map.get("rejected", 0)), str(status_map.get("pending_review", 0)), f"{approval_rate}%"]]
    summary_table = Table(summary_data, colWidths=[120, 100, 100, 120, 100])
    summary_table.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), rl_colors.HexColor("#1E3A5F")), ("TEXTCOLOR", (0, 0), (-1, 0), rl_colors.whitesmoke), ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"), ("FONTSIZE", (0, 0), (-1, -1), 9), ("GRID", (0, 0), (-1, -1), 0.5, rl_colors.grey), ("ALIGN", (0, 0), (-1, -1), "CENTER")]))
    elements.extend([summary_table, Spacer(1, 20), Paragraph("Recent Submissions (Last 100)", styles["Heading2"]), Spacer(1, 10)])
    table_data = [["KYC ID", "User ID", "Name", "Country", "Status", "Date", "Rejection Reason"]]
    for r in records:
        table_data.append([str(r.get("kyc_id", ""))[:15], str(r.get("user_id", ""))[-8:], str(r.get("full_name", ""))[:20], str(r.get("nationality", "")), str(r.get("status", "")), str(r.get("submitted_at", ""))[:10], str(r.get("rejection_reason", ""))[:30]])
    t = Table(table_data, colWidths=[100, 70, 120, 60, 80, 80, 180])
    t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), rl_colors.HexColor("#1E3A5F")), ("TEXTCOLOR", (0, 0), (-1, 0), rl_colors.whitesmoke), ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"), ("FONTSIZE", (0, 0), (-1, -1), 8), ("GRID", (0, 0), (-1, -1), 0.5, rl_colors.grey), ("ROWBACKGROUNDS", (0, 1), (-1, -1), [rl_colors.white, rl_colors.HexColor("#F0F4F8")]), ("VALIGN", (0, 0), (-1, -1), "MIDDLE")]))
    elements.append(t)

    def _draw_pdf_v15_chrome(canv, build_doc):
        y = draw_page_chrome(canv, width=float(build_doc.pagesize[0]), height=float(build_doc.pagesize[1]), margin_x=30, page_no=canv.getPageNumber(), title="ID Checker Governance Report", subtitle="Enterprise verification operations dashboard export", right_primary=f"Records: {total}", right_secondary=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"), badge_text="KYC / ID CHECKER COMPLIANCE", badge_status="INFO", footer_text="RealAICoach ID Checker • Enterprise profile")
        if canv.getPageNumber() == 1:
            card_y = draw_kv_card(canv, margin_x=30, content_w=250, y=y - 8, title="Summary", rows=[("Approved", str(status_map.get("verified", 0))), ("Rejected", str(status_map.get("rejected", 0))), ("Pending", str(status_map.get("pending_review", 0)))], tone=PALETTE["primary"])
            draw_callout_card(canv, margin_x=290, content_w=455, y=card_y, title="Approval Health", subtitle="ID Checker throughput signal", detail=f"Approval rate: {approval_rate}%. Keep above 75% for stable throughput and low review backlog.", status="PASS" if approval_rate >= 75 else "WARNING")

    doc.build(elements, onFirstPage=_draw_pdf_v15_chrome, onLaterPages=_draw_pdf_v15_chrome)
    pdf_bytes = enforce_pdf(buf.getvalue(), "id_checker_report")
    filename = build_pdf_filename("id-checker-report", datetime.now(timezone.utc).strftime('%Y%m%d_%H%M'))
    return filename, pdf_bytes