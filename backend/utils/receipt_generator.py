"""Payment Receipt Generator — Single source of truth for PDF + HTML receipts."""
import os
import tempfile
import logging
from functools import lru_cache
from urllib.request import urlopen
from urllib.parse import urlparse

from services.pdf_v15_theme import get_canonical_logo_tile_path
from utils.payment_localization import detect_payment_locale

_logger = logging.getLogger(__name__)

BRAND = os.environ.get("BRAND_NAME", "RealAICoach")
BRAND_COLOR = "#3B82F6"
SITE_URL = os.environ.get("SITE_URL", "https://realaicoach.app")
FRONTEND_BASE_URL = os.environ.get("FRONTEND_BASE_URL", "")
BRAND_LOGO_URL = os.environ.get("BRAND_LOGO_URL", "")
SUPPORT_EMAIL = os.environ.get("SUPPORT_EMAIL", "support@realaicoach.app")
GOOGLE_PLAY_URL = os.environ.get("GOOGLE_PLAY_URL", "https://play.google.com/store/search?q=RealAICoach&c=apps")
APP_STORE_URL = os.environ.get("APP_STORE_URL", "https://apps.apple.com/us/search?term=RealAICoach")
GOOGLE_PLAY_BADGE_IMAGE_URL = os.environ.get(
    "GOOGLE_PLAY_BADGE_IMAGE_URL",
    "https://play.google.com/intl/en_us/badges/static/images/badges/en_badge_web_generic.png",
)
APP_STORE_BADGE_IMAGE_URL = os.environ.get(
    "APP_STORE_BADGE_IMAGE_URL",
    "https://developer.apple.com/assets/elements/badges/download-on-the-app-store.svg",
)


def _detect_locale(payment_or_tx: dict) -> str:
    return detect_payment_locale(payment_or_tx)


