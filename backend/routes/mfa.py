"""Multi-Factor Authentication (MFA) — TOTP-based 2FA endpoints."""

from fastapi import APIRouter, HTTPException, Request
from datetime import datetime, timezone
from routes.db import db, get_current_user, require_admin
from utils.field_encryption import encrypt_field, decrypt_field, is_encrypted
import pyotp
import qrcode
import io
import base64
import logging

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/auth/mfa", tags=["MFA"])

APP_NAME = "RealAICoach"


@router.get("/status")
async def mfa_status(req: Request):
    """Check if MFA is enabled for the current user."""
    user = await get_current_user(req)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")

    mfa_doc = await db.user_mfa.find_one({"user_id": user.user_id}, {"_id": 0, "enabled": 1, "created_at": 1})
    return {
        "mfa_enabled": bool(mfa_doc and mfa_doc.get("enabled")),
        "setup_date": mfa_doc.get("created_at") if mfa_doc else None,
    }


@router.post("/setup")
async def mfa_setup(req: Request):
    """Generate a new TOTP secret and QR code for MFA setup."""
    user = await get_current_user(req)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")

    existing = await db.user_mfa.find_one({"user_id": user.user_id, "enabled": True})
    if existing:
        raise HTTPException(status_code=400, detail="MFA is already enabled. Disable it first to reconfigure.")

    secret = pyotp.random_base32()
    totp = pyotp.TOTP(secret)
    provisioning_uri = totp.provisioning_uri(name=user.email, issuer_name=APP_NAME)

    # Generate QR code as base64
    qr = qrcode.QRCode(version=1, box_size=6, border=2)
    qr.add_data(provisioning_uri)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    qr_base64 = base64.b64encode(buf.getvalue()).decode()

    # Store pending secret encrypted
    await db.user_mfa.update_one(
        {"user_id": user.user_id},
        {
            "$set": {
                "secret": encrypt_field(secret),
                "enabled": False,
                "setup_at": datetime.now(timezone.utc).isoformat(),
            }
        },
        upsert=True,
    )

    return {
        "secret": secret,
        "qr_code": f"data:image/png;base64,{qr_base64}",
        "provisioning_uri": provisioning_uri,
    }


@router.post("/verify")
async def mfa_verify(req: Request, body: dict):
    """Verify a TOTP code to complete MFA setup."""
    user = await get_current_user(req)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")

    code = body.get("code", "").strip()
    if not code:
        raise HTTPException(status_code=400, detail="Code is required")

    mfa_doc = await db.user_mfa.find_one({"user_id": user.user_id}, {"_id": 0})
    if not mfa_doc or not mfa_doc.get("secret"):
        raise HTTPException(status_code=400, detail="MFA setup not initiated. Call /setup first.")

    raw_secret = decrypt_field(mfa_doc["secret"])
    # Lazy-migrate: encrypt if still plaintext
    if not is_encrypted(mfa_doc["secret"]):
        await db.user_mfa.update_one({"user_id": user.user_id}, {"$set": {"secret": encrypt_field(raw_secret)}})

    totp = pyotp.TOTP(raw_secret)
    if not totp.verify(code, valid_window=1):
        raise HTTPException(status_code=400, detail="Invalid code. Please try again.")

    # Generate backup codes
    import secrets

    backup_codes = [secrets.token_hex(4) for _ in range(8)]
    hashed_backups = [__import__("hashlib").sha256(c.encode()).hexdigest() for c in backup_codes]

    await db.user_mfa.update_one(
        {"user_id": user.user_id},
        {
            "$set": {
                "enabled": True,
                "verified_at": datetime.now(timezone.utc).isoformat(),
                "created_at": datetime.now(timezone.utc).isoformat(),
                "backup_codes": hashed_backups,
            }
        },
    )

    # Update user record
    await db.users.update_one(
        {"user_id": user.user_id},
        {"$set": {"mfa_enabled": True}},
    )

    logger.info(f"MFA enabled for user {user.user_id}")

    # Send MFA enabled confirmation email
    try:
        from utils.email_service import send_catalog_template
        await send_catalog_template(
            recipient_email=user.email,
            template_key="mfa_enabled",
            recipient_name=user.name or user.email,
            user_name=user.name or user.email,
            method="Authenticator App",
            enabled_at=datetime.now(timezone.utc).strftime("%B %d, %Y at %I:%M %p UTC"),
        )
    except Exception as e:
        logger.warning(f"MFA enabled email failed: {e}")

    return {"enabled": True, "backup_codes": backup_codes}


