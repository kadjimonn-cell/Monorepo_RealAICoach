"""Home Dashboard API — Real-time stats, charts, activity feed for the enterprise home page."""

from fastapi import APIRouter, Request
from datetime import datetime, timezone, timedelta
from .db import db, get_current_user
from pydantic import BaseModel, Field
import random
from utils.access_control_engine import compute_effective_plan

router = APIRouter(prefix="/home", tags=["Home Dashboard"])


class NovaBubblePositionPayload(BaseModel):
    x: float = Field(..., ge=0)
    y: float = Field(..., ge=0)
    viewport_width: float | None = Field(default=None, gt=0)
    viewport_height: float | None = Field(default=None, gt=0)

# ── Static translation maps for dashboard strings ──
# Keys are English originals; values are {lang_code: translation}.
# These cover the most-visible user-facing strings returned by dashboard APIs.
_CATEGORY_TRANSLATIONS = {
    "Career":   {"fr": "Carrière", "es": "Carrera", "de": "Karriere", "pt": "Carreira", "ar": "مهنة", "zh": "职业", "ja": "キャリア", "ko": "경력", "it": "Carriera", "nl": "Carrière", "ru": "Карьера", "tr": "Kariyer", "pl": "Kariera", "sv": "Karriär", "hi": "करियर"},
    "Health":   {"fr": "Santé", "es": "Salud", "de": "Gesundheit", "pt": "Saúde", "ar": "صحة", "zh": "健康", "ja": "健康", "ko": "건강", "it": "Salute", "nl": "Gezondheid", "ru": "Здоровье", "tr": "Sağlık", "pl": "Zdrowie", "sv": "Hälsa", "hi": "स्वास्थ्य"},
    "Finance":  {"fr": "Finance", "es": "Finanzas", "de": "Finanzen", "pt": "Finanças", "ar": "مالية", "zh": "金融", "ja": "金融", "ko": "금융", "it": "Finanza", "nl": "Financiën", "ru": "Финансы", "tr": "Finans", "pl": "Finanse", "sv": "Ekonomi", "hi": "वित्त"},
    "Learning": {"fr": "Apprentissage", "es": "Aprendizaje", "de": "Lernen", "pt": "Aprendizado", "ar": "تعلم", "zh": "学习", "ja": "学習", "ko": "학습", "it": "Apprendimento", "nl": "Leren", "ru": "Обучение", "tr": "Öğrenme", "pl": "Nauka", "sv": "Lärande", "hi": "सीखना"},
    "Wellness": {"fr": "Bien-être", "es": "Bienestar", "de": "Wohlbefinden", "pt": "Bem-estar", "ar": "عافية", "zh": "健身", "ja": "ウェルネス", "ko": "웰빙", "it": "Benessere", "nl": "Welzijn", "ru": "Благополучие", "tr": "Sağlık", "pl": "Dobrostan", "sv": "Välbefinnande", "hi": "कल्याण"},
    "General":  {"fr": "Général", "es": "General", "de": "Allgemein", "pt": "Geral", "ar": "عام", "zh": "通用", "ja": "一般", "ko": "일반", "it": "Generale", "nl": "Algemeen", "ru": "Общий", "tr": "Genel", "pl": "Ogólne", "sv": "Allmänt", "hi": "सामान्य"},
}

_ACTIVITY_TRANSLATIONS = {
    "AI Session Completed":  {"fr": "Session IA Terminée", "es": "Sesión IA Completada", "de": "KI-Sitzung Abgeschlossen"},
    "Smart coaching session finished successfully": {"fr": "Session de coaching intelligent terminée avec succès", "es": "Sesión de coaching inteligente completada con éxito", "de": "Intelligente Coaching-Sitzung erfolgreich abgeschlossen"},
    "Goal Milestone":        {"fr": "Jalon d'Objectif", "es": "Hito de Objetivo", "de": "Ziel-Meilenstein"},
    "FPS Streak Milestone":  {"fr": "Série de Victoires FPS", "es": "Racha de Victorias FPS", "de": "FPS-Siegesserie"},
    "New performance milestone reached": {"fr": "Nouveau jalon de performance atteint", "es": "Nuevo hito de rendimiento alcanzado", "de": "Neuer Leistungsmeilenstein erreicht"},
    "Platform Update":       {"fr": "Mise à Jour Plateforme", "es": "Actualización de Plataforma", "de": "Plattform-Update"},
    "New AI models deployed for better coaching": {"fr": "Nouveaux modèles IA déployés pour un meilleur coaching", "es": "Nuevos modelos de IA implementados para mejor coaching", "de": "Neue KI-Modelle für besseres Coaching bereitgestellt"},
    "Coach Available":       {"fr": "Coach Disponible", "es": "Coach Disponible", "de": "Coach Verfügbar"},
    "New coaching slot opened for today": {"fr": "Nouveau créneau de coaching ouvert pour aujourd'hui", "es": "Nuevo espacio de coaching abierto para hoy", "de": "Neuer Coaching-Termin für heute verfügbar"},
    "Weekly Insight":        {"fr": "Insight Hebdomadaire", "es": "Análisis Semanal", "de": "Wöchentlicher Einblick"},
    "Your productivity score increased by 12%": {"fr": "Votre score de productivité a augmenté de 12%", "es": "Tu puntuación de productividad aumentó un 12%", "de": "Ihre Produktivitätsbewertung stieg um 12%"},
    "Payment E2E Daily Digest": {"fr": "Résumé quotidien des paiements E2E", "es": "Resumen diario de pagos E2E", "de": "Tägliche Zahlungsübersicht E2E"},
    "Payment not completed": {"fr": "Paiement non finalisé", "es": "Pago no completado", "de": "Zahlung nicht abgeschlossen"},
    "Admin Alert - Payment Failed": {"fr": "Alerte admin - Paiement échoué", "es": "Alerta de administrador - Pago fallido", "de": "Admin-Warnung - Zahlung fehlgeschlagen"},
    "Email Notification Cap Blocked": {"fr": "Limite d'e-mails atteinte", "es": "Límite de notificaciones por correo alcanzado", "de": "E-Mail-Benachrichtigungslimit erreicht"},
    "10/10 checks passed · severity HEALTHY": {"fr": "10/10 vérifications réussies · niveau SAIN", "es": "10/10 verificaciones aprobadas · estado SALUDABLE", "de": "10/10 Prüfungen bestanden · Status GESUND"},
    "Stripe could not complete your payment. No charge was completed. Try again or choose a different method.": {"fr": "Stripe n'a pas pu finaliser votre paiement. Aucun débit n'a été effectué. Réessayez ou choisissez une autre méthode.", "es": "Stripe no pudo completar tu pago. No se realizó ningún cargo. Inténtalo de nuevo o elige otro método.", "de": "Stripe konnte Ihre Zahlung nicht abschließen. Es wurde keine Belastung vorgenommen. Bitte versuchen Sie es erneut oder wählen Sie eine andere Methode."},
    "Blocked >2 sends for template 'user_notification_alert' to '{email}'. count=2": {"fr": "Plus de 2 envois bloqués pour le modèle 'user_notification_alert' vers '{email}'. total=2", "es": "Más de 2 envíos bloqueados para la plantilla 'user_notification_alert' a '{email}'. total=2", "de": "Mehr als 2 Sendungen für die Vorlage 'user_notification_alert' an '{email}' blockiert. Anzahl=2"},
}

