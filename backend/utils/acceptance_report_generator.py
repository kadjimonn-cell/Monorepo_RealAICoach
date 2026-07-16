"""Cross-provider acceptance report generator (JSON + Markdown + PDF)."""

from __future__ import annotations

import json
import hashlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List
import inspect

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle


def _enforce_pdf_v15_enterprise(payload: bytes, context: str) -> bytes:
    from middleware_pdf_policy import enforce_pdf_v15_theme_bytes

    themed, mode = enforce_pdf_v15_theme_bytes(payload)
    if mode in {"theme_passthrough_error", "non_pdf"} or not themed.startswith(b"%PDF-"):
        raise ValueError(f"PDF export validation failed: {context} ({mode})")
    return themed


ARTIFACT_FILES: List[str] = [
    "/tmp/fedapay_togo_basic_yearly_card_test.json",
    "/tmp/fedapay_abidjan_premium_monthly_test.json",
    "/tmp/fedapay_abidjan_basic_monthly_test.json",
    "/tmp/fedapay_togo_basic_monthly_card_test.json",
    "/tmp/iap_google_quebec_premium_monthly_test_after_fix.json",
    "/tmp/stripe_paris_basic_monthly_test.json",
    "/tmp/stripe_miami_basic_monthly_test.json",
    "/tmp/paypal_london_basic_monthly_test.json",
    "/tmp/paypal_sanantonio_premium_monthly_test.json",
    "/tmp/paypal_paris_basic_monthly_test.json",
]


def _normalize_record(raw: Dict[str, Any], artifact_path: str) -> Dict[str, Any]:
    summary = raw.get("summary", raw)
    simulation = raw.get("simulation", {})
    scenario = summary.get("scenario", {})
    tx = summary.get("transaction", {})
    counts = summary.get("counts", {})
    audit_types = summary.get("audit_event_types", [])

    # Compact IAP summary compatibility
    if not scenario and simulation.get("scenario"):
        s = simulation.get("scenario", {})
        scenario = {
            "name": "Goldie Jujuy",
            "email": s.get("email"),
            "home_address": "536 King Street, Quebec, Canada",
            "plan": str(s.get("plan", "")).title(),
            "duration": "1 month" if s.get("period") == "monthly" else str(s.get("period", "")),
            "platform": f"IAP {str(s.get('platform', '')).title()}",
        }
    if not tx and summary.get("transaction_id"):
        tx = {
            "transaction_id": summary.get("transaction_id"),
            "payment_status": summary.get("payment_status"),
            "provider": summary.get("provider"),
            "notification_sent": summary.get("notification_sent"),
            "user_receipt_sent": summary.get("user_receipt_sent"),
            "admin_receipt_sent": summary.get("admin_receipt_sent"),
            "receipt_number": summary.get("receipt_number"),
            "notification_dispatch_count": summary.get("notification_dispatch_count"),
        }
    if not counts and ("user_in_app_count" in summary or "admin_alert_count" in summary):
        counts = {
            "user_in_app_count": summary.get("user_in_app_count"),
            "admin_alert_count": summary.get("admin_alert_count"),
        }
    if not audit_types and summary.get("audit_event_types"):
        audit_types = summary.get("audit_event_types", [])

    user_in_app = counts.get("user_in_app_count")
    admin_alert = counts.get("admin_alert_count")
    dispatch_count = tx.get("notification_dispatch_count")
    if dispatch_count is None:
        dispatch_ok = (
            "user_in_app_notification_created" in audit_types
            and "admin_in_app_alert_created" in audit_types
            and "user_receipt_email_sent" in audit_types
            and "admin_receipt_email_sent" in audit_types
        )
    else:
        dispatch_ok = int(dispatch_count) == 1

    rule_pass = (
        user_in_app == 1
        and admin_alert == 1
        and bool(tx.get("notification_sent", True))
        and bool(tx.get("user_receipt_sent"))
        and bool(tx.get("admin_receipt_sent"))
        and dispatch_ok
        and ("subscription_confirmation_sent" not in audit_types)
    )

    provider = scenario.get("gateway") or scenario.get("platform") or tx.get("provider") or ""
    return {
        "artifact": artifact_path,
        "provider": provider,
        "scenario_name": scenario.get("name"),
        "scenario_location": scenario.get("home_address") or scenario.get("location"),
        "plan": scenario.get("plan"),
        "duration": scenario.get("duration"),
        "transaction_id": tx.get("transaction_id"),
        "receipt_number": tx.get("receipt_number"),
        "payment_status": tx.get("payment_status"),
        "user_in_app_count": user_in_app,
        "admin_alert_count": admin_alert,
        "user_receipt_sent": tx.get("user_receipt_sent"),
        "admin_receipt_sent": tx.get("admin_receipt_sent"),
        "notification_dispatch_count": dispatch_count,
        "has_subscription_confirmation_event": "subscription_confirmation_sent" in audit_types,
        "rule_1111_pass": rule_pass,
    }