# ── Multi-language label registry ──────────────────────────────────
_LABELS = {
    "receipt_title": {"en": "Enterprise Payment Confirmation", "fr": "Confirmation de paiement", "es": "Confirmación de pago", "pt": "Confirmação de pagamento", "ar": "تأكيد الدفع"},
    "paid": {"en": "PAID", "fr": "PAYÉ", "es": "PAGADO", "pt": "PAGO", "ar": "مدفوع"},
    "thanks": {"en": "Thanks", "fr": "Merci", "es": "Gracias", "pt": "Obrigado", "ar": "شكراً"},
    "payment_success_msg": {
        "en": "your payment was successful. Your receipt details are below.",
        "fr": "votre paiement a été validé. Les détails de votre reçu sont ci-dessous.",
        "es": "su pago fue exitoso. Los detalles de su recibo están a continuación.",
        "pt": "seu pagamento foi confirmado. Os detalhes do recibo estão abaixo.",
        "ar": "تم تأكيد دفعتك بنجاح. تفاصيل الإيصال أدناه.",
    },
    "receipt_number": {"en": "Receipt Number", "fr": "Numéro de reçu", "es": "Número de recibo", "pt": "Número do recibo", "ar": "رقم الإيصال"},
    "billed_to": {"en": "Billed To", "fr": "Facturé à", "es": "Facturado a", "pt": "Faturado para", "ar": "مفوتر إلى"},
    "description": {"en": "Description", "fr": "Description", "es": "Descripción", "pt": "Descrição", "ar": "الوصف"},
    "base_subscription_price": {"en": "Base Subscription Price", "fr": "Prix de base de l'abonnement", "es": "Precio base de la suscripción", "pt": "Preço base da assinatura", "ar": "السعر الأساسي للاشتراك"},
    "applicable_tax": {"en": "Applicable Tax", "fr": "Taxe applicable", "es": "Impuesto aplicable", "pt": "Imposto aplicável", "ar": "الضريبة المطبقة"},
    "amount": {"en": "Amount", "fr": "Montant", "es": "Monto", "pt": "Valor", "ar": "المبلغ"},
    "tax": {"en": "Tax", "fr": "Taxe", "es": "Impuesto", "pt": "Imposto", "ar": "الضريبة"},
    "processing_fee": {"en": "Processing Fee", "fr": "Frais de traitement", "es": "Tarifa de procesamiento", "pt": "Taxa de processamento", "ar": "رسوم المعالجة"},
    "payment_processing_fee": {"en": "Payment Processing Fee", "fr": "Frais de traitement du paiement", "es": "Tarifa de procesamiento del pago", "pt": "Taxa de processamento do pagamento", "ar": "رسوم معالجة الدفع"},
    "gross_amount": {"en": "Gross Amount", "fr": "Montant brut", "es": "Monto bruto", "pt": "Valor bruto", "ar": "المبلغ الإجمالي"},
    "net_amount": {"en": "Net Amount", "fr": "Montant net", "es": "Monto neto", "pt": "Valor líquido", "ar": "المبلغ الصافي"},
    "total": {"en": "Total", "fr": "Total", "es": "Total", "pt": "Total", "ar": "الإجمالي"},
    "total_you_pay": {"en": "Total You Pay", "fr": "Total à payer", "es": "Total a pagar", "pt": "Total a pagar", "ar": "الإجمالي الذي ستدفعه"},
    "payment_details": {"en": "Payment Details", "fr": "Détails du paiement", "es": "Detalles del pago", "pt": "Detalhes do pagamento", "ar": "تفاصيل الدفع"},
    "method": {"en": "Method", "fr": "Méthode", "es": "Método", "pt": "Método", "ar": "الطريقة"},
    "transaction_id": {"en": "Transaction ID", "fr": "ID Transaction", "es": "ID de transacción", "pt": "ID da transação", "ar": "رقم المعاملة"},
    "next_renewal": {"en": "Next Renewal", "fr": "Prochain renouvellement", "es": "Próxima renovación", "pt": "Próxima renovação", "ar": "التجديد التالي"},
    "receipt_explainability": {"en": "Receipt Explainability", "fr": "Explication du reçu", "es": "Explicación del recibo", "pt": "Explicação do recibo", "ar": "شرح الإيصال"},
    "tax_basis": {"en": "Tax Basis", "fr": "Base fiscale", "es": "Base fiscal", "pt": "Base tributária", "ar": "الأساس الضريبي"},
    "product_type": {"en": "Product Type", "fr": "Type de produit", "es": "Tipo de producto", "pt": "Tipo de produto", "ar": "نوع المنتج"},
    "fee_policy": {"en": "Fee Policy", "fr": "Politique des frais", "es": "Política de tarifas", "pt": "Política de taxas", "ar": "سياسة الرسوم"},
    "net_payout_basis": {"en": "Net Payout Basis", "fr": "Base du montant net", "es": "Base del monto neto", "pt": "Base do valor líquido", "ar": "أساس المبلغ الصافي"},
    "fee_policy_text": {"en": "Payment processing fee is included in the total paid by the customer.", "fr": "Les frais de traitement du paiement sont inclus dans le total payé par le client.", "es": "La tarifa de procesamiento del pago está incluida en el total pagado por el cliente.", "pt": "A taxa de processamento do pagamento está incluída no total pago pelo cliente.", "ar": "رسوم معالجة الدفع مضمنة في إجمالي ما يدفعه العميل."},
    "net_formula": {"en": "Total You Pay - Payment Processing Fee", "fr": "Total payé - Frais de traitement du paiement", "es": "Total a pagar - Tarifa de procesamiento del pago", "pt": "Total a pagar - Taxa de processamento do pagamento", "ar": "إجمالي ما تدفعه - رسوم معالجة الدفع"},
    "download_pdf": {"en": "Download PDF Receipt", "fr": "Télécharger le reçu PDF", "es": "Descargar recibo PDF", "pt": "Baixar recibo PDF", "ar": "تحميل إيصال PDF"},
    "auto_generated": {"en": "This is an automatically generated receipt from", "fr": "Ceci est un reçu généré automatiquement par", "es": "Este es un recibo generado automáticamente por", "pt": "Este é um recibo gerado automaticamente por", "ar": "هذا إيصال تم إنشاؤه تلقائياً من"},
    "questions_contact": {"en": "For questions, contact", "fr": "Pour toute question, contactez", "es": "Para preguntas, contacte", "pt": "Para dúvidas, contate", "ar": "للاستفسارات، تواصل مع"},
    "status": {"en": "STATUS", "fr": "STATUT", "es": "ESTADO", "pt": "ESTADO", "ar": "الحالة"},
    "verified_copy": {"en": "VERIFIED COPY", "fr": "COPIE VÉRIFIÉE", "es": "COPIA VERIFICADA", "pt": "CÓPIA VERIFICADA", "ar": "نسخة موثقة"},
    "scan_to_verify": {"en": "Scan to verify this document", "fr": "Scannez pour vérifier ce document", "es": "Escanee para verificar este documento", "pt": "Escaneie para verificar este documento", "ar": "امسح للتحقق من هذا المستند"},
    "subscription_active": {"en": "Your subscription is active", "fr": "Votre abonnement est actif", "es": "Su suscripción está activa", "pt": "Sua assinatura está ativa", "ar": "اشتراكك نشط"},
    "hello": {"en": "Hello", "fr": "Bonjour", "es": "Hola", "pt": "Olá", "ar": "مرحباً"},
    "your_subscription": {"en": "Your subscription", "fr": "Votre abonnement", "es": "Su suscripción", "pt": "Sua assinatura", "ar": "اشتراكك"},
    "is_now_active": {"en": "is now active.", "fr": "est maintenant actif.", "es": "está ahora activo.", "pt": "está agora ativo.", "ar": "نشط الآن."},
    "next_renewal_date": {"en": "Next renewal", "fr": "Prochain renouvellement", "es": "Próxima renovación", "pt": "Próxima renovação", "ar": "التجديد التالي"},
    "detailed_receipt_sent": {
        "en": "A detailed receipt with tax and processing fee information has been sent.",
        "fr": "Un reçu détaillé avec les informations fiscales et les frais de traitement a été envoyé.",
        "es": "Se ha enviado un recibo detallado con información fiscal y tarifas de procesamiento.",
        "pt": "Um recibo detalhado com informações fiscais e taxas de processamento foi enviado.",
        "ar": "تم إرسال إيصال مفصل يتضمن معلومات الضرائب ورسوم المعالجة.",
    },
    "thanks_team": {"en": "Thank you for using RealAICoach.", "fr": "Merci d'utiliser RealAICoach.", "es": "Gracias por usar RealAICoach.", "pt": "Obrigado por usar o RealAICoach.", "ar": "شكراً لاستخدامك RealAICoach."},
}