_CHECKLIST_TRANSLATIONS = {
    "Complete Your Profile":  {"fr": "Complétez Votre Profil", "es": "Completa Tu Perfil", "de": "Profil Vervollständigen"},
    "Start First AI Session": {"fr": "Démarrer Première Session IA", "es": "Iniciar Primera Sesión IA", "de": "Erste KI-Sitzung Starten"},
    "Set a Goal":             {"fr": "Définir un Objectif", "es": "Establecer un Objetivo", "de": "Ziel Setzen"},
    "Explore Coaching Tools":  {"fr": "Explorer les Outils de Coaching", "es": "Explorar Herramientas de Coaching", "de": "Coaching-Tools Erkunden"},
    "Complete Onboarding Tour": {"fr": "Terminer la Visite Guidée", "es": "Completar el Tour de Inicio", "de": "Einführungstour Abschließen"},
}

_DAY_TRANSLATIONS = {
    "Mon": {"fr": "Lun", "es": "Lun", "de": "Mo", "pt": "Seg", "it": "Lun", "nl": "Ma", "ru": "Пн", "zh": "周一", "ja": "月", "ko": "월", "ar": "اثن", "tr": "Pzt", "pl": "Pon", "sv": "Mån", "hi": "सोम"},
    "Tue": {"fr": "Mar", "es": "Mar", "de": "Di", "pt": "Ter", "it": "Mar", "nl": "Di", "ru": "Вт", "zh": "周二", "ja": "火", "ko": "화", "ar": "ثلا", "tr": "Sal", "pl": "Wt", "sv": "Tis", "hi": "मंगल"},
    "Wed": {"fr": "Mer", "es": "Mié", "de": "Mi", "pt": "Qua", "it": "Mer", "nl": "Wo", "ru": "Ср", "zh": "周三", "ja": "水", "ko": "수", "ar": "أرب", "tr": "Çar", "pl": "Śr", "sv": "Ons", "hi": "बुध"},
    "Thu": {"fr": "Jeu", "es": "Jue", "de": "Do", "pt": "Qui", "it": "Gio", "nl": "Do", "ru": "Чт", "zh": "周四", "ja": "木", "ko": "목", "ar": "خمي", "tr": "Per", "pl": "Czw", "sv": "Tor", "hi": "गुरु"},
    "Fri": {"fr": "Ven", "es": "Vie", "de": "Fr", "pt": "Sex", "it": "Ven", "nl": "Vr", "ru": "Пт", "zh": "周五", "ja": "金", "ko": "금", "ar": "جمع", "tr": "Cum", "pl": "Pt", "sv": "Fre", "hi": "शुक्र"},
    "Sat": {"fr": "Sam", "es": "Sáb", "de": "Sa", "pt": "Sáb", "it": "Sab", "nl": "Za", "ru": "Сб", "zh": "周六", "ja": "土", "ko": "토", "ar": "سبت", "tr": "Cmt", "pl": "Sob", "sv": "Lör", "hi": "शनि"},
    "Sun": {"fr": "Dim", "es": "Dom", "de": "So", "pt": "Dom", "it": "Dom", "nl": "Zo", "ru": "Вс", "zh": "周日", "ja": "日", "ko": "일", "ar": "أحد", "tr": "Paz", "pl": "Ndz", "sv": "Sön", "hi": "रवि"},
}


def _localize(text: str, lang: str, table: dict) -> str:
    """Look up a static translation. Returns original text if no translation found."""
    if lang == "en" or not lang:
        return text
    entry = table.get(text)
    if entry and lang in entry:
        return entry[lang]
    return text


def _extract_lang(request: Request) -> str:
    """Extract language code from query param or Accept-Language header."""
    lang = request.query_params.get("lang", "").strip().lower()[:5]
    if lang:
        return lang
    accept = request.headers.get("accept-language", "")
    if accept:
        primary = accept.split(",")[0].split(";")[0].strip().lower()
        if "-" in primary:
            primary = primary.split("-")[0]
        return primary
    return "en"


def _sanitize_activity_copy(title: str, message: str) -> tuple[str, str]:
    safe_title = str(title or "Activity").strip() or "Activity"
    safe_message = str(message or "").strip()
    if safe_title == "Email Notification Cap Blocked":
        safe_message = "More than two duplicate notification emails were blocked for the same recipient."
    elif safe_title == "Admin Alert - Payment Failed":
        safe_message = "A recent plan payment needs attention. Please review payment details or try another method."
    elif safe_title == "Payment E2E Daily Digest":
        safe_message = "Daily payment health checks completed successfully."
    return safe_title, safe_message

# ── Vanity Metrics (shared across Welcome, Login, Home) ──
_vanity_cache = {"ts": 0, "data": None}
VANITY_TTL = 45  # seconds
_vanity_stream_cache = {"ts": 0, "data": None}
VANITY_STREAM_TTL = 3  # seconds

_VANITY_BOUNDS = {
    "active_users": (2400, 3800),
    "ai_sessions_today": (1200, 2800),
    "global_coaches": (180, 420),
    "performance_boost": (34, 67),
    "users_online": (890, 1650),
    "system_health": (99.2, 99.9),
}

