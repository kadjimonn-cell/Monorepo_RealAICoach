"""
Compliance PDF Generator — creates signed PDF compliance attachments for governance archival.
"""
import io
import hashlib
from datetime import datetime, timezone
from typing import Dict, Any

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib import colors as rl_colors
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle

from services.pdf_v15_theme import PALETTE, draw_page_chrome


def generate_compliance_pdf(report: Dict[str, Any]) -> bytes:
    """Generate a governance-grade PDF compliance report with hash + checkpoint trace."""
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=20 * mm,
        rightMargin=20 * mm,
        topMargin=44 * mm,
        bottomMargin=24 * mm,
    )
    styles = getSampleStyleSheet()

    title_style = ParagraphStyle("Title", parent=styles["Title"], fontSize=18, spaceAfter=6, textColor=PALETTE["ink"])
    subtitle_style = ParagraphStyle("Subtitle", parent=styles["Normal"], fontSize=10, textColor=PALETTE["slate"], spaceAfter=12)
    heading_style = ParagraphStyle("SectionHead", parent=styles["Heading2"], fontSize=13, spaceBefore=14, spaceAfter=6, textColor=PALETTE["ink"])
    body_style = ParagraphStyle("Body", parent=styles["Normal"], fontSize=10, leading=14, textColor=rl_colors.HexColor("#334155"))
    mono_style = ParagraphStyle("Mono", parent=styles["Normal"], fontSize=8, fontName="Courier", textColor=PALETTE["slate"], leading=11)

    elements = []

    # Header
    elements.append(Paragraph("Enterprise Compliance Report", title_style))
    report_id = report.get("report_id", "N/A")
    generated_at = report.get("generated_at", datetime.now(timezone.utc).isoformat())
    elements.append(Paragraph(f"Report ID: {report_id} | Generated: {generated_at}", subtitle_style))
    elements.append(HRFlowable(width="100%", thickness=1, color=rl_colors.HexColor("#CBD5E1")))
    elements.append(Spacer(1, 8))

    # Runbook Summary
    runbook = report.get("runbook", {})
    elements.append(Paragraph("Runbook Summary", heading_style))
    rb_data = [
        ["Field", "Value"],
        ["Status", str(runbook.get("status", "N/A")).upper()],
        ["Phase", str(runbook.get("phase", "N/A"))],
        ["Duration", f"{runbook.get('duration_seconds', 0)}s"],
        ["Trigger", str(report.get("trigger_mode", "N/A"))],
        ["Requested By", str(report.get("generated_by", "N/A"))],
    ]
    rb_table = Table(rb_data, colWidths=[120, 340])
    rb_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), rl_colors.HexColor("#F1F5F9")),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("TEXTCOLOR", (0, 0), (-1, -1), rl_colors.HexColor("#1E293B")),
        ("GRID", (0, 0), (-1, -1), 0.5, rl_colors.HexColor("#E2E8F0")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    elements.append(rb_table)
    elements.append(Spacer(1, 10))

    # Reliability Section
    reliability = report.get("reliability", {})
    if reliability:
        elements.append(Paragraph("Reliability Assessment", heading_style))
        rel_data = [
            ["Metric", "Value"],
            ["Final Score", f"{reliability.get('final_score', 'N/A')}/100"],
            ["Grade", str(reliability.get('grade', 'N/A'))],
            ["Issues Found", str(reliability.get('issues_found', 0))],
            ["Issues Auto-Fixed", str(reliability.get('issues_auto_fixed', 0))],
        ]
        rel_table = Table(rel_data, colWidths=[120, 340])
        rel_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), rl_colors.HexColor("#F1F5F9")),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 9),
            ("GRID", (0, 0), (-1, -1), 0.5, rl_colors.HexColor("#E2E8F0")),
            ("LEFTPADDING", (0, 0), (-1, -1), 8),
            ("TOPPADDING", (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ]))
        elements.append(rel_table)
        elements.append(Spacer(1, 10))

    # Checkpoint Trace
    checkpoints = report.get("checkpoints", [])
    if checkpoints:
        elements.append(Paragraph("Checkpoint Trace", heading_style))
        for cp in checkpoints[:10]:
            elements.append(Paragraph(f"Checkpoint: {cp.get('checkpoint_id', 'N/A')} | Phase: {cp.get('phase', 'N/A')} | At: {cp.get('created_at', 'N/A')}", body_style))
        elements.append(Spacer(1, 10))

    # Hash Verification
    elements.append(Paragraph("Document Integrity", heading_style))
    report_json_str = str(report)
    content_hash = hashlib.sha256(report_json_str.encode()).hexdigest()
    elements.append(Paragraph(f"Content SHA-256: {content_hash}", mono_style))
    elements.append(Paragraph(f"Generated: {generated_at}", mono_style))
    elements.append(Paragraph("This document is machine-generated. Verify the hash against the platform's compliance audit trail.", body_style))

    # Footer
    elements.append(Spacer(1, 20))
    elements.append(HRFlowable(width="100%", thickness=0.5, color=rl_colors.HexColor("#CBD5E1")))
    elements.append(Paragraph(f"RealAICoach Enterprise Compliance | {generated_at[:10]} | Report {report_id}", ParagraphStyle("Footer", parent=styles["Normal"], fontSize=8, textColor=rl_colors.HexColor("#94A3B8"), alignment=1)))

    def _draw_chrome(canv, build_doc):
        draw_page_chrome(
            canv,
            width=float(build_doc.pagesize[0]),
            height=float(build_doc.pagesize[1]),
            margin_x=20 * mm,
            page_no=canv.getPageNumber(),
            title="Enterprise Compliance Report",
            subtitle="Canonical governance artifact",
            right_primary=f"Report {str(report_id)[:24]}",
            right_secondary=f"Generated {str(generated_at)[:19]}",
            badge_text="ENTERPRISE COMPLIANCE GOVERNANCE",
            badge_status="INFO",
            footer_text="RealAICoach compliance engine • Enterprise profile",
        )

    doc.build(elements, onFirstPage=_draw_chrome, onLaterPages=_draw_chrome)
    return buf.getvalue()