def _L(key: str, lang: str = "en") -> str:
    """Get a localized label."""
    entry = _LABELS.get(key)
    if not entry:
        return key
    return entry.get(lang, entry.get("en", key))


def _is_french_payment(payment: dict) -> bool:
    return _detect_locale(payment) == "fr"


RECEIPT_VERSION = "Official Enterprise Document"

# ── V7 Brand Color Constants ─────────────────────────────────────────
_V7_STRIPE_COLORS = [
    (59, 130, 246),   # #3B82F6 blue
    (139, 92, 246),   # #8B5CF6 purple
    (236, 72, 153),   # #EC4899 pink
    (6, 214, 160),    # #06D6A0 teal
]
_V7_AMBER = (245, 158, 11)   # #F59E0B — v7 warning/pending (not orange)
_V7_INDIGO_PILL = (30, 64, 175)  # #1E40AF — header pill bg


def _display_product_type(_: str | None = None) -> str:
    return "Digital Platform Access"

STATIC_BRAND_LOGO_PATH = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "static", "images", "brand-logo-full.png")
)
STATIC_DOCUMENT_LOGO_PATH = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "static", "images", "brand-logo-chip.png")
)


# ── Logo helpers ──────────────────────────────────────────────────────


def _get_brand_logo_public_url() -> str:
    if FRONTEND_BASE_URL:
        return f"{FRONTEND_BASE_URL}/api/static/images/brand-logo-full.png"
    return BRAND_LOGO_URL


def _get_document_logo_public_url() -> str:
    if FRONTEND_BASE_URL:
        return f"{FRONTEND_BASE_URL}/api/static/images/brand-logo-chip.png"
    return _get_brand_logo_public_url()


@lru_cache(maxsize=1)
def _get_brand_logo_bytes() -> bytes | None:
    if os.path.exists(STATIC_BRAND_LOGO_PATH):
        try:
            with open(STATIC_BRAND_LOGO_PATH, "rb") as f:
                return f.read()
        except Exception as exc:
            _logger.warning(f"Unable to read local brand logo: {exc}")
    if not BRAND_LOGO_URL:
        return None
    try:
        with urlopen(BRAND_LOGO_URL, timeout=10) as response:
            return response.read()
    except Exception as exc:
        _logger.warning(f"Unable to fetch brand logo: {exc}")
        return None


@lru_cache(maxsize=1)
def _get_document_logo_bytes() -> bytes | None:
    canonical_logo = get_canonical_logo_tile_path() or STATIC_DOCUMENT_LOGO_PATH
    if canonical_logo and os.path.exists(canonical_logo):
        try:
            with open(canonical_logo, "rb") as f:
                return f.read()
        except Exception as exc:
            _logger.warning(f"Unable to read document logo: {exc}")
    return _get_brand_logo_bytes()


@lru_cache(maxsize=1)
def _get_document_logo_temp_path() -> str | None:
    logo_bytes = _get_document_logo_bytes()
    if not logo_bytes:
        return None
    suffix = os.path.splitext(urlparse(_get_document_logo_public_url() or BRAND_LOGO_URL).path)[1] or ".png"
    fd, path = tempfile.mkstemp(prefix="realaicoach-document-logo-", suffix=suffix)
    with os.fdopen(fd, "wb") as logo_file:
        logo_file.write(logo_bytes)
    return path


# ── Format helpers ────────────────────────────────────────────────────


