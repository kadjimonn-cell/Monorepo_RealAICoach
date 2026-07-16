"""Shared helpers and configuration for extracted payment history modules."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Awaitable, Callable, Dict, Optional
import os
import uuid

from fastapi import HTTPException, Request

from utils.payment_localization import detect_payment_locale
from utils.pdf_v15_export import enforce_pdf_v15_enterprise as _base_enforce_pdf_v15_enterprise
from utils.receipt_generator import format_payment_method_label, format_payment_status_label

from .db import db
from .payments_branding import get_document_logo_public_url
from .payments_export_integrity import (
    build_integrity_payload,
    format_payment_date_label,
    parse_created_at,
    resolve_plan_name,
    sign_integrity_payload,
)
from .payments_pricing_guard import (
    apply_canonical_plan_pricing,
    assert_plan_pricing_or_block,
    assert_plan_pricing_or_raise_sync,
)


BRAND_NAME = os.environ.get("BRAND_NAME", "RealAICoach")


async def _missing_user_resolver(_request: Request, token_override: Optional[str] = None):
    raise HTTPException(status_code=503, detail="Payment history routes are not configured")


async def _missing_payment_email(*_args, **_kwargs):
    raise HTTPException(status_code=503, detail="Payment email sender is not configured")


def _default_safe_float(value: Any, fallback: float = 0.0) -> float:
    try:
        if value is None:
            return fallback
        return float(value)
    except (TypeError, ValueError):
        return fallback


_get_user_from_request: Callable[..., Awaitable[object | None]] = _missing_user_resolver
_send_payment_email: Callable[..., Awaitable[dict]] = _missing_payment_email
_safe_float: Callable[[Any, float], float] = _default_safe_float
_assert_plan_pricing_or_block = assert_plan_pricing_or_block
_assert_plan_pricing_or_raise_sync = assert_plan_pricing_or_raise_sync
_apply_canonical_plan_pricing = apply_canonical_plan_pricing
_format_payment_date_label = format_payment_date_label
_format_payment_method_label = format_payment_method_label
_format_payment_status_label = format_payment_status_label
_resolve_plan_name = resolve_plan_name
_parse_created_at = parse_created_at
_build_integrity_payload = build_integrity_payload
_sign_integrity_payload = sign_integrity_payload
_get_document_logo_public_url = get_document_logo_public_url


def configure_payment_history_routes(
    *,
    get_user_from_request: Callable[..., Awaitable[object | None]],
    send_payment_email: Callable[..., Awaitable[dict]],
    safe_float: Callable[[Any, float], float],
) -> None:
    global _get_user_from_request, _send_payment_email, _safe_float
    _get_user_from_request = get_user_from_request
    _send_payment_email = send_payment_email
    _safe_float = safe_float

    # Keep split route modules in sync even if they imported symbols directly.
    import sys

    module_names = (
        "routes.payments_history_tax_routes",
        "routes.payments_history_document_routes",
        "routes.payments_history_bulk_routes",
    )
    for module_name in module_names:
        mod = sys.modules.get(module_name)
        if not mod:
            continue
        setattr(mod, "_get_user_from_request", get_user_from_request)
        setattr(mod, "_send_payment_email", send_payment_email)
        setattr(mod, "_safe_float", safe_float)


def _enforce_pdf_v15_enterprise(payload: bytes, context: str) -> bytes:
    try:
        return _base_enforce_pdf_v15_enterprise(payload, context)
    except Exception:
        raise HTTPException(status_code=500, detail=f"PDF export validation failed: {context}")


def _detect_locale(tx: Optional[Dict[str, Any]] = None) -> str:
    return detect_payment_locale(tx)


def _is_french_context(tx: Optional[Dict[str, Any]] = None) -> bool:
    return _detect_locale(tx) == "fr"


def _receipt_product_type_label(_: Optional[str] = None) -> str:
    return "Digital Platform Access"


def _parse_statement_scope(scope: str, year: int, month: Optional[int]) -> tuple[str, str]:
    if scope not in {"monthly", "yearly"}:
        raise HTTPException(status_code=400, detail="scope must be monthly or yearly")
    if year < 2000 or year > 2100:
        raise HTTPException(status_code=400, detail="Invalid year")
    if scope == "monthly":
        if month is None or month < 1 or month > 12:
            raise HTTPException(status_code=400, detail="month is required for monthly scope (1-12)")
        prefix = f"{year:04d}-{month:02d}"
        label = f"{year:04d}-{month:02d}"
    else:
        prefix = f"{year:04d}"
        label = f"{year:04d}"
    return prefix, label


def _payment_from_txn(txn: Dict[str, Any], payment_id: str) -> Dict[str, Any]:
    subtotal = _safe_float(txn.get("subtotal", txn.get("amount", txn.get("amount_usd", 0))), 0.0)
    tax_amount = _safe_float(txn.get("tax_amount", 0), 0.0)
    processing_fee = _safe_float(txn.get("processing_fee", txn.get("fee", txn.get("fee_local", 0))), 0.0)
    amount_gross = _safe_float(txn.get("amount_gross", subtotal + tax_amount), subtotal + tax_amount)
    total_amount = _safe_float(txn.get("total_amount", amount_gross), amount_gross)
    amount_net = _safe_float(txn.get("amount_net", max(total_amount - processing_fee, 0)), max(total_amount - processing_fee, 0))
    raw_response = txn.get("raw_response") if isinstance(txn.get("raw_response"), dict) else {}
    pricing_breakdown = raw_response.get("pricing_breakdown") if isinstance(raw_response.get("pricing_breakdown"), dict) else {}
    base_plan_price = _safe_float(
        txn.get("base_plan_price", pricing_breakdown.get("base_plan_price", 0)),
        0.0,
    )

    return {
        "id": txn.get("id") or txn.get("payment_id") or payment_id,
        "payment_id": txn.get("payment_id") or txn.get("session_id") or payment_id,
        "transaction_id": txn.get("transaction_id") or txn.get("payment_id") or txn.get("session_id") or payment_id,
        "plan_id": txn.get("plan_id"),
        "amount": _safe_float(txn.get("amount", amount_gross), amount_gross),
        "currency": txn.get("currency", "USD"),
        "payment_method": txn.get("payment_method"),
        "provider": txn.get("provider") or txn.get("gateway") or txn.get("payment_method"),
        "status": txn.get("payment_status") or txn.get("status") or "completed",
        "billing_period": txn.get("billing_period"),
        "created_at": txn.get("created_at"),
        "updated_at": txn.get("updated_at"),
        "subtotal": subtotal,
        "tax_amount": tax_amount,
        "processing_fee": processing_fee,
        "amount_gross": amount_gross,
        "amount_net": amount_net,
        "total_amount": total_amount,
        "base_plan_price": base_plan_price,
        "tax_rate": _safe_float(txn.get("tax_rate", 0), 0.0),
        "tax_provider": txn.get("tax_provider", "internal_rules_engine"),
        "tax_breakdown": txn.get("tax_breakdown", []),
        "jurisdiction": txn.get("jurisdiction", {}),
        "product_type": txn.get("product_type", "education_digital_service"),
        "transparency_mode": bool(txn.get("transparency_mode", True)),
    }


async def _alert_missing_tax_fields(user_id: str, payment_id: str, context: str, missing_fields: list[str]) -> None:
    if not missing_fields:
        return
    await db.payment_tax_alerts.insert_one(
        {
            "alert_id": f"tax_alert_{uuid.uuid4().hex[:12]}",
            "user_id": user_id,
            "payment_id": payment_id,
            "context": context,
            "missing_fields": missing_fields,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "resolved": False,
        }
    )


async def _get_receipt_transparency_mode(user_id: str) -> bool:
    pref = await db.user_preferences.find_one({"user_id": user_id}, {"_id": 0, "receipt_transparency_mode": 1}) or {}
    if "receipt_transparency_mode" not in pref:
        return True
    return bool(pref.get("receipt_transparency_mode", True))


def _missing_tax_fields(payment: Dict[str, Any]) -> list[str]:
    required = ["subtotal", "tax_amount", "processing_fee", "amount_gross", "amount_net", "total_amount", "tax_rate", "jurisdiction", "product_type"]
    missing = []
    for field in required:
        value = payment.get(field)
        if value is None:
            missing.append(field)
        elif field == "jurisdiction" and not isinstance(value, dict):
            missing.append(field)
        elif field == "product_type" and not str(value).strip():
            missing.append(field)
    return missing


async def _find_payment_record(user_id: str, payment_id: str) -> dict:
    transparency_mode = await _get_receipt_transparency_mode(user_id)
    payment = await db.payments.find_one(
        {"user_id": user_id, "$or": [{"id": payment_id}, {"payment_id": payment_id}]}, {"_id": 0}
    )

    txn = await db.payment_transactions.find_one(
        {"user_id": user_id, "$or": [{"payment_id": payment_id}, {"session_id": payment_id}, {"id": payment_id}, {"transaction_id": payment_id}]},
        {"_id": 0},
    )

    if not payment and not txn:
        raise HTTPException(status_code=404, detail="Payment not found")

    if txn:
        canonical = _payment_from_txn(txn, payment_id)
        if payment:
            merged = {**payment, **canonical}
            merged["transparency_mode"] = transparency_mode
            missing_before = _missing_tax_fields(payment)
            if missing_before:
                await _alert_missing_tax_fields(user_id, payment_id, "receipt_generation", missing_before)
                await db.payments.update_one(
                    {"user_id": user_id, "$or": [{"id": payment_id}, {"payment_id": payment_id}]},
                    {"$set": {k: merged.get(k) for k in canonical.keys()}},
                )
            return merged
        canonical["transparency_mode"] = transparency_mode
        return canonical

    missing_payment_fields = _missing_tax_fields(payment)
    if missing_payment_fields:
        await _alert_missing_tax_fields(user_id, payment_id, "receipt_generation_no_txn", missing_payment_fields)
        subtotal = _safe_float(payment.get("amount", 0), 0.0)
        payment = {
            **payment,
            "subtotal": _safe_float(payment.get("subtotal", subtotal), subtotal),
            "tax_amount": _safe_float(payment.get("tax_amount", 0), 0.0),
            "processing_fee": _safe_float(payment.get("processing_fee", 0), 0.0),
            "amount_gross": _safe_float(payment.get("amount_gross", subtotal), subtotal),
            "total_amount": _safe_float(payment.get("total_amount", subtotal), subtotal),
            "amount_net": _safe_float(payment.get("amount_net", subtotal), subtotal),
            "tax_rate": _safe_float(payment.get("tax_rate", 0), 0.0),
            "jurisdiction": payment.get("jurisdiction", {}),
            "product_type": payment.get("product_type", "education_digital_service"),
            "transparency_mode": transparency_mode,
        }

    payment["transparency_mode"] = bool(payment.get("transparency_mode", transparency_mode))
    return payment


def _generate_document_html(
    doc_type: str, payment: dict, user_name: str, user_email: str, pdf_url: str = "", auto_open_pdf: bool = True
) -> str:
    plan_names = {"basic": "Basic", "premium": "Premium", "free": "Free"}
    plan_name = plan_names.get(payment.get("plan_id", ""), payment.get("plan_id", "Unknown"))
    amount = _safe_float(payment.get("amount", 0), 0.0)
    subtotal = _safe_float(payment.get("subtotal", amount), amount)
    tax_amount = _safe_float(payment.get("tax_amount", 0), 0.0)
    processing_fee = _safe_float(payment.get("processing_fee", 0), 0.0)
    amount_gross = _safe_float(payment.get("amount_gross", subtotal + tax_amount), subtotal + tax_amount)
    total_charged = _safe_float(payment.get("total_amount", amount_gross), amount_gross)
    amount_net = _safe_float(payment.get("amount_net", max(total_charged - processing_fee, 0)), max(total_charged - processing_fee, 0))
    tax_rate = _safe_float(payment.get("tax_rate", 0), 0.0)
    jurisdiction = payment.get("jurisdiction", {}) if isinstance(payment.get("jurisdiction"), dict) else {}
    tax_jurisdiction = f"{jurisdiction.get('country', '')}-{jurisdiction.get('state', '')}".strip("-") if jurisdiction else "N/A"
    method = payment.get("payment_method", "card")
    status = payment.get("status", "completed")
    created = payment.get("created_at", "")
    payment_id = payment.get("payment_id", payment.get("id", "N/A"))
    billing = payment.get("billing_period", "monthly")
    transparency_mode = bool(payment.get("transparency_mode", True))
    product_type = _receipt_product_type_label(payment.get("product_type", "education_digital_service"))
    is_fr = _is_french_context(payment)

    try:
        if isinstance(created, str):
            d = datetime.fromisoformat(created.replace("Z", "+00:00"))
        else:
            d = created
        date_str = d.strftime("%B %d, %Y")
        date_short = d.strftime("%Y-%m-%d")
    except Exception:
        date_str = str(created)[:10]
        date_short = str(created)[:10]

    doc_num = (
        f"{'INV' if doc_type == 'invoice' else 'RCT'}-{date_short.replace('-', '')}-{payment_id[:8].upper()}"
        if payment_id != "N/A"
        else f"{'INV' if doc_type == 'invoice' else 'RCT'}-{date_short.replace('-', '')}"
    )
    title = "FACTURE" if (is_fr and doc_type == "invoice") else "REÇU" if (is_fr and doc_type == "receipt") else "INVOICE" if doc_type == "invoice" else "RECEIPT"
    method_display = "Credit/Debit Card (Stripe)" if "stripe" in method else "PayPal" if method == "paypal" else "Mobile Money" if "mobile" in method else method.replace("_", " ").title()
    status_class = "status-paid" if status == "completed" else "status-pending"
    status_display = "Payé" if (is_fr and status == "completed") else "Paid" if status == "completed" else status.title()
    explainability_html = ""
    if transparency_mode:
        explain_title = "Explication du reçu" if is_fr else "Receipt Explainability"
        tax_basis_label = "Base fiscale" if is_fr else "Tax Basis"
        product_type_label = "Type de produit" if is_fr else "Product Type"
        fee_policy_label = "Politique des frais" if is_fr else "Fee Policy"
        net_amount_label = "Montant net après frais" if is_fr else "Net Settlement After Fee"
        fee_policy_text = "Les frais de traitement du paiement sont inclus dans le total payé par le client." if is_fr else "Payment processing fee is included in the total paid by the customer."
        formula_text = "Calcul: Prix de base + taxe applicable + frais de traitement = total à payer. Montant net après frais = total payé − frais de traitement." if is_fr else "How this was calculated: Base Subscription Price + Applicable Tax + Payment Processing Fee = Total You Pay. Net Settlement After Fee = Total You Pay − Payment Processing Fee."
        explainability_html = f"""
  <div class=\"section\">
   <div class=\"section-title\">{explain_title}</div>
   <div class=\"info-grid\">
    <div class=\"info-item\"><label>{tax_basis_label}</label><span>{tax_jurisdiction or 'N/A'} @ {tax_rate * 100:.2f}%</span></div>
    <div class=\"info-item\"><label>{product_type_label}</label><span>{product_type}</span></div>
    <div class=\"info-item\"><label>{fee_policy_label}</label><span>{fee_policy_text}</span></div>
    <div class=\"info-item\"><label>{net_amount_label}</label><span>${amount_net:.2f} USD</span></div>
   </div>
   <p style=\"margin:10px 0 0;color:#475569;font-size:12px;line-height:1.5;\">{formula_text}</p>
  </div>
