"""
Field-Level Encryption Utility
================================
Provides symmetric AES-128 (Fernet) encryption for sensitive MongoDB fields.
Key is loaded from the FIELD_ENCRYPTION_KEY environment variable.

Usage:
    from utils.field_encryption import encrypt_field, decrypt_field, is_encrypted

    # Encrypt before storing:
    doc["secret"] = encrypt_field(raw_secret)

    # Decrypt after reading:
    raw_secret = decrypt_field(doc["secret"])

    # Lazy-migration pattern (read → decrypt → use, then save encrypted copy):
    value = doc.get("field")
    if value and not is_encrypted(value):
        encrypted = encrypt_field(value)
        await db.collection.update_one({"_id": doc["_id"]}, {"$set": {"field": encrypted}})
"""
from cryptography.fernet import Fernet
import hmac
import hashlib
import os
import logging

logger = logging.getLogger(__name__)

ENCRYPTED_PREFIX = "enc:"

_fernet: Fernet | None = None
_lookup_key: bytes | None = None


def _get_fernet() -> Fernet:
    global _fernet
    if _fernet is None:
        key = os.environ.get("FIELD_ENCRYPTION_KEY", "")
        if not key:
            raise RuntimeError("FIELD_ENCRYPTION_KEY environment variable is not set")
        _fernet = Fernet(key.encode())
    return _fernet


def _get_lookup_key() -> bytes:
    """HMAC key for deterministic lookup hashes. Falls back to FIELD_ENCRYPTION_KEY if not set."""
    global _lookup_key
    if _lookup_key is None:
        k = os.environ.get("FIELD_LOOKUP_HMAC_KEY") or os.environ.get("FIELD_ENCRYPTION_KEY", "")
        if not k:
            raise RuntimeError("FIELD_LOOKUP_HMAC_KEY / FIELD_ENCRYPTION_KEY not set")
        _lookup_key = k.encode()
    return _lookup_key


def encrypt_field(value: str) -> str:
    """Encrypt a plaintext string for storage. Idempotent: already-encrypted values pass through."""
    if not isinstance(value, str) or not value:
        return value
    if is_encrypted(value):
        return value
    try:
        ciphertext = _get_fernet().encrypt(value.encode()).decode()
        return ENCRYPTED_PREFIX + ciphertext
    except Exception as exc:
        logger.error("Field encryption failed: %s", exc)
        raise


def decrypt_field(value: str) -> str:
    """
    Decrypt an encrypted field value.
    Falls back transparently if the value is unencrypted plaintext
    (backward-compatibility for data not yet migrated).
    """
    if not isinstance(value, str) or not value:
        return value
    if not is_encrypted(value):
        return value  # Legacy plaintext — return as-is
    try:
        raw = value[len(ENCRYPTED_PREFIX):]
        return _get_fernet().decrypt(raw.encode()).decode()
    except Exception as exc:
        logger.error("Field decryption failed: %s", exc)
        raise


def is_encrypted(value: str) -> bool:
    """Return True if the value was encrypted by this utility."""
    return isinstance(value, str) and value.startswith(ENCRYPTED_PREFIX)


def hash_lookup(value: str) -> str:
    """
    Deterministic HMAC-SHA256 hash for encrypted-field lookups.
    - Normalizes (lowercase + strip) so `"Alice@X.com "` == `"alice@x.com"`.
    - Hex digest — safe for MongoDB queries and indexes.
    - Use ONLY for exact-match lookups; prefix/regex/substring impossible by design.
    """
    if not isinstance(value, str) or not value:
        return ""
    normalized = value.strip().lower().encode()
    return hmac.new(_get_lookup_key(), normalized, hashlib.sha256).hexdigest()


def decrypt_doc(doc: dict, fields: tuple[str, ...] | list[str]) -> dict:
    """
    In-place decryption of a list of fields on a MongoDB document.
    Safe on docs where some fields may still be plaintext (lazy-migration).
    Returns the same dict for call-chaining.
    """
    if not isinstance(doc, dict):
        return doc
    for f in fields:
        val = doc.get(f)
        if isinstance(val, str) and val:
            try:
                doc[f] = decrypt_field(val)
            except Exception as exc:
                logger.warning("decrypt_doc: field=%s failed: %s", f, exc)
    return doc