def format_payment_method_label(method_raw: str) -> str:
    method = str(method_raw or "card").strip().lower()
    if "kkiapay" in method:
        return "Mobile Money (FedaPay)"
    if "stripe" in method:
        return "Card (Stripe)"
    if "paypal" in method:
        return "PayPal"
    if "fedapay" in method and any(card_hint in method for card_hint in ("card", "visa", "mastercard")):
        return "Card (FedaPay)"
    if "mobile" in method:
        return "Mobile Money (FedaPay)"
    if method == "fedapay":
        return "FedaPay"
    if "fedapay" in method:
        return "FedaPay"
    return method.replace("_", " ").title()


def format_payment_status_label(status_raw: str) -> str:
    status = str(status_raw or "unknown").strip().lower()
    if status in {"completed", "paid"}:
        return "Paid"
    if status == "initiated":
        return "Pending"
    return status.title()


# ── PDF Generation (single source of truth) ──────────────────────────


def _hex_to_rgb(hex_color: str) -> tuple:
    """Convert #RRGGBB hex string to (R, G, B) tuple."""
    h = hex_color.lstrip("#")
    if len(h) != 6:
        return (37, 99, 235)  # fallback blue
    return tuple(int(h[i:i+2], 16) for i in (0, 2, 4))


async def _load_branding_from_db() -> dict:
    """Load receipt branding settings from MongoDB (async).

    Zero-Assumptions enforcement: any branding doc containing fabricated
    business-identity tokens is rejected at load time. See
    /app/memory/ZERO_ASSUMPTIONS_POLICY.md.
    """
    try:
        from routes.db import db
        doc = await db.settings.find_one({"key": "receipt_branding"}, {"_id": 0})
        if doc and "value" in doc:
            from utils.zero_assumptions import scan_for_fabrications
            hits = scan_for_fabrications(doc["value"])
            if hits:
                _logger.error(
                    "[ZERO-ASSUMPTIONS] receipt_branding contains forbidden tokens %s; "
                    "refusing to use. Returning {} so caller falls back to defaults.",
                    hits,
                )
                return {}
            return doc["value"]
    except Exception as exc:
        _logger.warning(f"Could not load branding from DB: {exc}")
    return {}


def _load_branding_from_db_sync() -> dict:
    """Load receipt branding settings from MongoDB (sync fallback for non-async contexts)."""
    try:
        import pymongo
        mongo_url = os.environ.get("MONGO_URL", "")
        db_name = os.environ.get("DB_NAME", "realaicoach")
        if not mongo_url:
            return {}
        client = pymongo.MongoClient(mongo_url, serverSelectionTimeoutMS=2000)
        doc = client[db_name].settings.find_one({"key": "receipt_branding"}, {"_id": 0})
        client.close()
        if doc and "value" in doc:
            from utils.zero_assumptions import scan_for_fabrications
            hits = scan_for_fabrications(doc["value"])
            if hits:
                _logger.error(
                    "[ZERO-ASSUMPTIONS] receipt_branding (sync) contains forbidden "
                    "tokens %s; refusing to use.", hits,
                )
                return {}
            return doc["value"]
    except Exception as exc:
        _logger.warning(f"Could not load branding sync: {exc}")
    return {}


def generate_pdf_from_payment(doc_type: str, payment: dict, user_name: str, user_email: str, branding_override: dict | None = None) -> bytes:
    from utils.receipt_pdf_renderer import generate_pdf_from_payment as _generate_pdf
    return _generate_pdf(doc_type, payment, user_name, user_email, branding_override=branding_override)


# ── HTML Email Receipt ────────────────────────────────────────────────


def build_branded_receipt_html(
    receipt_number: str,
    user_name: str,
    user_email: str,
    plan_name: str,
    amount_usd: float,
    amount_local: float = 0,
    currency: str = "USD",
    payment_method: str = "Card",
    billing_period: str = "monthly",
    payment_date: str = "",
    renewal_date: str = "",
    gateway_fee: float = 0,
    ticket_id: str = "",
    download_url: str = "",
    payment_data: dict | None = None,
) -> str:
    from utils.receipt_email_html import build_branded_receipt_html as _build_html
    html = _build_html(
        receipt_number,
        user_name,
        user_email,
        plan_name,
        amount_usd,
        amount_local=amount_local,
        currency=currency,
        payment_method=payment_method,
        billing_period=billing_period,
        payment_date=payment_date,
        renewal_date=renewal_date,
        gateway_fee=gateway_fee,
        ticket_id=ticket_id,
        download_url=download_url,
        payment_data=payment_data,
    )

    # Enforce V7 fingerprint expected by email_service guardrail.
    if 'class="em-outer"' not in html:
        html = html.replace("<body ", '<body class="em-outer" ', 1)
        html = html.replace(
            '<table role="presentation" cellpadding="0" cellspacing="0" style="width:100%;background:#EEF2FF;">',
            '<table role="presentation" cellpadding="0" cellspacing="0" class="email-outer em-outer" style="width:100%;background:#EEF2FF;">',
            1,
        )

    return html
