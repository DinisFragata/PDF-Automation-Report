"""Stateless email ownership verification plus in-memory rate limiting.

The public demo may only send a report to an address whose owner proved
access to it. The flow is:

1. ``create_verification(email)`` returns a random 6-digit code (to be emailed
   to that address) and a signed token (returned to the browser).
2. ``verify_code(email, code, token)`` checks the code against the token.

The token is ``base64url(email|expiry|HMAC(secret, email|expiry|code))``, so no
database is needed. Rate limits are kept in memory, which is enough for a single
instance; use a shared store if the API is ever scaled horizontally.
"""

import base64
import hashlib
import hmac
import os
import re
import secrets
import threading
import time
from collections import defaultdict, deque

from dotenv import load_dotenv

load_dotenv()


CODE_TTL_SECONDS = 10 * 60
MAX_EMAIL_LENGTH = 254

EMAIL_PATTERN = re.compile(r"^[^@\s<>,;\"'()\[\]\\]+@[^@\s<>,;\"'()\[\]\\]+\.[^@\s<>,;\"'()\[\]\\]+$")


class VerificationError(ValueError):
    """The email, code or token is invalid or expired."""


class RateLimitError(Exception):
    """Too many requests for a given key."""


def is_email_enabled() -> bool:
    return os.getenv("ENABLE_EMAIL", "false").strip().lower() in ("1", "true", "yes")


def normalize_email(email: str) -> str:
    email = (email or "").strip().lower()

    if len(email) > MAX_EMAIL_LENGTH or not EMAIL_PATTERN.match(email):
        raise VerificationError("Please enter a valid email address.")

    return email


def _get_secret() -> bytes:
    secret = os.getenv("VERIFY_SECRET", "")

    if len(secret) < 16:
        raise RuntimeError("VERIFY_SECRET must be set to a random string of at least 16 characters.")

    return secret.encode()


def _sign(email: str, expiry: int, code: str) -> str:
    message = f"{email}|{expiry}|{code}".encode()
    return hmac.new(_get_secret(), message, hashlib.sha256).hexdigest()


def create_verification(email: str) -> tuple[str, str]:
    """Return ``(code, token)`` for an already normalized email."""
    code = f"{secrets.randbelow(1_000_000):06d}"
    expiry = int(time.time()) + CODE_TTL_SECONDS
    signature = _sign(email, expiry, code)

    token = base64.urlsafe_b64encode(f"{email}|{expiry}|{signature}".encode()).decode()

    return code, token


def verify_code(email: str, code: str, token: str) -> None:
    """Raise ``VerificationError`` unless ``code`` and ``token`` match ``email``."""
    email = normalize_email(email)

    try:
        token_email, expiry_text, signature = (
            base64.urlsafe_b64decode(token.encode()).decode().rsplit("|", 2)
        )
        expiry = int(expiry_text)
    except Exception:
        raise VerificationError("Invalid verification token.") from None

    if token_email != email:
        raise VerificationError("The code was not requested for this email.")

    if expiry < time.time():
        raise VerificationError("The code has expired. Please request a new one.")

    expected_signature = _sign(email, expiry, (code or "").strip())

    if not hmac.compare_digest(signature, expected_signature):
        raise VerificationError("Incorrect code.")


class RateLimiter:
    """Sliding-window limiter: at most ``limit`` hits per ``window`` seconds per key."""

    def __init__(self) -> None:
        self._hits: dict[str, deque] = defaultdict(deque)
        self._lock = threading.Lock()

    def check(self, key: str, limit: int, window: int) -> None:
        now = time.monotonic()

        with self._lock:
            hits = self._hits[key]

            while hits and now - hits[0] > window:
                hits.popleft()

            if len(hits) >= limit:
                raise RateLimitError("Too many requests. Please try again later.")

            hits.append(now)

            if len(self._hits) > 10_000:
                self._prune(now, window)

    def _prune(self, now: float, window: int) -> None:
        for key in [k for k, v in self._hits.items() if not v or now - v[-1] > window]:
            del self._hits[key]


limiter = RateLimiter()

HOUR = 60 * 60
DAY = 24 * HOUR


def check_code_request_limits(email: str, client_ip: str) -> None:
    """Limits for sending verification codes (each one is an outgoing email)."""
    limiter.check(f"code:ip:{client_ip}", limit=10, window=HOUR)
    limiter.check(f"code:email:{email}", limit=3, window=HOUR)
    limiter.check("code:global", limit=int(os.getenv("MAX_CODES_PER_DAY", "100")), window=DAY)


def check_verify_attempt_limits(email: str, client_ip: str) -> None:
    """Limits for guessing codes (a 6-digit code must not be brute-forceable)."""
    limiter.check(f"verify:ip:{client_ip}", limit=20, window=HOUR)
    limiter.check(f"verify:email:{email}", limit=5, window=CODE_TTL_SECONDS)


def check_report_email_limits(email: str) -> None:
    """Limits for report emails sent after a successful verification."""
    limiter.check(f"report:email:{email}", limit=5, window=HOUR)
    limiter.check("report:global", limit=int(os.getenv("MAX_REPORT_EMAILS_PER_DAY", "100")), window=DAY)