async def _maybe_await(value):
    if inspect.isawaitable(value):
        return await value
    return value


async def _load_branding(db) -> Dict[str, Any]:
    doc = await _maybe_await(db.settings.find_one({"key": "receipt_branding"}, {"_id": 0})) or {}
    value = doc.get("value") or {}
    return {
        "brand_name": value.get("brand_name") or "RealAICoach",
        "primary_color": value.get("primary_color") or "#1E3A8A",
        "secondary_color": value.get("secondary_color") or "#F97316",
        "custom_logo": value.get("custom_logo"),
    }


def _scenario_row_hash(row: Dict[str, Any]) -> str:
    canonical = {
        "provider": row.get("provider"),
        "scenario_name": row.get("scenario_name"),
        "scenario_location": row.get("scenario_location"),
        "plan": row.get("plan"),
        "duration": row.get("duration"),
        "transaction_id": row.get("transaction_id"),
        "receipt_number": row.get("receipt_number"),
        "payment_status": row.get("payment_status"),
        "user_in_app_count": row.get("user_in_app_count"),
        "admin_alert_count": row.get("admin_alert_count"),
        "user_receipt_sent": row.get("user_receipt_sent"),
        "admin_receipt_sent": row.get("admin_receipt_sent"),
        "rule_1111_pass": row.get("rule_1111_pass"),
        "artifact": row.get("artifact"),
    }
    payload = json.dumps(canonical, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _write_markdown(path: Path, report: Dict[str, Any]) -> None:
    lines = [
        "# Cross-Provider Acceptance Report (1/1/1/1 Communication Rule)",
        "",
        f"Generated at: {report['generated_at']}",
        f"Scenarios: {report['total_scenarios']} | Passed: {report['passed']} | Failed: {report['failed']}",
        f"Version: {report['version']}",
        "",
        report["rule_definition"],
        "",
        "| Provider | User | Location | Plan | Duration | Transaction ID | Receipt # | PASS | Row Hash |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for row in report["rows"]:
        lines.append(
            f"| {row.get('provider','')} | {row.get('scenario_name','')} | {row.get('scenario_location','')} | {row.get('plan','')} | {row.get('duration','')} | {row.get('transaction_id','')} | {row.get('receipt_number','')} | {'PASS' if row.get('rule_1111_pass') else 'FAIL'} | {str(row.get('row_hash',''))[:12]}... |"
        )
    lines.extend(
        [
            "",
            "## Signature",
            "- Prepared by: __________________________",
            "- Reviewed by: __________________________",
            "- Approved by: __________________________",
            "- Date: _________________________________",
            "",
            "## Artifact Sources",
        ]
    )
    lines.append("")
    lines.append(f"- Report integrity hash: `{report.get('report_integrity_hash', '')}`")
    lines.append(f"- Tamper-evident rows: `{len(report.get('rows', []))}`")
    for row in report["rows"]:
        lines.append(f"- `{row['artifact']}`")
    path.write_text("\n".join(lines))


def _write_pdf(path: Path, report: Dict[str, Any], branding: Dict[str, Any]) -> None:
    from utils.pdf_v15_layout_composer import compose_pdf_v15_helper_layout

    primary = colors.HexColor(branding["primary_color"])
    accent = colors.HexColor(branding["secondary_color"])
    ink = colors.HexColor("#0F172A")
    slate = colors.HexColor("#475569")
    slate_soft = colors.HexColor("#F1F5F9")
    card_bg = colors.HexColor("#F8FAFC")
    border_soft = colors.HexColor("#E2E8F0")
    success = colors.HexColor("#15803D")
    danger = colors.HexColor("#B91C1C")
    danger_soft = colors.HexColor("#FEE2E2")

    page_w, _page_h = landscape(A4)
    margin = 28
    content_w = page_w - 2 * margin

    styles = getSampleStyleSheet()
    hero_title = ParagraphStyle("HeroTitle", parent=styles["Normal"], textColor=colors.white, fontName="Helvetica-Bold", fontSize=16, leading=19)
    hero_sub = ParagraphStyle("HeroSub", parent=styles["Normal"], textColor=colors.HexColor("#BFDBFE"), fontSize=8.5, leading=11)
    hero_meta_label = ParagraphStyle("HeroMetaLabel", parent=styles["Normal"], textColor=colors.HexColor("#93C5FD"), fontSize=6.5, leading=8)
    hero_meta_value = ParagraphStyle("HeroMetaValue", parent=styles["Normal"], textColor=colors.white, fontName="Helvetica-Bold", fontSize=8.5, leading=11)
    kpi_label = ParagraphStyle("KpiLabel", parent=styles["Normal"], textColor=slate, fontSize=7, leading=9)
    section_title = ParagraphStyle("SectionTitle", parent=styles["Normal"], textColor=ink, fontName="Helvetica-Bold", fontSize=9.5, leading=12)
    body_small = ParagraphStyle("BodySmall", parent=styles["Normal"], textColor=slate, fontSize=7.5, leading=10)
    mono_small = ParagraphStyle("MonoSmall", parent=styles["Normal"], textColor=ink, fontName="Courier", fontSize=7.5, leading=10)

    def _kpi_value_style(color) -> ParagraphStyle:
        return ParagraphStyle("KpiValue", parent=styles["Normal"], textColor=color, fontName="Helvetica-Bold", fontSize=15, leading=18)

    doc = SimpleDocTemplate(str(path), pagesize=landscape(A4), leftMargin=margin, rightMargin=margin, topMargin=100, bottomMargin=44)
    content = []

    # --- Hero band ---
    total = int(report.get("total_scenarios", 0))
    passed = int(report.get("passed", 0))
    failed = int(report.get("failed", 0))
    generated_short = str(report.get("generated_at", ""))[:19].replace("T", " ") + " UTC"
    meta_inner = Table(
        [
            [Paragraph("VERSION", hero_meta_label), Paragraph("GENERATED", hero_meta_label)],
            [Paragraph(str(report.get("version", "")), hero_meta_value), Paragraph(generated_short, hero_meta_value)],
        ],
        colWidths=[105, 145],
    )
    meta_inner.setStyle(TableStyle([
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 1),
    ]))
    hero = Table(
        [[
            [Paragraph("Communication Policy Compliance Matrix", hero_title),
             Paragraph("1/1/1/1 Communication Rule &nbsp;•&nbsp; Cross-Provider Acceptance &nbsp;•&nbsp; Nightly Automated Run", hero_sub)],
            meta_inner,
        ]],
        colWidths=[content_w - 270, 270],
    )
    hero.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), primary),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (0, 0), 14),
        ("LEFTPADDING", (1, 0), (1, 0), 10),
        ("RIGHTPADDING", (0, 0), (-1, -1), 10),
        ("TOPPADDING", (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
    ]))
    content.append(hero)
    accent_strip = Table([[""]], colWidths=[content_w], rowHeights=[3])
    accent_strip.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), accent),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
    ]))
    content.append(accent_strip)
    content.append(Spacer(1, 8))

    # --- KPI cards ---
    pass_rate = f"{(passed / total * 100):.0f}%" if total else "—"
    kpis = [
        ("SCENARIOS", str(total), ink),
        ("PASSED", str(passed), success if passed else ink),
        ("FAILED", str(failed), danger if failed else success),
        ("PASS RATE", pass_rate, success if total and failed == 0 else (danger if failed else slate)),
    ]
    card_w = (content_w - 3 * 12) / 4
    kpi_cells = []
    for label, value, color in kpis:
        kpi_cells.append([Paragraph(label, kpi_label), Paragraph(value, _kpi_value_style(color))])
    kpi_row = Table(
        [[kpi_cells[0], "", kpi_cells[1], "", kpi_cells[2], "", kpi_cells[3]]],
        colWidths=[card_w, 12, card_w, 12, card_w, 12, card_w],
    )
    kpi_style = TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("LEFTPADDING", (0, 0), (-1, -1), 12),
    ])
    for col in (0, 2, 4, 6):
        kpi_style.add("BACKGROUND", (col, 0), (col, 0), card_bg)
        kpi_style.add("BOX", (col, 0), (col, 0), 0.8, border_soft)
    kpi_row.setStyle(kpi_style)
    content.append(kpi_row)
    content.append(Spacer(1, 8))

    # --- PASS criteria checklist ---
    criteria = [
        "Exactly 1 user in-app notification",
        "Exactly 1 admin in-app alert",
        "Notification dispatched (notification_sent = true)",
        "User receipt email sent",
        "Admin receipt email sent",
        "Dispatch count = 1 (or legacy equivalent audit)",
        "No subscription_confirmation_sent event",
    ]
    bullet = f'<font color="{branding["secondary_color"]}">■</font>&nbsp;&nbsp;'
    half = (len(criteria) + 1) // 2
    crit_rows = []
    for i in range(half):
        left = Paragraph(bullet + criteria[i], body_small)
        right = Paragraph(bullet + criteria[i + half], body_small) if i + half < len(criteria) else ""
        crit_rows.append([left, right])
    criteria_tbl = Table(
        [[Paragraph("PASS Criteria — 1/1/1/1 Rule", section_title), ""]] + crit_rows,
        colWidths=[content_w / 2, content_w / 2],
    )
    criteria_tbl.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), slate_soft),
        ("BOX", (0, 0), (-1, -1), 0.8, border_soft),
        ("SPAN", (0, 0), (1, 0)),
        ("LEFTPADDING", (0, 0), (-1, -1), 12),
        ("RIGHTPADDING", (0, 0), (-1, -1), 12),
        ("TOPPADDING", (0, 0), (0, 0), 6),
        ("BOTTOMPADDING", (0, 0), (0, 0), 3),
        ("TOPPADDING", (0, 1), (-1, -1), 2),
        ("BOTTOMPADDING", (0, 1), (-1, -1), 2),
        ("BOTTOMPADDING", (0, -1), (-1, -1), 6),
    ]))
    content.append(criteria_tbl)
    content.append(Spacer(1, 8))

    # --- Compliance matrix ---
    content.append(Paragraph("Scenario Compliance Matrix", section_title))
    content.append(Spacer(1, 5))
    if report["rows"]:
        table_data = [["Provider", "User", "Location", "Plan", "Duration", "Transaction ID", "Receipt #", "Status", "Row Hash"]]
        for row in report["rows"]:
            table_data.append([
                str(row.get("provider", "")),
                str(row.get("scenario_name", "")),
                str(row.get("scenario_location", "")),
                str(row.get("plan", "")),
                str(row.get("duration", "")),
                str(row.get("transaction_id", "")),
                str(row.get("receipt_number", "")),
                "PASS" if row.get("rule_1111_pass") else "FAIL",
                f"{str(row.get('row_hash', ''))[:10]}…",
            ])
        weights = [0.09, 0.12, 0.18, 0.08, 0.08, 0.17, 0.10, 0.07, 0.11]
        table = Table(table_data, repeatRows=1, colWidths=[content_w * w for w in weights])
        style = TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), primary),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 7.5),
            ("GRID", (0, 0), (-1, -1), 0.25, border_soft),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, card_bg]),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ("ALIGN", (7, 0), (7, -1), "CENTER"),
            ("FONTNAME", (7, 1), (7, -1), "Helvetica-Bold"),
        ])
        for i, row in enumerate(report["rows"], start=1):
            if row.get("rule_1111_pass"):
                style.add("TEXTCOLOR", (7, i), (7, i), success)
            else:
                style.add("TEXTCOLOR", (7, i), (7, i), danger)
                style.add("BACKGROUND", (0, i), (-1, i), danger_soft)
        table.setStyle(style)
        content.append(table)
    else:
        empty_title = ParagraphStyle("EmptyTitle", parent=section_title, alignment=1, textColor=slate)
        empty_body = ParagraphStyle("EmptyBody", parent=body_small, alignment=1)
        empty_tbl = Table(
            [[[
                Paragraph("No scenario artifacts captured for this run", empty_title),
                Spacer(1, 4),
                Paragraph("Run the payment simulators (Stripe, PayPal, FedaPay, Google IAP, Apple IAP) to populate the compliance matrix for the next nightly report.", empty_body),
            ]]],
            colWidths=[content_w],
            rowHeights=[58],
        )
        empty_tbl.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), card_bg),
            ("BOX", (0, 0), (-1, -1), 0.8, border_soft),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("LEFTPADDING", (0, 0), (-1, -1), 40),
            ("RIGHTPADDING", (0, 0), (-1, -1), 40),
        ]))
        content.append(empty_tbl)
    content.append(Spacer(1, 8))

    # --- Tamper-evident integrity ---
    integrity_tbl = Table(
        [
            [Paragraph("Tamper-Evident Integrity", section_title), ""],
            [Paragraph("REPORT INTEGRITY HASH (SHA-256)", kpi_label), Paragraph("TAMPER-EVIDENT SIGNATURE", kpi_label)],
            [Paragraph(str(report.get("report_integrity_hash", "")), mono_small), Paragraph(str(report.get("tamper_signature", "")), mono_small)],
        ],
        colWidths=[content_w / 2, content_w / 2],
    )
    integrity_tbl.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), slate_soft),
        ("BOX", (0, 0), (-1, -1), 0.8, border_soft),
        ("SPAN", (0, 0), (1, 0)),
        ("BACKGROUND", (0, 2), (-1, 2), colors.white),
        ("BOX", (0, 2), (0, 2), 0.6, border_soft),
        ("BOX", (1, 2), (1, 2), 0.6, border_soft),
        ("LEFTPADDING", (0, 0), (-1, -1), 12),
        ("RIGHTPADDING", (0, 0), (-1, -1), 12),
        ("TOPPADDING", (0, 0), (0, 0), 8),
        ("BOTTOMPADDING", (0, 1), (-1, 1), 2),
        ("TOPPADDING", (0, 2), (-1, 2), 5),
        ("BOTTOMPADDING", (0, 2), (-1, 2), 8),
    ]))
    content.append(integrity_tbl)
    content.append(Spacer(1, 12))

    # --- Sign-off strip ---
    sign_labels = ["PREPARED BY", "REVIEWED BY", "APPROVED BY", "DATE"]
    sign_w = (content_w - 3 * 12) / 4
    sign_tbl = Table(
        [
            ["", "", "", "", "", "", ""],
            [Paragraph(sign_labels[0], kpi_label), "", Paragraph(sign_labels[1], kpi_label), "", Paragraph(sign_labels[2], kpi_label), "", Paragraph(sign_labels[3], kpi_label)],
        ],
        colWidths=[sign_w, 12, sign_w, 12, sign_w, 12, sign_w],
        rowHeights=[24, 12],
    )
    sign_style = TableStyle([
        ("VALIGN", (0, 1), (-1, 1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
    ])
    for col in (0, 2, 4, 6):
        sign_style.add("LINEBELOW", (col, 0), (col, 0), 0.8, slate)
    sign_tbl.setStyle(sign_style)
    content.append(sign_tbl)

    doc.build(content)
    raw_pdf = path.read_bytes()
    composed_pdf = compose_pdf_v15_helper_layout(
        raw_pdf,
        title="Acceptance Report",
        subtitle="Cross-provider communication policy compliance",
        right_primary=f"Rows: {len(report.get('rows', []))}",
        right_secondary=f"Version: {report.get('version', 'n/a')}",
        badge_text="ACCEPTANCE POLICY MATRIX",
        badge_status="PASS" if int(report.get("failed", 0)) == 0 else "WARNING",
        render_local_badge=True,
        footer_text="RealAICoach QA Governance • Enterprise profile",
        summary_title="Policy Snapshot",
        summary_rows=[
            ("Scenarios", str(report.get("total_scenarios", 0))),
            ("Passed", str(report.get("passed", 0))),
            ("Failed", str(report.get("failed", 0))),
        ],
        callout_title="Tamper Signature",
        callout_subtitle="Report integrity",
        callout_detail=str(report.get("tamper_signature", ""))[:70],
        callout_status="PASS" if int(report.get("failed", 0)) == 0 else "WARNING",
    )
    path.write_bytes(_enforce_pdf_v15_enterprise(composed_pdf, f"acceptance_report_{report.get('report_id', 'unknown')}"))


async def generate_acceptance_reports(db) -> Dict[str, Any]:
    rows: List[Dict[str, Any]] = []
    for file_path in ARTIFACT_FILES:
        p = Path(file_path)
        if not p.exists():
            continue
        raw = json.loads(p.read_text())
        rows.append(_normalize_record(raw, file_path))

    rows.sort(key=lambda r: (str(r.get("provider")), str(r.get("plan")), str(r.get("scenario_location"))))
    for row in rows:
        row["row_hash"] = _scenario_row_hash(row)

    generated_at = datetime.now(timezone.utc).isoformat()
    version = datetime.now(timezone.utc).strftime("v%Y.%m.%d.%H%M")
    aggregate_payload = json.dumps(
        {
            "generated_at": generated_at,
            "version": version,
            "row_hashes": [row.get("row_hash") for row in rows],
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    report_integrity_hash = hashlib.sha256(aggregate_payload.encode("utf-8")).hexdigest()
    tamper_signature = hashlib.sha256(f"{report_integrity_hash}:{version}".encode("utf-8")).hexdigest()
    report = {
        "generated_at": generated_at,
        "version": version,
        "total_scenarios": len(rows),
        "passed": sum(1 for r in rows if r.get("rule_1111_pass")),
        "failed": sum(1 for r in rows if not r.get("rule_1111_pass")),
        "rule_definition": "PASS requires: user_in_app_count=1, admin_alert_count=1, notification_sent=true, user_receipt_sent=true, admin_receipt_sent=true, dispatch_count=1 (or legacy equivalent audit), and no subscription_confirmation_sent event.",
        "report_integrity_hash": report_integrity_hash,
        "tamper_signature": tamper_signature,
        "rows": rows,
    }

    md_path = Path("/app/memory/ACCEPTANCE_REPORT.md")
    json_path = Path("/tmp/cross_provider_acceptance_report.json")
    pdf_path = Path("/tmp/cross_provider_acceptance_report.pdf")
    pdf_memory_path = Path("/app/memory/ACCEPTANCE_REPORT.pdf")

    json_path.write_text(json.dumps(report, indent=2, default=str))
    _write_markdown(md_path, report)
    branding = await _load_branding(db)
    _write_pdf(pdf_path, report, branding)
    pdf_memory_path.write_bytes(pdf_path.read_bytes())

    return {
        "json": str(json_path),
        "markdown": str(md_path),
        "pdf": str(pdf_memory_path),
        "pdf_export": str(pdf_path),
        "generated_at": generated_at,
        "version": version,
        "passed": report["passed"],
        "failed": report["failed"],
        "total": report["total_scenarios"],
    }
