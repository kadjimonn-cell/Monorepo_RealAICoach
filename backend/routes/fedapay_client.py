"""FedaPay API client for processing mobile money payments.

Supports both live and sandbox environments with automatic URL selection,
phone validation, retry protection, and proper token-based checkout flow.
"""

import httpx
import hmac
import hashlib
import logging
import os
import asyncio
from typing import Dict, Any, Optional
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

# Sandbox test numbers (Benin country code: bj, new format with mandatory "01" prefix)
SANDBOX_SUCCESS_NUMBERS = ["0166000001", "0164000001"]
SANDBOX_FAILURE_NUMBERS = ["0166000000", "0164000000"]
SANDBOX_VALID_NUMBERS = SANDBOX_SUCCESS_NUMBERS + SANDBOX_FAILURE_NUMBERS

MAX_RETRIES = 2
RETRY_DELAY = 1.0


def _get_api_base_url() -> str:
    """Return the correct FedaPay API base URL based on key prefix and environment."""
    env = os.environ.get("FEDAPAY_ENV", "sandbox").lower()
    key = os.environ.get("FEDAPAY_SECRET_KEY", "")
    # Key prefix always takes priority over env setting
    if key.startswith("sk_sandbox"):
        return "https://sandbox-api.fedapay.com/v1"
    if key.startswith("sk_live"):
        if env == "sandbox":
            logger.warning("FEDAPAY_ENV=sandbox but key is sk_live_*. Using live API URL for compatibility.")
        return "https://api.fedapay.com/v1"
    # Fallback based on env when key prefix is unknown
    if env == "sandbox":
        return "https://sandbox-api.fedapay.com/v1"
    return "https://api.fedapay.com/v1"


def _get_headers() -> Dict[str, str]:
    key = os.environ.get("FEDAPAY_SECRET_KEY", "")
    return {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}


def is_sandbox() -> bool:
    """Check if FedaPay is running in sandbox mode.
    Key prefix is authoritative: sk_sandbox_* = sandbox, sk_live_* = live."""
    key = os.environ.get("FEDAPAY_SECRET_KEY", "")
    if key.startswith("sk_sandbox"):
        return True
    if key.startswith("sk_live"):
        return False  # Live keys cannot use sandbox API
    return os.environ.get("FEDAPAY_ENV", "sandbox").lower() == "sandbox"


def validate_sandbox_phone(phone: str) -> Dict[str, Any]:
    """Validate phone number for sandbox mode. Returns validation result."""
    clean = phone.replace("+", "").replace(" ", "").replace("-", "")
    # Strip Benin country code if present
    if clean.startswith("229"):
        clean = clean[3:]

    if clean in SANDBOX_VALID_NUMBERS:
        will_succeed = clean in SANDBOX_SUCCESS_NUMBERS
        return {
            "valid": True,
            "cleaned": clean,
            "will_succeed": will_succeed,
            "message": "Valid sandbox test number" + (" (will succeed)" if will_succeed else " (will simulate failure)"),
        }

    return {
        "valid": False,
        "cleaned": clean,
        "will_succeed": False,
        "message": f"Invalid sandbox phone. Use one of: {', '.join(SANDBOX_VALID_NUMBERS)}",
        "valid_numbers": SANDBOX_VALID_NUMBERS,
        "success_numbers": SANDBOX_SUCCESS_NUMBERS,
        "failure_numbers": SANDBOX_FAILURE_NUMBERS,
    }