_VANITY_STEPS = {
    "active_users": 4,          # monotonic: +0..4 per tick (was ±68 → caused visible "3,611 → 3,607" drops)
    "ai_sessions_today": 6,     # monotonic: +0..6 per tick (was ±74)
    "global_coaches": 1,        # monotonic: +0..1 per tick (was ±9 → "397 → 395" drops)
    "performance_boost": 1,     # gauge: ±1 (natural avg oscillation)
    "users_online": 12,         # gauge: ±12 (users legitimately come/go)
    "system_health": 0.1,       # gauge: ±0.1 (health ebbs slightly)
}

# Keys that must only ever grow on successive stream ticks (cumulative / social-proof
# counters — seeing them go DOWN looks like a data bug to end users and shows up as
# "Welcome page is glitching"). All other keys in _VANITY_STEPS are symmetric gauges.
_VANITY_MONOTONIC = {"active_users", "ai_sessions_today", "global_coaches"}


def _clamp_metric(value, lower, upper):
    return max(lower, min(upper, value))


def _next_stream_metric(key: str, current):
    lower, upper = _VANITY_BOUNDS[key]
    step = _VANITY_STEPS[key]
    monotonic = key in _VANITY_MONOTONIC

    if isinstance(lower, float) or isinstance(upper, float):
        delta = random.uniform(0, step) if monotonic else random.uniform(-step, step)
        next_value = round(_clamp_metric(float(current) + delta, float(lower), float(upper)), 1)
        return next_value

    delta = random.randint(0, int(step)) if monotonic else random.randint(-int(step), int(step))
    next_value = int(_clamp_metric(int(current) + delta, int(lower), int(upper)))
    return next_value


def _generate_stream_vanity_metrics():
    """Generate low-latency live vanity metrics with mild up/down movement."""
    import time

    now = time.time()
    if _vanity_stream_cache["data"] and (now - _vanity_stream_cache["ts"]) < VANITY_STREAM_TTL:
        return _vanity_stream_cache["data"]

    previous = _vanity_stream_cache["data"] or _generate_vanity_metrics()

    data = {
        "active_users": _next_stream_metric("active_users", previous.get("active_users", 2800)),
        "ai_sessions_today": _next_stream_metric("ai_sessions_today", previous.get("ai_sessions_today", 1500)),
        "global_coaches": _next_stream_metric("global_coaches", previous.get("global_coaches", 280)),
        "performance_boost": _next_stream_metric("performance_boost", previous.get("performance_boost", 47)),
        "users_online": _next_stream_metric("users_online", previous.get("users_online", 1200)),
        "system_health": _next_stream_metric("system_health", previous.get("system_health", 99.5)),
        "ttl": VANITY_STREAM_TTL,
        "mode": "stream",
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }

    _vanity_stream_cache["ts"] = now
    _vanity_stream_cache["data"] = data
    return data


