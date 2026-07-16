"""Ad-blocker-safe payment document proxy routes extracted from payments.py."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Awaitable, Callable, Optional
from urllib.parse import quote

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response

from utils.pdf_v15_export import enforce_pdf_v15_enterprise as _base_enforce_pdf_v15_enterprise
from utils.pdf_v15_filename import build_pdf_v15_filename

from .payments_export_integrity import build_integrity_meta, export_theme_palette, parse_created_at
from .payments_history_shared import (
    _find_payment_record,
    _format_payment_date_label,
    _format_payment_status_label,
    _generate_document_html,
    _generate_pdf_from_payment,
    _get_document_logo_public_url,
)
from .payments_reporting_routes import (
    _build_payment_history_csv_text,
    _fetch_payment_history_export_items,
    _get_payment_history_export_settings,
    export_payment_history_csv,
    export_payment_history_pdf,
)


router = APIRouter()
BRAND_NAME = "RealAICoach"


async def _missing_user_resolver(_request: Request, token_override: Optional[str] = None):
    raise HTTPException(status_code=503, detail="Payment document proxy routes are not configured")


_get_user_from_request: Callable[..., Awaitable[object | None]] = _missing_user_resolver
_export_theme_palette = export_theme_palette
_build_integrity_meta = build_integrity_meta
_parse_created_at = parse_created_at


def configure_payment_document_proxy_routes(
    *,
    get_user_from_request: Callable[..., Awaitable[object | None]],
    brand_name: str,
) -> None:
    global _get_user_from_request, BRAND_NAME
    _get_user_from_request = get_user_from_request
    BRAND_NAME = brand_name or BRAND_NAME


def _enforce_pdf_v15_enterprise(payload: bytes, context: str) -> bytes:
    try:
        return _base_enforce_pdf_v15_enterprise(payload, context)
    except Exception:
        raise HTTPException(status_code=500, detail=f"PDF export validation failed: {context}")


def _assert_invoice_plan_access(user) -> None:
    """Invoice documents require a Basic plan or higher (receipts are owner-scoped free)."""
    from utils.access_control_engine import compute_effective_plan

    user_doc = {
        "is_admin": getattr(user, "is_admin", False),
        "subscription_plan": getattr(user, "subscription_plan", "free"),
        "subscription_status": getattr(user, "subscription_status", "active"),
        "full_access": getattr(user, "full_access", False),
        "subscription_permanent": getattr(user, "subscription_permanent", False),
        "premium_access": getattr(user, "premium_access", False),
    }
    if compute_effective_plan(user_doc) == "free":
        raise HTTPException(
            status_code=403,
            detail={
                "error": "Subscription Required",
                "message": "Invoice documents require a Basic plan or higher. Upgrade now to unlock access.",
                "current_plan": "free",
                "required_plan": "basic",
                "upgrade_url": "/subscription/plans",
            },
        )

@router.get("/docs/report")
async def docs_report(request: Request, token: str = None):
    """Proxy for PDF export — generic name avoids ad-blocker URL pattern matching."""
    return await export_payment_history_pdf(request, token)


@router.get("/docs/data")
async def docs_data(request: Request, token: str = None):
    """Proxy for CSV export — generic name avoids ad-blocker URL pattern matching."""
    return await export_payment_history_csv(request, token)


@router.get("/content/document")
@router.post("/content/document")
async def content_document(
    request: Request, doc_type: str = None, payment_id: str = None, inline: str = None, token: str = None
):
    """Proxy for receipt/invoice PDFs via a generic URL to avoid ad-blocker blocking."""

    payload = {}
    if request.method == "POST":
        content_type = (request.headers.get("content-type") or "").lower()
        try:
            if "application/json" in content_type:
                body = await request.json()
                if isinstance(body, dict):
                    payload = body
            else:
                form_data = await request.form()
                payload = {k: str(v) for k, v in form_data.items()}
        except Exception:
            payload = {}

    doc_alias = {
        "receipt": "receipt",
        "invoice": "invoice",
        "r": "receipt",
        "i": "invoice",
    }
    doc_type = doc_alias.get((doc_type or payload.get("doc_type") or payload.get("d") or "").strip().lower())
    payment_id = (payment_id or payload.get("payment_id") or payload.get("p") or "").strip()
    inline = (inline or payload.get("inline") or payload.get("v") or "").strip()
    token_override = (token or payload.get("token") or payload.get("t") or "").strip() or None

    if not doc_type or doc_type not in {"receipt", "invoice"}:
        raise HTTPException(status_code=400, detail="Invalid document type")
    if not payment_id:
        raise HTTPException(status_code=400, detail="Missing payment_id")
    user = await _get_user_from_request(request, token_override=token_override)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    if doc_type == "invoice":
        _assert_invoice_plan_access(user)
    payment = await _find_payment_record(user.user_id, payment_id)
    tm_value = request.query_params.get("tm") or request.query_params.get("transparency") or payload.get("tm") or payload.get("transparency")
    if str(tm_value or "").lower() in {"0", "false", "off"}:
        payment["transparency_mode"] = False
    pdf_bytes = await _generate_pdf_from_payment(doc_type, payment, getattr(user, "name", ""), user.email)
    pdf_bytes = _enforce_pdf_v15_enterprise(pdf_bytes, f"content_document_{doc_type}_{payment_id}")
    inline_requested = str(inline).lower() in {"1", "true", "yes", "inline"}
    disposition = "inline" if inline_requested else f'attachment; filename="{build_pdf_v15_filename(doc_type, payment_id)}"'
    return Response(content=pdf_bytes, media_type="application/pdf", headers={"Content-Disposition": disposition, "Cache-Control": "no-store, no-cache, must-revalidate", "Pragma": "no-cache"})


@router.get("/content/retrieve")
@router.post("/content/retrieve")
async def content_retrieve(request: Request, token: str = None):
    """Proxy for PDF export — alternate generic name for legacy clients."""
    return await export_payment_history_pdf(request, token)


@router.get("/content/export")
@router.post("/content/export")
async def content_export(request: Request, token: str = None):
    """Proxy for CSV export — alternate generic name for legacy clients."""
    return await export_payment_history_csv(request, token)


@router.get("/asset/f")
@router.post("/asset/f")
async def asset_file(request: Request, d: str = None, p: str = None, v: str = None, t: str = None):
    """Extra-safe short alias for receipt/invoice PDF routes to avoid browser URL blocking heuristics."""
    return await content_document(request=request, doc_type=d, payment_id=p, inline=v, token=t)


@router.get("/asset/x")
@router.post("/asset/x")
async def asset_export(request: Request, f: str = None, t: str = None, v: str = None):
    """Extra-safe short alias for payment history exports (f=p|pdf or f=c|csv)."""
    payload = {}
    if request.method == "POST":
        content_type = (request.headers.get("content-type") or "").lower()
        try:
            if "application/json" in content_type:
                body = await request.json()
                if isinstance(body, dict):
                    payload = body
            else:
                form_data = await request.form()
                payload = {k: str(v) for k, v in form_data.items()}
        except Exception:
            payload = {}

    file_type = (f or payload.get("f") or "").strip().lower()
    token_override = (t or payload.get("t") or payload.get("token") or "").strip() or None
    if token_override:
        request.state.token_override = token_override

    if file_type in {"p", "pdf"}:
        return await export_payment_history_pdf(request=request, token=token_override, inline=v)
    if file_type in {"c", "csv"}:
        return await export_payment_history_csv(request=request, token=token_override)
    raise HTTPException(status_code=400, detail="Invalid export type")


@router.get("/r/f")
@router.post("/r/f")
async def relay_file(request: Request, d: str = None, p: str = None, v: str = None, t: str = None, inline: str = None):
    """Ultra-neutral alias for receipt/invoice PDFs used by preview builds."""
    # Support both 'v' and 'inline' query params for inline viewing
    inline_flag = inline or v
    return await content_document(request=request, doc_type=d, payment_id=p, inline=inline_flag, token=t)


@router.get("/r/x")
@router.post("/r/x")
async def relay_export(request: Request, f: str = None, t: str = None, v: str = None, inline: str = None):
    """Ultra-neutral alias for payment history exports used by preview builds."""
    return await asset_export(request=request, f=f, t=t, v=v or inline)


@router.get("/r/v")
async def relay_document_view(request: Request, d: str, p: str, t: str = None, tm: str = "1"):
    """Preview-safe HTML viewer for invoice/receipt documents."""
    doc_alias = {"receipt": "receipt", "invoice": "invoice", "r": "receipt", "i": "invoice"}
    doc_type = doc_alias.get((d or "").strip().lower())
    payment_id = (p or "").strip()
    token_override = (t or "").strip() or None

    if not doc_type:
        raise HTTPException(status_code=400, detail="Invalid document type")
    if not payment_id:
        raise HTTPException(status_code=400, detail="Missing payment_id")

    user = await _get_user_from_request(request, token_override=token_override)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    if doc_type == "invoice":
        _assert_invoice_plan_access(user)

    payment = await _find_payment_record(user.user_id, payment_id)
    if str(tm).lower() in {"0", "false", "off"}:
        payment["transparency_mode"] = False
    safe_pdf_url = f"/api/r/f?d={'r' if doc_type == 'receipt' else 'i'}&p={payment_id}&v=0&tm={tm}"
    if token_override:
        safe_pdf_url = f"{safe_pdf_url}&t={token_override}"

    html = _generate_document_html(
        doc_type,
        payment,
        getattr(user, "name", ""),
        user.email,
        pdf_url=safe_pdf_url,
        auto_open_pdf=False,
    )
    return HTMLResponse(content=html)


@router.get("/r/t")
async def relay_history_tool(request: Request, m: str, t: str = None):
    """Preview-safe HTML tool page for payment history print/export actions."""
    mode = (m or "").strip().lower()
    token_override = (t or "").strip() or None
    user = await _get_user_from_request(request, token_override=token_override)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")

    if mode not in {"pdf", "csv", "print"}:
        raise HTTPException(status_code=400, detail="Invalid tool mode")

    if mode == "pdf":
        inline_pdf_url = "/api/r/x?f=p&v=1"
        if token_override:
            inline_pdf_url = f"{inline_pdf_url}&t={token_override}"
        return RedirectResponse(url=inline_pdf_url, status_code=302)

    items = await _fetch_payment_history_export_items(user.user_id, limit=400)
    settings = await _get_payment_history_export_settings()
    palette = _export_theme_palette(settings.get("theme_profile"))
    csv_text = _build_payment_history_csv_text(items)

    rows = []
    total_spent = 0.0
    for item in items:
        if str(item.get("status", "")).lower() in {"completed", "paid", "success", "succeeded"}:
            total_spent += float(item.get("amount", 0) or 0)
        rows.append(
            "<tr>"
            f"<td>{_format_payment_date_label(item.get('created_at', ''), with_time=True)}</td>"
            f"<td>{item.get('reference_id') or '—'}</td>"
            f"<td>{item.get('plan_name', 'Unknown')} Plan</td>"
            f"<td>${float(item.get('amount', 0) or 0):.2f} {item.get('currency', 'USD')}</td>"
            f"<td>{item.get('method', 'Unknown')}</td>"
            f"<td>{item.get('status_label', _format_payment_status_label(item.get('status', 'unknown')))}</td>"
            f"<td>{item.get('source', 'Payments')}</td>"
            "</tr>"
        )

    integrity = _build_integrity_meta(csv_text, len(items), total_spent, signature_enabled=settings.get("signature_enabled", True))
    generated_dt = _parse_created_at(integrity.get("generated_at")) or datetime.now(timezone.utc)
    generated_label = generated_dt.strftime("%B %d, %Y at %I:%M %p UTC")

    if mode == "csv":
        data_uri = f"data:text/csv;charset=utf-8,{quote(csv_text)}"
        logo_url = _get_document_logo_public_url()
        logo_html = (
            f'<img src="{logo_url}" alt="{BRAND_NAME} logo" style="width:138px;max-width:100%;height:auto;display:block;margin-bottom:16px;" />'
            if logo_url
            else ""
        )
        html = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Payment History CSV</title>
<style>body{{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;padding:24px;background:#EEF2FF;color:#0f172a}}.shell{{max-width:1080px;margin:0 auto;background:#fff;border:1px solid {palette['surface_border']};border-radius:24px;overflow:hidden;box-shadow:0 18px 40px rgba(37,99,235,0.12)}}.hero{{padding:22px 24px;background:{palette['hero_bg']};color:#fff}}h1{{margin:10px 0 6px;font-size:30px;letter-spacing:-.6px}}p{{margin:0;color:{palette['hero_text']}}}.meta{{margin-top:10px;font-size:12px;color:{palette['hero_text']};font-weight:700}}.body{{padding:22px 24px}}.actions{{display:flex;gap:10px;flex-wrap:wrap;margin:0 0 16px}}button,a{{background:{palette['table_header']};color:#fff;border:none;border-radius:999px;padding:12px 18px;font-weight:700;cursor:pointer;text-decoration:none;display:inline-flex;align-items:center;justify-content:center}}a.back{{background:#fff;color:#0f172a;border:1px solid #cbd5e1}}pre{{white-space:pre-wrap;word-break:break-word;background:#0F172A;color:#E2E8F0;padding:18px;border-radius:16px;border:1px solid #334155;overflow:auto;max-height:520px}}.sig{{margin-top:12px;padding:12px;border-radius:10px;background:#F8FAFC;border:1px solid #E2E8F0;font-size:11px;color:#334155}}</style>
</head><body><div class="shell"><div class="hero">{logo_html}<h1>Payment History CSV</h1><p>Enterprise export with standardized accounting columns.</p><div class="meta">Rows: {len(items)} · Total You Paid: ${total_spent:.2f} · Theme: {settings.get('theme_profile','enterprise').title()}</div></div><div class="body"><div class="actions"><a data-testid="payment-history-csv-download-link" href="{data_uri}" download="payment-history-enterprise.csv">Download CSV</a><a class="back" href="/payment-history">Back to Payment History</a></div><pre>{csv_text}</pre><div class="sig" data-testid="payment-history-integrity-footer">{settings.get('signature_label','Integrity Signature')}<br/>Report ID: {integrity['report_id']}<br/>Generated: {generated_label}<br/>Generated ISO: {integrity['generated_at']}<br/>Report Hash: {integrity['data_hash']}<br/>Signature: {integrity['signature'] or 'DISABLED'}</div></div></div></body></html>"""
        return HTMLResponse(content=html)

    page_title = "Payment History PDF" if mode == "pdf" else "Print Payment History"
    page_subtitle = (
        "Use your browser print dialog to save this page as PDF."
        if mode == "pdf"
        else "Use your browser print dialog to print or save this page as PDF."
    )
    auto_print_script = (
        "<script>setTimeout(function(){window.print();},250);</script>" if mode in {"pdf", "print"} else ""
    )
    html = f"""<!DOCTYPE html>
<html><head><meta charset=\"utf-8\"><meta name=\"viewport\" content=\"width=device-width,initial-scale=1\"><title>{page_title}</title>
<style>body{{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;padding:24px;background:#EEF2FF;color:#0f172a}}.shell{{max-width:1080px;margin:0 auto;background:#fff;border:1px solid {palette['surface_border']};border-radius:24px;overflow:hidden;box-shadow:0 18px 40px rgba(37,99,235,0.12)}}.hero{{padding:22px 24px;background:{palette['hero_bg']};color:#fff}}h1{{margin:10px 0 6px;font-size:30px;letter-spacing:-.6px}}p{{margin:0;color:{palette['hero_text']}}}.meta{{margin-top:10px;font-size:12px;color:{palette['hero_text']};font-weight:700}}.body{{padding:22px 24px}}.actions{{margin:0 0 18px;display:flex;gap:10px;flex-wrap:wrap}}button,a{{background:{palette['table_header']};color:#fff;border:none;border-radius:999px;padding:12px 18px;font-weight:700;cursor:pointer;text-decoration:none;display:inline-flex;align-items:center;justify-content:center}}a.back{{background:#fff;color:#0f172a;border:1px solid #cbd5e1}}table{{width:100%;border-collapse:collapse;border:1px solid {palette['table_grid']};border-radius:16px;overflow:hidden}}th,td{{padding:11px 10px;border-bottom:1px solid #e2e8f0;text-align:left;font-size:12px}}th{{background:{palette['table_header']};color:#fff;font-size:11px;text-transform:uppercase;letter-spacing:.08em}}tr:nth-child(even) td{{background:#F8FAFC}}.sig{{margin-top:12px;padding:12px;border-radius:10px;background:#F8FAFC;border:1px solid #E2E8F0;font-size:11px;color:#334155}}@media print{{.actions{{display:none}}body{{padding:0;background:#fff}}.shell{{box-shadow:none;border:none}}}}</style>
</head><body><div class=\"shell\"><div class=\"hero\"><h1>{page_title}</h1><p>{page_subtitle}</p><div class=\"meta\">{getattr(user, "email", "")} · Generated {generated_label} · Total You Paid: ${total_spent:.2f} · Rows: {len(rows)} · Theme: {settings.get('theme_profile','enterprise').title()}</div></div><div class=\"body\"><div class=\"actions\"><button data-testid=\"payment-history-print-dialog-button\" onclick=\"window.print();return false;\">Print / Save as PDF</button><a class=\"back\" href=\"/payment-history\">Back to Payment History</a></div><table><thead><tr><th>Date</th><th>Reference</th><th>Plan</th><th>Amount</th><th>Method</th><th>Status</th><th>Source</th></tr></thead><tbody>{"".join(rows) if rows else '<tr><td colspan="7">No payments found.</td></tr>'}</tbody></table><div class=\"sig\" data-testid=\"payment-history-integrity-footer\">{settings.get('signature_label','Integrity Signature')}<br/>Report ID: {integrity['report_id']}<br/>Generated: {generated_label}<br/>Generated ISO: {integrity['generated_at']}<br/>Report Hash: {integrity['data_hash']}<br/>Signature: {integrity['signature'] or 'DISABLED'}</div></div></div>{auto_print_script}</body></html>"""
    return HTMLResponse(content=html)
