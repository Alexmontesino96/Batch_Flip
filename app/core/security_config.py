"""Security configuration — password policy, headers, rate limits.

Enforces Amazon SP-API security requirements:
- Password: 12+ chars, mixed case, numbers, special chars
- Account lockout after 10 failed attempts (Supabase handles this)
- Security headers on all responses
"""

import re

from fastapi import HTTPException

# Password policy (Amazon requirement: 12+ chars, mixed case, numbers, special)
MIN_PASSWORD_LENGTH = 12
PASSWORD_PATTERN = re.compile(
    r"^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)(?=.*[!@#$%^&*()_+\-=\[\]{};':\"\\|,.<>\/?])"
)


def validate_password(password: str) -> None:
    """Valida password contra Amazon security requirements."""
    if len(password) < MIN_PASSWORD_LENGTH:
        raise HTTPException(400, f"Password must be at least {MIN_PASSWORD_LENGTH} characters")
    if not PASSWORD_PATTERN.search(password):
        raise HTTPException(400, "Password must contain uppercase, lowercase, number, and special character")


# Security headers (OWASP recommended)
SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "X-XSS-Protection": "1; mode=block",
    "Strict-Transport-Security": "max-age=31536000; includeSubDomains",
    "Cache-Control": "no-store, no-cache, must-revalidate",
    "Referrer-Policy": "strict-origin-when-cross-origin",
}