"""

    download_btn = ""
    download_url_attr = ""
    pdf_redirect_script = ""
    fallback_banner = ""
    if pdf_url:
        from utils.pdf_v15_filename import build_pdf_v15_filename

        fallback_download_name = build_pdf_v15_filename("receipt", payment_id)
        download_btn_label = "Télécharger le PDF" if is_fr else "Download PDF"
        download_btn = f'<a href="{pdf_url}" class="act-btn act-download" id="downloadBtn" download onclick="window.location.href=this.href;return false;" style="text-decoration:none;color:#fff"><svg viewBox="0 0 24 24"><path d="M5 20h14v-2H5v2zm7-18L5.33 9h3.84v6h3.66V9h3.84L12 2z" transform="rotate(180 12 12)"/></svg> {download_btn_label}</a>'
        download_url_attr = f'data-pdf-url="{pdf_url}"'
        if auto_open_pdf:
            pdf_redirect_script = f'''
try{{
  fetch("{pdf_url}").then(function(r){{
    if(!r.ok)throw new Error("fetch fail");
    return r.blob();
  }}).then(function(b){{
    var u=URL.createObjectURL(b);
    window.location.replace(u);
  }}).catch(function(){{
    window.location.replace("{pdf_url}");
  }});
}}catch(e){{}}'''
            fallback_banner = f'''<div style="max-width:680px;margin:0 auto 16px;background:#FEF3C3;border:1px solid #F59E0B;border-radius:12px;padding:16px 24px;text-align:center">
  <p style="margin:0;color:#92400E;font-size:14px;font-weight:600">Loading PDF...</p>
  <p style="margin:8px 0 0;font-size:13px;color:#78350F">
    If not loaded automatically:
    <a href="#" id="fallbackDownload" style="color:#2563EB;text-decoration:underline;font-weight:700">Click here to download PDF</a>
    &nbsp;&bull;&nbsp; Press <kbd style="background:#E5E7EB;padding:2px 6px;border-radius:3px;font-size:11px">Ctrl+P</kbd> to print
  </p>
  <script>
  document.getElementById("fallbackDownload").addEventListener("click",function(e){{
    e.preventDefault();
    fetch("{pdf_url}").then(function(r){{return r.blob();}}).then(function(b){{
      var u=URL.createObjectURL(b);
      var a=document.createElement("a");a.href=u;a.download="{fallback_download_name}";
      document.body.appendChild(a);a.click();document.body.removeChild(a);
    }}).catch(function(){{window.location.href="{pdf_url}";}});
  }});
  </script>
</div>'''

    logo_url = _get_document_logo_public_url()
    logo_block = f'<img src="{logo_url}" alt="{BRAND_NAME}" style="width:36px;height:36px;object-fit:contain;border-radius:8px;display:inline-block;vertical-align:middle;margin-right:10px;" /><span style="font-size:16px;font-weight:700;vertical-align:middle;letter-spacing:0.3px">{BRAND_NAME}</span>' if logo_url else f'<div class="brand">{BRAND_NAME}</div>'
    return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>RealAICoach {title} {doc_num}</title>
<script>{pdf_redirect_script}</script>
<script>
(function(){{
  document.addEventListener('click',function(e){{
    var el=e.target;
    for(var i=0;i<6&&el;i++){{
      if(el.classList&&el.classList.contains('act-print')){{e.stopImmediatePropagation();e.preventDefault();window.print();return;}}
      if(el.classList&&el.classList.contains('act-download')){{e.stopImmediatePropagation();e.preventDefault();var h=el.getAttribute('href')||el.dataset&&el.dataset.pdfUrl;if(h)window.location.href=h;return;}}
      el=el.parentElement;
    }}
  }},true);
}})();
</script>
<style>
*{{margin:0;padding:0;box-sizing:border-box}}
body{{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;background:#eef2ff;color:#1e293b;padding:40px}}
.doc{{max-width:680px;margin:0 auto;background:#fff;border-radius:20px;overflow:hidden;box-shadow:0 12px 36px rgba(37,99,235,0.14);border:1px solid #bfdbfe;position:relative;z-index:1}}
.doc-header{{background:linear-gradient(135deg,#1d4ed8,#4f46e5,#0ea5e9);padding:36px 40px;color:#fff}}
.doc-header h1{{font-size:28px;font-weight:800;letter-spacing:2px;margin-bottom:4px}}
.doc-header .brand{{font-size:14px;opacity:0.85;margin-bottom:20px}}
.doc-header .meta{{display:flex;justify-content:space-between;font-size:13px;opacity:0.9}}
.doc-body{{padding:36px 40px}}
.section{{margin-bottom:28px}}
.section-title{{font-size:11px;text-transform:uppercase;letter-spacing:1.5px;color:#94a3b8;font-weight:600;margin-bottom:12px}}
.info-grid{{display:grid;grid-template-columns:1fr 1fr;gap:16px}}
.info-item label{{display:block;font-size:12px;color:#94a3b8;margin-bottom:2px}}
.info-item span{{font-size:14px;font-weight:600;color:#1e293b}}
table{{width:100%;border-collapse:collapse}}
table th{{text-align:left;font-size:12px;text-transform:uppercase;letter-spacing:1px;color:#94a3b8;padding:10px 0;border-bottom:2px solid #e2e8f0;font-weight:600}}
table td{{padding:14px 0;border-bottom:1px solid #f1f5f9;font-size:14px}}
table td:last-child,table th:last-child{{text-align:right}}
.total-row td{{border-bottom:none;padding-top:16px;font-size:16px;font-weight:700;color:#0ea5e9}}
.status{{display:inline-flex;align-items:center;gap:6px;padding:4px 12px;border-radius:20px;font-size:12px;font-weight:600}}
.status-paid{{background:#dcfce7;color:#166534}}
.status-pending{{background:#fef9c3;color:#854d0e}}
.doc-footer{{padding:24px 40px;background:#f8fafc;border-top:1px solid #e2e8f0;text-align:center}}
.doc-footer p{{font-size:12px;color:#94a3b8;line-height:1.6}}
.back-link{{display:inline-flex;align-items:center;justify-content:center;margin-top:16px;color:#2563eb;font-size:13px;font-weight:700;text-decoration:none}}
.actions{{display:flex;gap:12px;justify-content:center;margin-top:24px;flex-wrap:wrap;position:relative;z-index:2147483647}}
.act-btn{{display:inline-flex;align-items:center;gap:8px;padding:12px 28px;border-radius:10px;font-size:14px;font-weight:600;cursor:pointer;border:none;position:relative;z-index:2147483647;pointer-events:auto!important}}
.act-print{{background:linear-gradient(135deg,#2563eb,#4f46e5);color:#fff}}
.act-download{{background:linear-gradient(135deg,#4f46e5,#0891b2);color:#fff}}
.act-btn svg{{width:16px;height:16px;fill:currentColor;pointer-events:none}}
@media print{{.actions{{display:none!important}}body{{padding:0;background:#fff}}.doc{{box-shadow:none;border-radius:0}}}}
</style></head><body>
{fallback_banner}
<div class="doc"><div class="doc-header">{logo_block}<h1>{title}</h1><div class="meta"><span>{doc_num}</span><span>{date_str}</span></div></div>
<div class="doc-body"><div class="section"><div class="section-title">{('Facturé à' if doc_type == 'invoice' else 'Client') if is_fr else ('Billed To' if doc_type == 'invoice' else 'Customer')}</div><div class="info-grid"><div class="info-item"><label>{'Nom' if is_fr else 'Name'}</label><span>{user_name or ('Client' if is_fr else 'Customer')}</span></div><div class="info-item"><label>Email</label><span><!--email_off-->{user_email}<!--/email_off--></span></div></div></div>
<div class="section"><div class="section-title">{('Détails de la facture' if doc_type == 'invoice' else 'Détails du paiement') if is_fr else ('Invoice Details' if doc_type == 'invoice' else 'Payment Details')}</div><table><tr><th>Description</th><th>{'Montant' if is_fr else 'Amount'}</th></tr><tr><td>{"Prix de base de l'abonnement" if is_fr else 'Base Subscription Price'} — {plan_name} Plan ({billing.title()})</td><td>${subtotal:.2f}</td></tr><tr><td>{'Taxe applicable' if is_fr else 'Applicable Tax'} ({tax_jurisdiction} @ {tax_rate * 100:.2f}%)</td><td>${tax_amount:.2f}</td></tr><tr><td>{'Frais de traitement du paiement' if is_fr else 'Payment Processing Fee'}</td><td>${processing_fee:.2f}</td></tr><tr><td>{'Type de produit' if is_fr else 'Product Type'}</td><td>{product_type}</td></tr><tr class="total-row"><td>{'Total à payer' if is_fr else 'Total You Pay'}</td><td>${total_charged:.2f} USD</td></tr></table></div>
<div class="section"><div class="section-title">{'Informations de paiement' if is_fr else 'Payment Info'}</div><div class="info-grid"><div class="info-item"><label>{'Méthode' if is_fr else 'Method'}</label><span>{method_display}</span></div><div class="info-item"><label>{'Statut' if is_fr else 'Status'}</label><span class="status {status_class}">{status_display}</span></div><div class="info-item"><label>{'ID Transaction' if is_fr else 'Transaction ID'}</label><span style="font-size:12px;word-break:break-all">{payment_id}</span></div><div class="info-item"><label>Date</label><span>{date_str}</span></div></div></div>{explainability_html}</div>
<div class="doc-footer"><p>RealAICoach LLC &bull; <!--email_off-->support@realaicoach.app<!--/email_off--></p><p>Thank you for your subscription!</p><div class="actions" {download_url_attr}><button class="act-btn act-print" type="button" onclick="window.print();return false;">Print / Save as PDF</button>{download_btn}</div><a href="/payment-history" class="back-link">&larr; Back to Payment History</a></div></div></body></html>"""