@router.post("/disable")
async def mfa_disable(req: Request, body: dict):
    """Disable MFA for the current user (requires current TOTP code)."""
    user = await get_current_user(req)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")

    code = body.get("code", "").strip()
    if not code:
        raise HTTPException(status_code=400, detail="Current TOTP code is required")

    mfa_doc = await db.user_mfa.find_one({"user_id": user.user_id}, {"_id": 0})
    if not mfa_doc or not mfa_doc.get("enabled"):
        raise HTTPException(status_code=400, detail="MFA is not enabled")

    raw_secret = decrypt_field(mfa_doc["secret"])
    totp = pyotp.TOTP(raw_secret)
    if not totp.verify(code, valid_window=1):
        raise HTTPException(status_code=400, detail="Invalid code")

    await db.user_mfa.update_one(
        {"user_id": user.user_id},
        {"$set": {"enabled": False, "disabled_at": datetime.now(timezone.utc).isoformat()}},
    )
    await db.users.update_one(
        {"user_id": user.user_id},
        {"$set": {"mfa_enabled": False}},
    )

    logger.info(f"MFA disabled for user {user.user_id}")

    # Send MFA disabled security alert email
    try:
        from utils.email_service import send_catalog_template
        await send_catalog_template(
            recipient_email=user.email,
            template_key="mfa_disabled",
            recipient_name=user.name or user.email,
            user_name=user.name or user.email,
            disabled_at=datetime.now(timezone.utc).strftime("%B %d, %Y at %I:%M %p UTC"),
        )
    except Exception as e:
        logger.warning(f"MFA disabled email failed: {e}")

    return {"disabled": True}


@router.post("/validate")
async def mfa_validate_login(req: Request, body: dict):
    """Validate TOTP code during login flow (called after password verification)."""
    user_id = body.get("user_id", "")
    code = body.get("code", "").strip()

    if not user_id or not code:
        raise HTTPException(status_code=400, detail="user_id and code are required")

    mfa_doc = await db.user_mfa.find_one({"user_id": user_id, "enabled": True}, {"_id": 0})
    if not mfa_doc:
        raise HTTPException(status_code=400, detail="MFA is not enabled for this user")

    raw_secret = decrypt_field(mfa_doc["secret"])
    totp = pyotp.TOTP(raw_secret)
    valid = totp.verify(code, valid_window=1)

    if not valid:
        # Check backup codes
        import hashlib

        code_hash = hashlib.sha256(code.encode()).hexdigest()
        backups = mfa_doc.get("backup_codes", [])
        if code_hash in backups:
            # Use and remove backup code
            backups.remove(code_hash)
            await db.user_mfa.update_one(
                {"user_id": user_id},
                {"$set": {"backup_codes": backups}},
            )
            valid = True

    if not valid:
        raise HTTPException(status_code=401, detail="Invalid MFA code")

    return {"valid": True}


@router.get("/admin/stats")
async def mfa_admin_stats(req: Request):
    """Admin view of MFA adoption statistics."""
    await require_admin(req)
    total_enabled = await db.user_mfa.count_documents({"enabled": True})
    total_users = await db.users.count_documents({})

    return {
        "total_users": total_users,
        "mfa_enabled_count": total_enabled,
        "adoption_rate": round(total_enabled / max(total_users, 1) * 100, 1),
    }
