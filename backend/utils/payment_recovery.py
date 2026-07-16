"""Automated Payment Failure Recovery System.

Generates secure recovery tokens, schedules escalating email sequences,
and provides one-click recovery links for failed payments.
"""

import os
import uuid
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional

logger = logging.getLogger("payment_recovery")

FRONTEND_BASE = os.environ.get("FRONTEND_BASE_URL", os.environ.get("DASHBOARD_LINK_URL", ""))

CURRENCY_SYMBOLS = {
    "USD": "$", "EUR": "\u20ac", "GBP": "\u00a3", "XOF": "CFA ", "XAF": "CFA ",
    "JPY": "\u00a5", "CAD": "CA$", "AUD": "A$", "INR": "\u20b9", "BRL": "R$",
    "NGN": "\u20a6", "KES": "KSh", "GHS": "GH\u20b5", "ZAR": "R", "CHF": "CHF ",
    "SEK": "kr", "PLN": "z\u0142", "TRY": "\u20ba", "THB": "\u0e3f", "RUB": "\u20bd",
    "MXN": "MX$", "KRW": "\u20a9",
}
NO_DECIMAL = {"JPY", "KRW", "XOF", "XAF"}


def format_currency(amount: float, currency: str = "USD") -> str:
    cur = currency.upper()
    sym = CURRENCY_SYMBOLS.get(cur, f"{cur} ")
    if cur in NO_DECIMAL:
        return f"{sym}{int(amount):,}"
    return f"{sym}{amount:,.2f}"


async def create_recovery_token(
    db,
    user_id: str,
    plan_id: str,
    billing_period: str,
    payment_method: str,
    amount_usd: float,
    currency: str = "USD",
    amount_local: float = 0,
    session_id: str = "",
) -> str:
    """Create a secure recovery token for a failed payment."""
    token = f"rcv_{uuid.uuid4().hex}"
    expires_at = datetime.now(timezone.utc) + timedelta(days=14)

    await db.payment_recovery.update_one(
        {"user_id": user_id, "status": "active"},
        {"$set": {"status": "superseded", "superseded_at": datetime.now(timezone.utc).isoformat()}},
    )

    await db.payment_recovery.insert_one({
        "token": token,
        "user_id": user_id,
        "plan_id": plan_id,
        "billing_period": billing_period,
        "payment_method": payment_method,
        "amount_usd": amount_usd,
        "currency": currency,
        "amount_local": amount_local,
        "session_id": session_id,
        "status": "active",
        "emails_sent": 0,
        "last_email_at": None,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "expires_at": expires_at.isoformat(),
        "recovered": False,
        "recovered_at": None,
    })

    logger.info(f"Recovery token created for user {user_id}: {token}")
    return token


def get_recovery_url(token: str) -> str:
    """Build the one-click recovery URL."""
    base = FRONTEND_BASE or ""
    return f"{base}/subscription/recover?token={token}"


async def validate_recovery_token(db, token: str) -> Optional[dict]:
    """Validate a recovery token. Returns token doc or None."""
    doc = await db.payment_recovery.find_one(
        {"token": token, "status": "active"},
        {"_id": 0},
    )
    if not doc:
        return None
    if doc.get("recovered"):
        return None
    if doc.get("expires_at"):
        exp = datetime.fromisoformat(doc["expires_at"])
        if datetime.now(timezone.utc) > exp:
            await db.payment_recovery.update_one(
                {"token": token}, {"$set": {"status": "expired"}}
            )
            return None
    return doc


async def mark_recovered(db, token: str, new_session_id: str = ""):
    """Mark a recovery token as used."""
    await db.payment_recovery.update_one(
        {"token": token},
        {"$set": {
            "recovered": True,
            "recovered_at": datetime.now(timezone.utc).isoformat(),
            "status": "recovered",
            "new_session_id": new_session_id,
        }},
    )
    logger.info(f"Recovery token {token} marked as recovered")


async def process_recovery_emails(db):
    """Scheduled task: send escalating recovery emails for active tokens.

    Email schedule:
      - Email 1: Immediately (handled at failure time)
      - Email 2: After 3 days
      - Email 3: After 7 days (final warning)
    """
    from utils.email_service import is_email_configured

    if not is_email_configured():
        return

    now = datetime.now(timezone.utc)
    active_tokens = db.payment_recovery.find(
        {"status": "active", "recovered": False, "emails_sent": {"$lt": 3}},
    )

    count = 0
    async for token_doc in active_tokens:
        emails_sent = token_doc.get("emails_sent", 0)
        created = datetime.fromisoformat(token_doc["created_at"])
        last_email = token_doc.get("last_email_at")
        if last_email:
            last_email = datetime.fromisoformat(last_email)

        # Determine if it's time to send the next email
        should_send = False
        email_stage = emails_sent + 1

        if email_stage == 2 and (now - created).days >= 3:
            if not last_email or (now - last_email).days >= 2:
                should_send = True
        elif email_stage == 3 and (now - created).days >= 7:
            if not last_email or (now - last_email).days >= 3:
                should_send = True

        if not should_send:
            continue

        user_id = token_doc["user_id"]
        user = await db.users.find_one({"user_id": user_id}, {"_id": 0, "email": 1, "name": 1})
        if not user or not user.get("email"):
            continue

        recovery_url = get_recovery_url(token_doc["token"])
        currency = token_doc.get("currency", "USD")
        amount = token_doc.get("amount_local", 0) if currency != "USD" else token_doc.get("amount_usd", 0)
        amount_str = format_currency(amount, currency)

        from utils.email_templates import build_recovery_email_day3, build_recovery_email_day7

        if email_stage == 2:
            build_recovery_email_day3(
                user_name=user.get("name", ""),
                plan_name=token_doc.get("plan_id", "basic").title(),
                amount=amount_str,
                recovery_link=recovery_url,
            )
        else:
            build_recovery_email_day7(
                user_name=user.get("name", ""),
                plan_name=token_doc.get("plan_id", "basic").title(),
                amount=amount_str,
                recovery_link=recovery_url,
            )

        try:
            from utils.email_service import send_catalog_template
            template_key = "recovery_day3" if email_stage == 2 else "recovery_day7"
            await send_catalog_template(
                recipient_email=user["email"],
                template_key=template_key,
                user_name=user.get("name", ""),
                plan_name=token_doc.get("plan_id", "basic").title(),
                amount=amount_str,
                recovery_link=recovery_url,
            )
            await db.payment_recovery.update_one(
                {"token": token_doc["token"]},
                {"$set": {"emails_sent": email_stage, "last_email_at": now.isoformat()}},
            )
            count += 1
            logger.info(f"Recovery email #{email_stage} sent to {user['email']} (token: {token_doc['token']})")
        except Exception as e:
            logger.error(f"Recovery email failed for {user_id}: {e}")

    if count > 0:
        logger.info(f"Recovery email batch: sent {count} emails")