async def _generate_pdf_from_payment(doc_type: str, payment: dict, user_name: str, user_email: str) -> bytes:
    from utils.receipt_generator import generate_pdf_from_payment

    try:
        snapshot = await _assert_plan_pricing_or_block(payment, context=f"pdf_generation_{doc_type}")
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    canonical_payment = _apply_canonical_plan_pricing(payment, snapshot)
    return generate_pdf_from_payment(doc_type, canonical_payment, user_name, user_email)


def _build_single_document_csv_text(doc_type: str, payment: dict, user_name: str, user_email: str) -> str:
    import csv
    import io

    payment_id = payment.get("payment_id") or payment.get("id") or ""
    transaction_id = payment.get("transaction_id") or payment_id
    created_at = payment.get("created_at")
    created_label = _format_payment_date_label(created_at, with_time=True)
    status_label = _format_payment_status_label(payment.get("status") or payment.get("payment_status") or "unknown")
    method_label = _format_payment_method_label(payment.get("payment_method"))
    plan_name = str(payment.get("plan_name") or _resolve_plan_name(payment.get("plan_id", "")))
    amount = float(payment.get("amount", 0) or 0)
    currency = str(payment.get("currency", "USD") or "USD").upper()
    tax_amount = float(payment.get("tax_amount", 0) or 0)
    fee_amount = float(payment.get("processing_fee", payment.get("fee", 0)) or 0)
    subtotal = float(payment.get("subtotal", amount) or amount)
    gross = float(payment.get("amount_gross", subtotal + tax_amount) or (subtotal + tax_amount))
    total = float(payment.get("total_amount", gross) or gross)
    amount_net = float(payment.get("amount_net", max(total - fee_amount, 0)) or max(total - fee_amount, 0))
    jurisdiction = payment.get("jurisdiction", {}) if isinstance(payment.get("jurisdiction"), dict) else {}
    jurisdiction_label = f"{jurisdiction.get('country', '')}-{jurisdiction.get('state', '')}".strip("-")
    tax_rate = float(payment.get("tax_rate", 0) or 0)
    product_type = _receipt_product_type_label(str(payment.get("product_type", "education_digital_service") or "education_digital_service"))

    doc_prefix = "INV" if doc_type == "invoice" else "RCT"
    try:
        created_dt = _parse_created_at(created_at) or datetime.now(timezone.utc)
        doc_id = f"{doc_prefix}-{created_dt.strftime('%Y%m%d')}-{str(payment_id)[:8].upper()}"
    except Exception:
        doc_id = f"{doc_prefix}-{str(payment_id)[:8].upper()}"

    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow([
        "Document Type", "Document ID", "Payment ID", "Transaction ID", "Timestamp", "User Name", "User Email",
        "Plan", "Currency", "Base Subscription Price", "Applicable Tax", "Tax Rate", "Tax Jurisdiction",
        "Product Type", "Payment Processing Fee", "Customer Charge Total", "Net Settlement After Fee", "Payment Method", "Status",
    ])
    writer.writerow([
        doc_type.title(), doc_id, payment_id, transaction_id, created_label, user_name or "", user_email or "",
        f"{plan_name} Plan", currency, f"{subtotal:.2f}", f"{tax_amount:.2f}", f"{tax_rate:.6f}", jurisdiction_label,
        product_type, f"{fee_amount:.2f}", f"{total:.2f}", f"{amount_net:.2f}", method_label, status_label,
    ])
    result = buffer.getvalue()
    buffer.close()
    return result


async def _verify_document_lookup(doc: str) -> tuple[dict | None, str | None]:
    parts = doc.split("-")
    if len(parts) < 3:
        return None, "Invalid document format."

    doc_type = parts[0]
    doc_date = parts[1]
    pay_prefix = "-".join(parts[2:])
    if doc_type not in ("RCT", "INV"):
        return None, "Invalid document type."

    all_payments = await db.payments.find(
        {"status": {"$in": ["completed", "succeeded", "paid"]}},
        {"_id": 0, "payment_id": 1, "created_at": 1, "amount": 1, "plan_id": 1, "email": 1, "user_id": 1},
    ).to_list(10000)
    for p in all_payments:
        pid = p.get("payment_id", "")
        if pid[:8].upper() != pay_prefix.upper():
            continue
        created = p.get("created_at", "")
        try:
            pdate = created.strftime("%Y%m%d") if isinstance(created, datetime) else str(created)[:10].replace("-", "")
        except Exception:
            pdate = ""
        if pdate == doc_date:
            return p, None
    return None, "No matching document found in our records."
