"""Fernet symmetric encryption for OAuth tokens stored in the database."""

import base64

from cryptography.fernet import Fernet

from ..config import get_settings

_fernet: Fernet | None = None


def _get_fernet() -> Fernet:
    global _fernet
    if _fernet is None:
        key = get_settings().encryption_key
        if not key:
            # Generate a throwaway key in development (tokens won't survive restarts)
            key = Fernet.generate_key().decode()
        # Accept raw base64 keys or plain strings
        try:
            _fernet = Fernet(key.encode() if isinstance(key, str) else key)
        except Exception:
            # If key isn't valid Fernet format, derive one from it
            import hashlib
            derived = base64.urlsafe_b64encode(hashlib.sha256(key.encode()).digest())
            _fernet = Fernet(derived)
    return _fernet


def encrypt_token(plaintext: str) -> str:
    """Encrypt a token for database storage."""
    if not plaintext:
        return ""
    return _get_fernet().encrypt(plaintext.encode()).decode()


def decrypt_token(ciphertext: str) -> str:
    """Decrypt a stored token."""
    if not ciphertext:
        return ""
    try:
        return _get_fernet().decrypt(ciphertext.encode()).decode()
    except Exception:
        # Token may be stored in plaintext from before encryption was added
        return ciphertext