def _generate_vanity_metrics(stream: bool = False):
    """Generate impressive random platform metrics."""
    if stream:
        return _generate_stream_vanity_metrics()

    import time

    now = time.time()
    if _vanity_cache["data"] and (now - _vanity_cache["ts"]) < VANITY_TTL:
        return _vanity_cache["data"]

    data = {
        "active_users": random.randint(2400, 3800),
        "ai_sessions_today": random.randint(1200, 2800),
        "global_coaches": random.randint(180, 420),
        "performance_boost": random.randint(34, 67),
        "users_online": random.randint(890, 1650),
        "system_health": round(random.uniform(99.2, 99.9), 1),
        "ttl": VANITY_TTL,
        "mode": "standard",
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
    _vanity_cache["ts"] = now
    _vanity_cache["data"] = data
    return data


def _parse_iso_datetime(value):
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if value is None:
        return None
    raw = str(value).strip()
    if not raw:
        return None
    normalized = raw.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    except Exception:
        return None


@router.get("/dashboard-stats")
async def get_dashboard_stats(request: Request):
    """Real-time dashboard statistics for the home page hero section."""
    user = await get_current_user(request)
    if not user:
        from fastapi.responses import JSONResponse
        return JSONResponse(status_code=401, content={"detail": "Authentication required"})
    now = datetime.now(timezone.utc)
    vanity = _generate_vanity_metrics()

    # Admin-set overrides from platform_stats take precedence
    try:
        admin_stats = await db.platform_stats.find_one({"key": "global"}, {"_id": 0})
    except Exception:
        admin_stats = None

    try:
        total_users = await db.users.count_documents({})
    except Exception:
        total_users = 0

    return {
        "active_users": (admin_stats or {}).get("active_users") or vanity["active_users"],
        "total_users": max(total_users, 1),
        "ai_sessions_today": (admin_stats or {}).get("ai_sessions_today") or vanity["ai_sessions_today"],
        "total_sessions": 0,
        "performance_boost": (admin_stats or {}).get("performance_boost") or vanity["performance_boost"],
        "global_coaches": (admin_stats or {}).get("global_coaches") or vanity["global_coaches"],
        "ai_status": (admin_stats or {}).get("ai_status") or "online",
        "timestamp": now.isoformat(),
    }


@router.get("/dashboard")
async def get_dashboard_stats_alias(request: Request):
    """Compatibility alias for legacy /api/home/dashboard clients."""
    return await get_dashboard_stats(request)


@router.get("/chart-data")
async def get_chart_data(request: Request):
    """Chart data for the home page dashboard preview."""
    lang = _extract_lang(request)
    now = datetime.now(timezone.utc)
    days_labels = []
    ai_performance = []
    user_growth = []

    for i in range(6, -1, -1):
        day = now - timedelta(days=i)
        label = day.strftime("%a")
        days_labels.append(_localize(label, lang, _DAY_TRANSLATIONS))

        day_start = day.replace(hour=0, minute=0, second=0, microsecond=0)
        day_end = day_start + timedelta(days=1)

        try:
            count = await db.conversations.count_documents(
                {"created_at": {"$gte": day_start.isoformat(), "$lt": day_end.isoformat()}}
            )
        except Exception:
            count = 0
        ai_performance.append(max(count, random.randint(2, 8) if count == 0 else count))

        try:
            ucount = await db.users.count_documents(
                {"created_at": {"$gte": day_start.isoformat(), "$lt": day_end.isoformat()}}
            )
        except Exception:
            ucount = 0
        user_growth.append(max(ucount, random.randint(1, 5) if ucount == 0 else ucount))

    # Coaching categories distribution
    categories = [
        {"name": _localize("Career", lang, _CATEGORY_TRANSLATIONS), "value": 35, "color": "#3B82F6"},
        {"name": _localize("Health", lang, _CATEGORY_TRANSLATIONS), "value": 20, "color": "#10B981"},
        {"name": _localize("Finance", lang, _CATEGORY_TRANSLATIONS), "value": 18, "color": "#8B5CF6"},
        {"name": _localize("Learning", lang, _CATEGORY_TRANSLATIONS), "value": 15, "color": "#F59E0B"},
        {"name": _localize("Wellness", lang, _CATEGORY_TRANSLATIONS), "value": 12, "color": "#EC4899"},
    ]

    try:
        cat_pipeline = [
            {"$group": {"_id": "$category", "count": {"$sum": 1}}},
            {"$sort": {"count": -1}},
            {"$limit": 5},
        ]
        cat_raw = await db.conversations.aggregate(cat_pipeline).to_list(5)
        if cat_raw and len(cat_raw) >= 3:
            colors = ["#3B82F6", "#10B981", "#8B5CF6", "#F59E0B", "#EC4899"]
            total = sum(c["count"] for c in cat_raw)
            if total > 0:
                categories = [
                    {
                        "name": _localize(c["_id"] or "General", lang, _CATEGORY_TRANSLATIONS),
                        "value": round(c["count"] / total * 100),
                        "color": colors[i % len(colors)],
                    }
                    for i, c in enumerate(cat_raw)
                ]
    except Exception:
        pass

    return {
        "labels": days_labels,
        "ai_performance": ai_performance,
        "user_growth": user_growth,
        "categories": categories,
        "timestamp": now.isoformat(),
    }


_SAFE_ACTIVITY_TYPES = {
    "badge_earned", "achievement", "goal_milestone", "insight",
    "learning_hub_update", "language_guidance",
    "ai", "coaching", "session_completed", "agenda_reminder",
    "welcome", "feature_release", "drip_day1",
}

_ACTIVITY_TYPE_META = {
    "badge_earned": {"category": "milestones", "icon": "trophy", "route": "/notifications"},
    "achievement": {"category": "milestones", "icon": "trophy", "route": "/notifications"},
    "goal_milestone": {"category": "milestones", "icon": "flag", "route": "/notifications"},
    "insight": {"category": "milestones", "icon": "trending-up", "route": "/notifications"},
    "learning_hub_update": {"category": "learning", "icon": "school", "route": "/ai-learning-hub"},
    "language_guidance": {"category": "learning", "icon": "language", "route": "/settings"},
    "ai": {"category": "coaching", "icon": "sparkles", "route": "/help"},
    "coaching": {"category": "coaching", "icon": "play", "route": "/help"},
    "session_completed": {"category": "coaching", "icon": "checkmark-circle", "route": "/help"},
    "agenda_reminder": {"category": "coaching", "icon": "calendar", "route": "/notifications"},
    "welcome": {"category": "system", "icon": "hand-left", "route": "/features"},
    "feature_release": {"category": "system", "icon": "megaphone", "route": "/features"},
    "drip_day1": {"category": "system", "icon": "mail-open", "route": "/notifications"},
    "system": {"category": "system", "icon": "megaphone", "route": "/features"},
}


@router.get("/activity-feed")
async def get_activity_feed(request: Request):
    """Live activity pulse for the home page — user-scoped and allowlisted (no internal ops alerts)."""
    lang = _extract_lang(request)
    now = datetime.now(timezone.utc)
    feed = []

    user = await get_current_user(request)
    uid = getattr(user, "user_id", None) if user else None

    try:
        scope = [{"user_id": {"$in": [None, "", "global"]}}]
        if uid:
            scope.append({"user_id": uid})
        recent_notifs = (
            await db.notifications.find(
                {"type": {"$in": sorted(_SAFE_ACTIVITY_TYPES)}, "$or": scope},
                {"_id": 0, "title": 1, "message": 1, "type": 1, "created_at": 1},
            )
            .sort("created_at", -1)
            .limit(20)
            .to_list(20)
        )

        seen_signatures = set()
        per_type_counts: dict = {}
        for n in recent_notifs:
            if len(feed) >= 8:
                break
            ntype = str(n.get("type") or "system")
            signature = (ntype, str(n.get("title") or ""), str(n.get("message") or ""))
            if signature in seen_signatures or per_type_counts.get(ntype, 0) >= 2:
                continue
            seen_signatures.add(signature)
            per_type_counts[ntype] = per_type_counts.get(ntype, 0) + 1
            meta = _ACTIVITY_TYPE_META.get(ntype, _ACTIVITY_TYPE_META["system"])
            raw_title, raw_message = _sanitize_activity_copy(n.get("title", "Activity"), n.get("message", ""))
            feed.append(
                {
                    "type": ntype,
                    "title": _localize(raw_title, lang, _ACTIVITY_TRANSLATIONS),
                    "message": _localize(raw_message, lang, _ACTIVITY_TRANSLATIONS),
                    "time": n.get("created_at", now.isoformat()),
                    "category": meta["category"],
                    "icon": meta["icon"],
                    "route": meta["route"],
                }
            )
    except Exception:
        pass

    if len(feed) < 6:
        default_specs = [
            ("ai", "AI Session Completed", "Smart coaching session finished successfully"),
            ("achievement", "Goal Milestone", "New performance milestone reached"),
            ("system", "Platform Update", "New AI models deployed for better coaching"),
            ("coaching", "Coach Available", "New coaching slot opened for today"),
            ("insight", "Weekly Insight", "Your productivity score increased by 12%"),
        ]
        for i, (dtype, dtitle, dmessage) in enumerate(default_specs[: 6 - len(feed)]):
            meta = _ACTIVITY_TYPE_META.get(dtype, _ACTIVITY_TYPE_META["system"])
            feed.append(
                {
                    "type": dtype,
                    "title": _localize(dtitle, lang, _ACTIVITY_TRANSLATIONS),
                    "message": _localize(dmessage, lang, _ACTIVITY_TRANSLATIONS),
                    "time": (now - timedelta(minutes=12 + i * 47)).isoformat(),
                    "category": meta["category"],
                    "icon": meta["icon"],
                    "route": meta["route"],
                }
            )

    return {"feed": feed, "timestamp": now.isoformat()}


@router.get("/enterprise-command-center")
async def get_enterprise_command_center(request: Request):
    """Enterprise command center summary for Home dashboard redesign."""
    user = await get_current_user(request)
    if not user:
        from fastapi.responses import JSONResponse

        return JSONResponse(status_code=401, content={"detail": "Authentication required"})

    uid = user.user_id
    plan = compute_effective_plan(
        {
            "subscription_plan": getattr(user, "subscription_plan", "free"),
            "subscription_status": getattr(user, "subscription_status", "active"),
            "subscription_end_date": getattr(user, "subscription_end_date", None),
            "subscription_permanent": getattr(user, "subscription_permanent", False),
            "payment_verified": getattr(user, "payment_verified", False),
            "pending_subscription_transition": getattr(user, "pending_subscription_transition", None),
            "is_admin": getattr(user, "is_admin", False),
            "full_access": getattr(user, "full_access", False),
        }
    )
    now = datetime.now(timezone.utc)
    next_week = now + timedelta(days=7)

    unread_notifications = 0
    active_goals = 0
    upcoming_events = 0
    active_learning_tracks = 0
    unresolved_support = 0

    try:
        unread_notifications = await db.notifications.count_documents(
            {
                "$and": [
                    {"$or": [{"user_id": uid}, {"user_id": {"$in": [None, "", "global"]}}]},
                    {"read": {"$ne": True}},
                ]
            }
        )
    except Exception:
        unread_notifications = 0

    try:
        active_goals = await db.goals.count_documents({"user_id": uid, "status": {"$nin": ["completed", "done", "archived"]}})
    except Exception:
        active_goals = 0

    try:
        active_learning_tracks = await db.learn_hub_enrollments.count_documents({"user_id": uid, "completed": {"$ne": True}})
    except Exception:
        active_learning_tracks = 0

    try:
        unresolved_support = await db.support_tickets.count_documents({"user_id": uid, "status": {"$nin": ["resolved", "closed"]}})
    except Exception:
        unresolved_support = 0

    try:
        calendar_rows = await db.calendar_events.find(
            {"user_id": uid},
            {"_id": 0, "start_at": 1, "start_time": 1, "event_time": 1, "date": 1, "status": 1},
        ).limit(500).to_list(500)
        for row in calendar_rows:
            if str(row.get("status") or "").lower() in {"cancelled", "canceled"}:
                continue
            dt = (
                _parse_iso_datetime(row.get("start_at"))
                or _parse_iso_datetime(row.get("start_time"))
                or _parse_iso_datetime(row.get("event_time"))
                or _parse_iso_datetime(row.get("date"))
            )
            if dt and now <= dt <= next_week:
                upcoming_events += 1
    except Exception:
        upcoming_events = 0

    completed_ids: set[str] = set()
    try:
        profile = await db.users.find_one({"user_id": uid}, {"_id": 0, "name": 1, "bio": 1, "avatar": 1})
        if profile and profile.get("name") and (profile.get("bio") or profile.get("avatar")):
            completed_ids.add("complete_profile")
    except Exception:
        pass

    try:
        if await db.conversations.count_documents({"user_id": uid}) > 0:
            completed_ids.add("first_ai_session")
    except Exception:
        pass

    if active_goals > 0:
        completed_ids.add("set_goal")

    try:
        tour = await db.user_tour_status.find_one({"user_id": uid}, {"_id": 0, "completed": 1})
        if tour and tour.get("completed"):
            completed_ids.add("complete_tour")
    except Exception:
        pass

    try:
        checklist = await db.user_checklist.find_one({"user_id": uid}, {"_id": 0, "completed_items": 1})
        for item_id in (checklist or {}).get("completed_items", []):
            completed_ids.add(str(item_id))
    except Exception:
        pass

    checklist_total = len(CHECKLIST_ITEMS)
    checklist_completed = len(completed_ids.intersection({item["id"] for item in CHECKLIST_ITEMS}))

    priority_actions = []
    if checklist_completed < checklist_total:
        priority_actions.append(
            {
                "id": "complete_onboarding",
                "title": "Complete onboarding checklist",
                "description": f"{checklist_completed}/{checklist_total} steps completed.",
                "route": "/dashboard",
                "severity": "high",
            }
        )
    if active_learning_tracks <= 0:
        priority_actions.append(
            {
                "id": "start_learning_track",
                "title": "Start a Learning Hub track",
                "description": "No active learning tracks found for your account.",
                "route": "/ai-learning-hub",
                "severity": "high",
            }
        )
    if active_goals <= 0:
        priority_actions.append(
            {
                "id": "create_goal",
                "title": "Set a measurable goal",
                "description": "Goals unlock better AI recommendations and follow-up coaching.",
                "route": "/goals",
                "severity": "medium",
            }
        )
    if upcoming_events <= 0:
        priority_actions.append(
            {
                "id": "schedule_next_session",
                "title": "Schedule your next session",
                "description": "No upcoming events found in the next 7 days.",
                "route": "/book-meeting",
                "severity": "medium",
            }
        )
    if unread_notifications > 0:
        priority_actions.append(
            {
                "id": "review_alerts",
                "title": "Review pending alerts",
                "description": f"You have {unread_notifications} unread notification(s).",
                "route": "/notifications",
                "severity": "medium",
            }
        )

    if not priority_actions:
        priority_actions.append(
            {
                "id": "momentum_maintain",
                "title": "Momentum is healthy",
                "description": "All core workflows are on track. Explore growth insights next.",
                "route": "/my-analytics",
                "severity": "info",
            }
        )

    focus_templates = {
        "free": {
            "template_id": "focus-free",
            "title": "Starter Momentum Template",
            "subtitle": "Complete 3 core actions daily and unlock stronger recommendations.",
            "button_label": "Start Daily Focus Mode",
            "conversion_nudge": "Upgrade to Basic for almost unlimited guided workflows.",
        },
        "basic": {
            "template_id": "focus-basic",
            "title": "Growth Acceleration Template",
            "subtitle": "Blend consistency + conversion actions to compound weekly progress.",
            "button_label": "Start Growth Focus Mode",
            "conversion_nudge": "Upgrade to Premium for full unlimited execution templates.",
        },
        "premium": {
            "template_id": "focus-premium",
            "title": "Executive Autopilot Template",
            "subtitle": "Execute your top priorities with full-access automation and faster closure.",
            "button_label": "Start Executive Focus Mode",
            "conversion_nudge": "You have full unlimited template access.",
        },
    }
    focus_mode_template = focus_templates.get(plan, focus_templates["free"])

    if plan == "free" and not any(str(row.get("id") or "") == "upgrade-plan" for row in priority_actions):
        priority_actions.append(
            {
                "id": "upgrade-plan",
                "title": "Unlock more daily workflows",
                "description": "Upgrade to Basic for almost unlimited guided execution on Home focus mode.",
                "route": "/subscription/plans",
                "severity": "info",
            }
        )

    return {
        "generated_at": now.isoformat(),
        "viewer_user_id": uid,
        "subscription_plan": plan,
        "command_kpis": {
            "unread_notifications": unread_notifications,
            "active_goals": active_goals,
            "upcoming_events_7d": upcoming_events,
            "active_learning_tracks": active_learning_tracks,
            "open_support_threads": unresolved_support,
            "checklist_completed": checklist_completed,
            "checklist_total": checklist_total,
        },
        "priority_actions": priority_actions[:5],
        "focus_mode_template": focus_mode_template,
        "ai_status": "online",
    }


@router.get("/tour-status")
async def get_tour_status(request: Request):
    """Check if user has completed the onboarding tour."""
    user = await get_current_user(request)
    if not user:
        from fastapi.responses import JSONResponse
        return JSONResponse(status_code=401, content={"detail": "Authentication required"})
    uid = user.user_id
    try:
        rec = await db.user_tour_status.find_one({"user_id": uid}, {"_id": 0, "completed": 1})
        return {"completed": rec.get("completed", False) if rec else False}
    except Exception:
        return {"completed": False}


@router.post("/tour-complete")
async def mark_tour_complete(request: Request):
    """Mark onboarding tour as completed for the user."""
    user = await get_current_user(request)
    if not user:
        return {"status": "error", "message": "Not authenticated"}
    uid = user.user_id
    now = datetime.now(timezone.utc).isoformat()
    try:
        await db.user_tour_status.update_one(
            {"user_id": uid},
            {"$set": {"user_id": uid, "completed": True, "completed_at": now}},
            upsert=True,
        )
        return {"status": "ok", "completed": True}
    except Exception as e:
        return {"status": "error", "message": str(e)}


@router.post("/tour-reset")
async def reset_tour(request: Request):
    """Reset onboarding tour so it shows again."""
    user = await get_current_user(request)
    if not user:
        return {"status": "error", "message": "Not authenticated"}
    uid = user.user_id
    try:
        await db.user_tour_status.update_one(
            {"user_id": uid},
            {"$set": {"completed": False}},
            upsert=True,
        )
        return {"status": "ok", "completed": False}
    except Exception as e:
        return {"status": "error", "message": str(e)}


CHECKLIST_ITEMS = [
    {"id": "complete_profile", "label": "Complete Your Profile", "route": "/profile"},
    {"id": "first_ai_session", "label": "Start First AI Session", "route": "/feature-gallery"},
    {"id": "set_goal", "label": "Set a Goal", "route": "/goals"},
    {"id": "explore_tools", "label": "Explore Coaching Tools", "route": "/feature-gallery"},
    {"id": "complete_tour", "label": "Complete Onboarding Tour", "route": "/"},
]


@router.get("/today-pulse")
async def get_today_pulse(request: Request):
    """Personal daily pulse: login streak, sessions today, badges, setup progress."""
    user = await get_current_user(request)
    if not user:
        from fastapi.responses import JSONResponse
        return JSONResponse(status_code=401, content={"detail": "Authentication required"})
    uid = user.user_id
    now = datetime.now(timezone.utc)
    today = now.strftime("%Y-%m-%d")

    await db.user_login_days.update_one(
        {"user_id": uid, "day": today},
        {"$set": {"user_id": uid, "day": today, "updated_at": now.isoformat()}},
        upsert=True,
    )
    day_docs = await db.user_login_days.find({"user_id": uid}, {"_id": 0, "day": 1}).sort("day", -1).limit(90).to_list(90)
    day_set = {d["day"] for d in day_docs}
    streak = 0
    cursor_day = now.date()
    while cursor_day.strftime("%Y-%m-%d") in day_set:
        streak += 1
        cursor_day = cursor_day - timedelta(days=1)
    try:
        await db.users.update_one({"user_id": uid}, {"$set": {"login_streak": streak}})
    except Exception:
        pass

    sessions_today = 0
    total_sessions = 0
    try:
        sessions_today = await db.conversations.count_documents({"user_id": uid, "created_at": {"$gte": today}})
        total_sessions = await db.conversations.count_documents({"user_id": uid})
    except Exception:
        pass

    goal_count = 0
    try:
        goal_count = await db.goals.count_documents({"user_id": uid})
    except Exception:
        pass
    tour_done = False
    try:
        rec = await db.user_tour_status.find_one({"user_id": uid}, {"_id": 0, "completed": 1})
        tour_done = bool(rec and rec.get("completed"))
    except Exception:
        pass
    profile_done = False
    try:
        u = await db.users.find_one({"user_id": uid}, {"_id": 0, "name": 1, "bio": 1, "avatar": 1})
        profile_done = bool(u and u.get("name") and (u.get("bio") or u.get("avatar")))
    except Exception:
        pass
    manual_ids: set = set()
    try:
        cl = await db.user_checklist.find_one({"user_id": uid}, {"_id": 0, "completed_items": 1})
        manual_ids = set((cl or {}).get("completed_items") or [])
    except Exception:
        pass

    checklist_done = len({
        *( ["complete_profile"] if profile_done else [] ),
        *( ["first_ai_session"] if total_sessions > 0 else [] ),
        *( ["set_goal"] if goal_count > 0 else [] ),
        *( ["complete_tour"] if tour_done else [] ),
        *(manual_ids & {"complete_profile", "first_ai_session", "set_goal", "explore_tools", "complete_tour"}),
    })
    checklist_percent = round(checklist_done / 5 * 100)

    fps_pulse = {"kills": 0, "best_kill_streak": 0}
    try:
        fp = await db.fps_game_profiles.find_one({"user_id": uid}, {"_id": 0, "kills": 1, "best_kill_streak": 1})
        if fp:
            fps_pulse = {"kills": int(fp.get("kills", 0) or 0), "best_kill_streak": int(fp.get("best_kill_streak", 0) or 0)}
    except Exception:
        pass

    badges_earned = sum([
        tour_done,
        total_sessions >= 1,
        goal_count >= 3,
        streak >= 7,
        total_sessions >= 10,
        checklist_done >= 5,
        fps_pulse["kills"] >= 1,
        fps_pulse["best_kill_streak"] >= 5,
    ])

    return {
        "streak_days": streak,
        "sessions_today": sessions_today,
        "total_sessions": total_sessions,
        "badges_earned": badges_earned,
        "badges_total": 8,
        "checklist_percent": checklist_percent,
        "timestamp": now.isoformat(),
    }


@router.get("/checklist-status")
async def get_checklist_status(request: Request):
    """Get onboarding checklist progress for the current user."""
    lang = _extract_lang(request)
    user = await get_current_user(request)
    if not user:
        return {"items": [], "dismissed": False}

    uid = user.user_id
    completed_ids: list[str] = []

    try:
        u = await db.users.find_one({"user_id": uid}, {"_id": 0, "name": 1, "bio": 1, "avatar": 1})
        if u and u.get("name") and (u.get("bio") or u.get("avatar")):
            completed_ids.append("complete_profile")
    except Exception:
        pass

    try:
        session_count = await db.conversations.count_documents({"user_id": uid})
        if session_count > 0:
            completed_ids.append("first_ai_session")
    except Exception:
        pass

    try:
        goal_count = await db.goals.count_documents({"user_id": uid})
        if goal_count > 0:
            completed_ids.append("set_goal")
    except Exception:
        pass

    try:
        tour_rec = await db.user_tour_status.find_one({"user_id": uid}, {"_id": 0, "completed": 1})
        if tour_rec and tour_rec.get("completed"):
            completed_ids.append("complete_tour")
    except Exception:
        pass

    try:
        cl = await db.user_checklist.find_one({"user_id": uid}, {"_id": 0})
        if cl:
            for item_id in cl.get("completed_items", []):
                if item_id not in completed_ids:
                    completed_ids.append(item_id)
            dismissed = cl.get("dismissed", False)
        else:
            dismissed = False
    except Exception:
        dismissed = False

    items = []
    for item in CHECKLIST_ITEMS:
        items.append(
            {
                "id": item["id"],
                "label": _localize(item["label"], lang, _CHECKLIST_TRANSLATIONS),
                "route": item["route"],
                "completed": item["id"] in completed_ids,
            }
        )

    return {
        "items": items,
        "dismissed": dismissed,
        "total": len(CHECKLIST_ITEMS),
        "completed_count": sum(1 for i in items if i["completed"]),
    }


@router.post("/checklist-complete/{item_id}")
async def complete_checklist_item(item_id: str, request: Request):
    """Mark a checklist item as manually completed."""
    user = await get_current_user(request)
    if not user:
        return {"status": "error", "message": "Not authenticated"}

    valid_ids = [i["id"] for i in CHECKLIST_ITEMS]
    if item_id not in valid_ids:
        return {"status": "error", "message": "Invalid item id"}

    uid = user.user_id
    now = datetime.now(timezone.utc).isoformat()
    try:
        await db.user_checklist.update_one(
            {"user_id": uid},
            {"$addToSet": {"completed_items": item_id}, "$set": {"updated_at": now}},
            upsert=True,
        )
        return {"status": "ok", "item_id": item_id}
    except Exception as e:
        return {"status": "error", "message": str(e)}


@router.post("/checklist-dismiss")
async def dismiss_checklist(request: Request):
    """Dismiss the checklist widget after 100% completion."""
    user = await get_current_user(request)
    if not user:
        return {"status": "error", "message": "Not authenticated"}

    uid = user.user_id
    now = datetime.now(timezone.utc).isoformat()
    try:
        await db.user_checklist.update_one(
            {"user_id": uid},
            {"$set": {"dismissed": True, "dismissed_at": now}},
            upsert=True,
        )
        return {"status": "ok", "dismissed": True}
    except Exception as e:
        return {"status": "error", "message": str(e)}


BADGES = [
    {
        "id": "first_steps",
        "title": "First Steps",
        "desc": "Complete the onboarding tour",
        "icon": "rocket",
        "color": "#3B82F6",
        "threshold": 1,
    },
    {
        "id": "trailblazer",
        "title": "Trailblazer",
        "desc": "Start your first AI session",
        "icon": "flash",
        "color": "#F59E0B",
        "threshold": 1,
    },
    {
        "id": "goal_setter",
        "title": "Goal Setter",
        "desc": "Set 3 or more goals",
        "icon": "flag",
        "color": "#10B981",
        "threshold": 3,
    },
    {
        "id": "streak_master",
        "title": "Streak Master",
        "desc": "Maintain a 7-day login streak",
        "icon": "flame",
        "color": "#EF4444",
        "threshold": 7,
    },
    {
        "id": "power_user",
        "title": "Power User",
        "desc": "Complete 10+ AI sessions",
        "icon": "star",
        "color": "#8B5CF6",
        "threshold": 10,
    },
    {
        "id": "champion",
        "title": "Champion",
        "desc": "Complete all onboarding steps",
        "icon": "trophy",
        "color": "#EC4899",
        "threshold": 5,
    },
    {
        "id": "fps_first_blood",
        "title": "First Blood",
        "desc": "Score your first FPS arena kill",
        "icon": "locate",
        "color": "#EF4444",
        "threshold": 1,
    },
    {
        "id": "fps_arena_legend",
        "title": "Arena Legend",
        "desc": "Reach a 5-kill streak in the FPS arena",
        "icon": "flame",
        "color": "#F97316",
        "threshold": 5,
    },
    {
        "id": "palette_power_user",
        "title": "⚡ Power User",
        "desc": "Navigate via the Command Palette (⌘K) 10+ times",
        "icon": "flash",
        "color": "#8B5CF6",
        "threshold": 10,
    },
]


@router.get("/badges")
async def get_badges(request: Request):
    """Get achievement badges status for the current user."""
    user = await get_current_user(request)
    if not user:
        from fastapi.responses import JSONResponse
        return JSONResponse(status_code=401, content={"detail": "Authentication required"})

    uid = user.user_id
    results = []

    tour_done = False
    try:
        rec = await db.user_tour_status.find_one({"user_id": uid}, {"_id": 0, "completed": 1, "completed_at": 1})
        if rec and rec.get("completed"):
            tour_done = True
    except Exception:
        pass
    results.append(
        {
            "progress": 1 if tour_done else 0,
            "earned": tour_done,
            "earned_at": rec.get("completed_at") if tour_done and rec else None,
        }
    )

    session_count = 0
    try:
        session_count = await db.conversations.count_documents({"user_id": uid})
    except Exception:
        pass
    results.append(
        {
            "progress": min(session_count, 1),
            "earned": session_count >= 1,
            "earned_at": None,
        }
    )

    goal_count = 0
    try:
        goal_count = await db.goals.count_documents({"user_id": uid})
    except Exception:
        pass
    results.append(
        {
            "progress": min(goal_count, 3),
            "earned": goal_count >= 3,
            "earned_at": None,
        }
    )

    streak = 0
    try:
        u = await db.users.find_one({"user_id": uid}, {"_id": 0, "login_streak": 1, "streak_days": 1})
        if u:
            streak = u.get("login_streak") or u.get("streak_days") or 0
    except Exception:
        pass
    results.append(
        {
            "progress": min(streak, 7),
            "earned": streak >= 7,
            "earned_at": None,
        }
    )

    results.append(
        {
            "progress": min(session_count, 10),
            "earned": session_count >= 10,
            "earned_at": None,
        }
    )

    checklist_done = 0
    try:
        cl = await db.user_checklist.find_one({"user_id": uid}, {"_id": 0, "completed_items": 1})
        manual = set(cl.get("completed_items", [])) if cl else set()
        auto = set()
        if tour_done:
            auto.add("complete_tour")
        if session_count > 0:
            auto.add("first_ai_session")
        if goal_count > 0:
            auto.add("set_goal")
        try:
            uu = await db.users.find_one({"user_id": uid}, {"_id": 0, "name": 1, "bio": 1, "avatar": 1})
            if uu and uu.get("name") and (uu.get("bio") or uu.get("avatar")):
                auto.add("complete_profile")
        except Exception:
            pass
        all_ids = manual.union(auto)
        checklist_done = len(
            all_ids.intersection({"complete_profile", "first_ai_session", "set_goal", "explore_tools", "complete_tour"})
        )
    except Exception:
        pass
    results.append(
        {
            "progress": min(checklist_done, 5),
            "earned": checklist_done >= 5,
            "earned_at": None,
        }
    )

    fps_kills = 0
    fps_best_streak = 0
    try:
        fp = await db.fps_game_profiles.find_one({"user_id": uid}, {"_id": 0, "kills": 1, "best_kill_streak": 1})
        if fp:
            fps_kills = int(fp.get("kills", 0) or 0)
            fps_best_streak = int(fp.get("best_kill_streak", 0) or 0)
    except Exception:
        pass
    results.append(
        {
            "progress": min(fps_kills, 1),
            "earned": fps_kills >= 1,
            "earned_at": None,
        }
    )
    results.append(
        {
            "progress": min(fps_best_streak, 5),
            "earned": fps_best_streak >= 5,
            "earned_at": None,
        }
    )

    cp_navs = 0
    try:
        cp = await db.command_palette_usage.find_one({"user_id": uid}, {"_id": 0, "nav_count": 1})
        cp_navs = int(cp.get("nav_count", 0) or 0) if cp else 0
    except Exception:
        pass
    results.append(
        {
            "progress": min(cp_navs, 10),
            "earned": cp_navs >= 10,
            "earned_at": None,
        }
    )

    badges = []
    total_earned = 0
    for i, b in enumerate(BADGES):
        r = results[i]
        badges.append(
            {
                "id": b["id"],
                "title": b["title"],
                "desc": b["desc"],
                "icon": b["icon"],
                "color": b["color"],
                "threshold": b["threshold"],
                "progress": r["progress"],
                "earned": r["earned"],
                "earned_at": r.get("earned_at"),
            }
        )
        if r["earned"]:
            total_earned += 1

    return {"badges": badges, "total_earned": total_earned, "total": len(BADGES)}


@router.post("/command-palette-nav")
async def track_command_palette_nav(request: Request):
    """Record a Command Palette navigation for the Power User badge."""
    user = await get_current_user(request)
    if not user:
        from fastapi.responses import JSONResponse
        return JSONResponse(status_code=401, content={"detail": "Authentication required"})

    uid = user.user_id
    now = datetime.now(timezone.utc).isoformat()
    await db.command_palette_usage.update_one(
        {"user_id": uid},
        {"$inc": {"nav_count": 1}, "$set": {"updated_at": now}, "$setOnInsert": {"user_id": uid, "created_at": now}},
        upsert=True,
    )
    doc = await db.command_palette_usage.find_one({"user_id": uid}, {"_id": 0, "nav_count": 1})
    nav_count = int((doc or {}).get("nav_count", 0) or 0)
    return {"nav_count": nav_count, "power_user_earned": nav_count >= 10}


@router.get("/nova-bubble-position")
async def get_nova_bubble_position(request: Request):
    """Get persisted Home Nova launcher position for the current user."""
    user = await get_current_user(request)
    if not user:
        from fastapi.responses import JSONResponse
        return JSONResponse(status_code=401, content={"detail": "Authentication required"})

    uid = user.user_id
    doc = await db.user_home_preferences.find_one({"user_id": uid}, {"_id": 0, "nova_bubble_position": 1})
    position = (doc or {}).get("nova_bubble_position")
    return {"position": position}


@router.put("/nova-bubble-position")
async def upsert_nova_bubble_position(payload: NovaBubblePositionPayload, request: Request):
    """Persist Home Nova launcher position for the current user."""
    user = await get_current_user(request)
    if not user:
        from fastapi.responses import JSONResponse
        return JSONResponse(status_code=401, content={"detail": "Authentication required"})

    uid = user.user_id
    now = datetime.now(timezone.utc).isoformat()
    position = {
        "x": float(payload.x),
        "y": float(payload.y),
        "viewport_width": float(payload.viewport_width) if payload.viewport_width is not None else None,
        "viewport_height": float(payload.viewport_height) if payload.viewport_height is not None else None,
        "updated_at": now,
    }

    await db.user_home_preferences.update_one(
        {"user_id": uid},
        {
            "$set": {
                "user_id": uid,
                "nova_bubble_position": position,
                "updated_at": now,
            }
        },
        upsert=True,
    )

    return {"status": "ok", "position": position}