async def create_transaction(
    amount: float,
    currency: str,
    description: str,
    customer_firstname: str,
    customer_lastname: str,
    customer_email: str,
    customer_phone: str,
    callback_url: Optional[str] = None,
    metadata: Optional[Dict] = None,
) -> Dict[str, Any]:
    """Create a FedaPay transaction and return transaction data with payment URL.

    Uses the correct API URL based on FEDAPAY_ENV.
    Implements retry logic for transient failures.
    """
    api_base = _get_api_base_url()
    headers = _get_headers()
    sandbox = is_sandbox()

    logger.info(f"FedaPay creating transaction: env={'sandbox' if sandbox else 'live'}, api={api_base}, amount={amount} {currency}")

    # Clean the phone number
    clean_phone = customer_phone.replace("+", "").replace(" ", "").replace("-", "")
    if clean_phone.startswith("229"):
        clean_phone = clean_phone[3:]

    # Build transaction payload matching FedaPay API spec
    tx_payload: Dict[str, Any] = {
        "description": description,
        "amount": int(amount),
        "currency": {"iso": currency.upper()},
        "callback_url": callback_url or "",
        "customer": {
            "firstname": customer_firstname,
            "lastname": customer_lastname,
            "email": customer_email,
            "phone_number": {
                "number": clean_phone,
                "country": "bj",
            },
        },
    }
    if metadata:
        tx_payload["metadata"] = metadata

    last_error = None
    for attempt in range(1, MAX_RETRIES + 2):
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                # Step 1: Create transaction
                resp = await client.post(
                    f"{api_base}/transactions",
                    json=tx_payload,
                    headers=headers,
                )
                resp.raise_for_status()
                resp_data = resp.json()
                tx = resp_data.get("v1/transaction", resp_data)
                tx_id = tx.get("id")
                logger.info(f"FedaPay transaction created (attempt {attempt}): id={tx_id}")

                # Step 2: Generate token for checkout widget
                payment_url = ""
                token = ""
                if tx_id:
                    token_resp = await client.post(
                        f"{api_base}/transactions/{tx_id}/token",
                        json={},
                        headers=headers,
                    )
                    if token_resp.status_code == 200:
                        token_data = token_resp.json()
                        token = token_data.get("token", "")
                        # Always prefer the URL returned by FedaPay API (authoritative)
                        payment_url = token_data.get("url", "")
                        if not payment_url and token:
                            # Fallback: construct URL only if API didn't provide one
                            checkout_base = "https://sandbox-checkout.fedapay.com" if sandbox else "https://checkout.fedapay.com"
                            payment_url = f"{checkout_base}/checkout/{token}"
                        logger.info(f"FedaPay token generated for tx {tx_id}: url={payment_url[:80] if payment_url else 'none'}")
                    else:
                        logger.warning(f"FedaPay token generation failed: {token_resp.status_code} {token_resp.text[:200]}")

                return {
                    "transaction_id": tx_id,
                    "reference": tx.get("reference", ""),
                    "status": tx.get("status", "pending"),
                    "amount": amount,
                    "currency": currency,
                    "payment_url": payment_url,
                    "token": token,
                    "sandbox": sandbox,
                }

        except httpx.HTTPStatusError as e:
            last_error = e
            err_text = e.response.text[:300]
            logger.warning(f"FedaPay API error (attempt {attempt}/{MAX_RETRIES + 1}): {e.response.status_code} - {err_text}")
            if e.response.status_code >= 500 and attempt <= MAX_RETRIES:
                await asyncio.sleep(RETRY_DELAY * attempt)
                continue
            raise
        except (httpx.ConnectError, httpx.TimeoutException) as e:
            last_error = e
            logger.warning(f"FedaPay connection error (attempt {attempt}/{MAX_RETRIES + 1}): {e}")
            if attempt <= MAX_RETRIES:
                await asyncio.sleep(RETRY_DELAY * attempt)
                continue
            raise

    raise last_error or Exception("FedaPay transaction creation failed after retries")


async def get_transaction(transaction_id: int) -> Dict[str, Any]:
    """Retrieve a transaction's current status from FedaPay."""
    api_base = _get_api_base_url()
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.get(f"{api_base}/transactions/{transaction_id}", headers=_get_headers())
        resp.raise_for_status()
        return resp.json().get("v1/transaction", resp.json())


