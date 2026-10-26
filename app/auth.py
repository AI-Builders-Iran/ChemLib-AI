"""Library-admin authentication (a single shared password from the environment)."""

from __future__ import annotations

import hmac
import os


def admin_configured() -> bool:
    """True when ADMIN_PASSWORD is set; without it the admin panel stays locked."""
    return bool(os.getenv("ADMIN_PASSWORD"))


def verify_admin_password(candidate: str) -> bool:
    """Constant-time comparison against ADMIN_PASSWORD."""
    expected = os.getenv("ADMIN_PASSWORD", "")
    if not expected:
        return False
    return hmac.compare_digest(candidate.encode("utf-8"), expected.encode("utf-8"))
