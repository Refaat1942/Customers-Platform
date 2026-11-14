"""Google Authenticator / any TOTP app (RFC 6238: 6 digits, 30 seconds, SHA-1)."""

import base64
import hashlib
import hmac
import io
import secrets
import struct
import time
from urllib.parse import quote

import segno


def new_secret() -> str:
    return base64.b32encode(secrets.token_bytes(20)).decode().rstrip("=")


def _code(secret: str, counter: int) -> str:
    key = base64.b32decode(secret + "=" * (-len(secret) % 8), casefold=True)
    digest = hmac.new(key, struct.pack(">Q", counter), hashlib.sha1).digest()
    o = digest[-1] & 0x0F
    n = (struct.unpack(">I", digest[o:o + 4])[0] & 0x7FFFFFFF) % 1_000_000
    return f"{n:06d}"


def verify(secret: str, code: str, window: int = 1, at: float | None = None) -> bool:
    """Accept the current code and one step before/after (phone clocks drift a little)."""
    code = "".join(ch for ch in (code or "") if ch.isdigit())
    if len(code) != 6 or not secret:
        return False
    step = int((at or time.time()) // 30)
    return any(hmac.compare_digest(_code(secret, step + d), code) for d in range(-window, window + 1))


def now_code(secret: str) -> str:  # for tests
    return _code(secret, int(time.time() // 30))


def uri(secret: str, username: str, issuer: str) -> str:
    label = quote(f"{issuer}:{username}")
    return f"otpauth://totp/{label}?secret={secret}&issuer={quote(issuer)}&digits=6&period=30"


def qr_svg(text: str) -> str:
    buf = io.BytesIO()
    segno.make(text, error="m").save(buf, kind="svg", scale=5, border=2, dark="#1f2420")
    return buf.getvalue().decode()