async def generate_checkout_url_for_transaction(transaction_id: int | str) -> Dict[str, Any]:
    """Generate (or regenerate) checkout token URL for an existing FedaPay transaction."""
    api_base = _get_api_base_url()
    sandbox = is_sandbox()
    tx_id: int | str = int(transaction_id) if str(transaction_id).isdigit() else transaction_id

    async with httpx.AsyncClient(timeout=30.0) as client:
        token_resp = await client.post(
            f"{api_base}/transactions/{tx_id}/token",
            json={},
            headers=_get_headers(),
        )
        token_resp.raise_for_status()
        token_data = token_resp.json()
        token = token_data.get("token", "")
        payment_url = token_data.get("url", "")
        if not payment_url and token:
            checkout_base = "https://sandbox-checkout.fedapay.com" if sandbox else "https://checkout.fedapay.com"
            payment_url = f"{checkout_base}/checkout/{token}"

        return {
            "transaction_id": tx_id,
            "token": token,
            "payment_url": payment_url,
            "sandbox": sandbox,
        }


def verify_webhook_signature(signature_header: str, raw_body: bytes) -> bool:
    """Verify FedaPay webhook signature using HMAC-SHA256.
    Header format: t=<timestamp>,s=<signature>
    Signed payload: <timestamp>.<raw_body>
    """
    secret = os.environ.get("FEDAPAY_WEBHOOK_SECRET", "")
    if not secret or not signature_header:
        return False
    try:
        parts = {}
        for part in signature_header.split(","):
            k, v = part.strip().split("=", 1)
            parts[k] = v
        timestamp = parts.get("t", "")
        signature = parts.get("s", "")
        if not timestamp or not signature:
            return False
        message = f"{timestamp}.{raw_body.decode('utf-8')}"
        expected = hmac.new(secret.encode(), message.encode(), hashlib.sha256).hexdigest()
        return hmac.compare_digest(signature, expected)
    except Exception as e:
        logger.error(f"Webhook signature verification error: {e}")
        return False


def get_current_webhook_url() -> str:
    """Build the correct webhook URL from the current deployment URL."""
    def _normalize(candidate: str) -> str:
        if not candidate:
            return ""
        parsed = urlparse(candidate.strip())
        if parsed.scheme != "https" or not parsed.netloc:
            return ""
        return f"{parsed.scheme}://{parsed.netloc}"

    def _is_preview_base(candidate: str) -> bool:
        host = urlparse(candidate).netloc.lower()
        return ".preview.emergentagent.com" in host

    key = os.environ.get("FEDAPAY_SECRET_KEY", "")
    live_key = key.startswith("sk_live")

    frontend_base = _normalize(os.environ.get("FRONTEND_BASE_URL", ""))
    explicit_base = _normalize(os.environ.get("WEBHOOK_BASE_URL", "") or os.environ.get("FEDAPAY_WEBHOOK_BASE_URL", ""))
    dashboard_base = _normalize(os.environ.get("DASHBOARD_LINK_URL", ""))
    support_base = _normalize(os.environ.get("SUPPORT_LINK_URL", ""))
    runtime_frontend_env = _normalize(os.environ.get("REACT_APP_BACKEND_URL", ""))
    frontend_file_base = ""

    try:
        with open("/app/frontend/.env") as f:
            for line in f:
                if line.startswith("REACT_APP_BACKEND_URL="):
                    frontend_file_base = _normalize(line.strip().split("=", 1)[1])
                    break
    except Exception:
        frontend_file_base = ""

    public_base = explicit_base or dashboard_base or support_base
    auto_base = frontend_base or runtime_frontend_env or frontend_file_base
    base = public_base or auto_base

    # For live keys, never prioritize ephemeral preview hosts when a stable public base exists.
    if live_key and public_base and _is_preview_base(base) and not _is_preview_base(public_base):
        base = public_base

    # Defensive guard for live mode: avoid preview URLs unless explicitly allowed.
    allow_preview_live = str(os.environ.get("FEDAPAY_ALLOW_PREVIEW_WEBHOOK_SYNC", "false")).strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
    if live_key and base and _is_preview_base(base) and not allow_preview_live:
        if public_base and not _is_preview_base(public_base):
            base = public_base
        else:
            logger.warning(
                "FedaPay live key detected but webhook base resolves to preview host. Set WEBHOOK_BASE_URL for a stable domain."
            )
    if frontend_base and frontend_file_base and frontend_base != frontend_file_base:
        logger.warning(
            "FedaPay webhook base mismatch detected. Using FRONTEND_BASE_URL=%s instead of frontend/.env URL=%s",
            frontend_base,
            frontend_file_base,
        )

    return f"{base}/api/payments/fedapay/webhook" if base else ""


async def sync_webhook_url() -> Dict[str, Any]:
    """Auto-sync the FedaPay webhook URL to match the current deployment."""
    secret = os.environ.get("FEDAPAY_SECRET_KEY", "")
    if not secret:
        return {"status": "skipped", "reason": "no_secret_key"}

    target_url = get_current_webhook_url()
    if not target_url:
        return {"status": "skipped", "reason": "no_base_url"}

    live_key = secret.startswith("sk_live")
    allow_preview_live = str(os.environ.get("FEDAPAY_ALLOW_PREVIEW_WEBHOOK_SYNC", "false")).strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
    target_host = urlparse(target_url).netloc.lower()
    if live_key and ".preview.emergentagent.com" in target_host and not allow_preview_live:
        return {
            "status": "skipped",
            "reason": "unsafe_preview_target_for_live_key",
            "url": target_url,
            "hint": "Set WEBHOOK_BASE_URL to your stable production domain",
        }

    api_base = _get_api_base_url()
    headers = _get_headers()

    def _extract_webhooks(payload: Dict[str, Any]) -> list:
        if not isinstance(payload, dict):
            return []
        candidates = [
            payload.get("v1/webhooks"),
            payload.get("webhooks"),
            payload.get("data"),
        ]
        for key, value in payload.items():
            if isinstance(value, list):
                candidates.append(value)
            if isinstance(value, dict):
                nested = value.get("webhooks")
                if isinstance(nested, list):
                    candidates.append(nested)
        for candidate in candidates:
            if isinstance(candidate, list):
                return candidate
        return []

    def _normalize_url(candidate: str) -> str:
        if not candidate:
            return ""
        parsed = urlparse(candidate)
        if not parsed.scheme or not parsed.netloc:
            return ""
        return f"{parsed.scheme}://{parsed.netloc}{parsed.path.rstrip('/')}"

    def _is_fedapay_path(candidate: str) -> bool:
        path = (urlparse(candidate).path or "").rstrip("/")
        return path in ("/api/payments/fedapay/webhook", "/api/fedapay/webhook")

    def _normalize_webhook_item(item: Dict[str, Any]) -> Dict[str, Any]:
        if not isinstance(item, dict):
            return {}
        nested = item.get("v1/webhook")
        if isinstance(nested, dict):
            merged = {**nested}
            for k, v in item.items():
                if k == "v1/webhook":
                    continue
                merged.setdefault(k, v)
            return merged
        return item

    def _extract_id(item: Dict[str, Any]) -> str:
        candidate = item.get("id")
        if candidate is None:
            return ""
        return str(candidate).strip()

    def _build_payload(url: str) -> Dict[str, Any]:
        return {
            "url": url,
            "enabled": True,
            "ssl_verify": True,
            # Prevent provider-side hard-disable on transient errors
            "disable_on_error": False,
        }

    def _response_detail(resp: httpx.Response) -> str:
        try:
            payload = resp.json()
            if isinstance(payload, dict):
                return str(payload)[:500]
            return str(payload)[:500]
        except Exception:
            return (resp.text or "")[:500]

    async def _cleanup_stale(client: httpx.AsyncClient, stale: list, keep_id: str = "") -> int:
        deleted = 0
        for row in stale:
            stale_id = _extract_id(row)
            if not stale_id or (keep_id and stale_id == keep_id):
                continue
            try:
                r = await client.delete(f"{api_base}/webhooks/{stale_id}", headers=headers)
                if r.status_code < 300:
                    logger.info(f"Deleted stale FedaPay webhook {stale_id}: {row.get('url')}")
                    deleted += 1
            except Exception:
                continue
        return deleted

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(f"{api_base}/webhooks", headers=headers)
            resp.raise_for_status()
            parsed = resp.json()
            data = parsed if isinstance(parsed, dict) else {}
            raw_webhooks = _extract_webhooks(data)
            webhooks = [_normalize_webhook_item(row) for row in raw_webhooks if isinstance(row, dict)]

            normalized_target = _normalize_url(target_url)
            correct_webhook = None
            stale_webhooks = []
            old_url = ""

            for wh in webhooks:
                url = str(wh.get("url") or "")
                normalized_url = _normalize_url(url)
                if not _is_fedapay_path(url):
                    continue
                if normalized_url == normalized_target and bool(wh.get("enabled", True)):
                    correct_webhook = wh
                else:
                    stale_webhooks.append(wh)
                    if not old_url:
                        old_url = url

            if correct_webhook:
                deleted = await _cleanup_stale(client, stale_webhooks, keep_id=_extract_id(correct_webhook))
                return {
                    "status": "ok",
                    "action": "cleaned_stale" if deleted else "none",
                    "url": target_url,
                    "webhook_id": _extract_id(correct_webhook),
                    "old_url": old_url,
                    "new_url": target_url,
                    "deleted": deleted,
                }

            # Safe strategy: create/update first; delete stale only after success.
            errors = []
            payload = _build_payload(target_url)
            create_candidates = [
                payload,
                {"webhook": payload},
                {"v1/webhook": payload},
            ]

            active_webhook_id = ""
            active_action = ""

            # Try update first if a stale webhook already exists
            if stale_webhooks:
                primary = stale_webhooks[0]
                primary_id = _extract_id(primary)
                if primary_id:
                    for method in ("put", "patch"):
                        for body in create_candidates:
                            try:
                                update_resp = await client.request(
                                    method,
                                    f"{api_base}/webhooks/{primary_id}",
                                    json=body,
                                    headers=headers,
                                )
                                if update_resp.status_code < 300:
                                    active_webhook_id = primary_id
                                    active_action = "updated"
                                    break
                                errors.append(f"{method.upper()}:{update_resp.status_code}:{_response_detail(update_resp)}")
                            except Exception as exc:
                                errors.append(f"{method.upper()}:{exc}")
                        if active_webhook_id:
                            break

            # If update failed, create a fresh webhook
            if not active_webhook_id:
                for body in create_candidates:
                    try:
                        create_resp = await client.post(f"{api_base}/webhooks", json=body, headers=headers)
                        if create_resp.status_code < 300:
                            created = create_resp.json()
                            normalized = _normalize_webhook_item(created if isinstance(created, dict) else {})
                            active_webhook_id = _extract_id(normalized)
                            active_action = "recreated" if stale_webhooks else "created"
                            break
                        errors.append(f"POST:{create_resp.status_code}:{_response_detail(create_resp)}")
                    except Exception as exc:
                        errors.append(f"POST:{exc}")

            if not active_webhook_id and not active_action:
                # Preserve stale webhook(s) instead of deleting and causing total outage.
                return {
                    "status": "error",
                    "error": "unable_to_create_or_update_webhook",
                    "detail": " | ".join(errors)[:1200],
                    "stale_preserved": len(stale_webhooks),
                    "url": target_url,
                }

            deleted = await _cleanup_stale(client, stale_webhooks, keep_id=active_webhook_id)
            return {
                "status": "ok",
                "action": active_action,
                "url": target_url,
                "webhook_id": active_webhook_id or "unknown",
                "old_url": old_url,
                "new_url": target_url,
                "deleted": deleted,
            }

    except httpx.HTTPStatusError as e:
        return {
            "status": "error",
            "error": f"HTTP {e.response.status_code}",
            "detail": _response_detail(e.response),
            "url": target_url,
        }
    except Exception as e:
        return {"status": "error", "error": str(e), "url": target_url}
