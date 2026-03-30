"""
API key authentication for admin routes.

Set ADMIN_API_KEY in the environment. Requests to admin endpoints must include:
    X-API-Key: <your key>

If ADMIN_API_KEY is not set, the app will start but all admin endpoints return 503.
"""

from __future__ import annotations

import os

from fastapi import HTTPException, Security
from fastapi.security import APIKeyHeader

_API_KEY_HEADER = APIKeyHeader(name="X-API-Key", auto_error=False)


def require_api_key(key: str | None = Security(_API_KEY_HEADER)) -> str:
    """FastAPI dependency: validate X-API-Key header against ADMIN_API_KEY env var."""
    admin_key = os.getenv("ADMIN_API_KEY", "").strip()
    if not admin_key:
        raise HTTPException(
            status_code=503,
            detail="Admin API is not configured (ADMIN_API_KEY not set).",
        )
    if not key or key != admin_key:
        raise HTTPException(
            status_code=401,
            detail="Invalid or missing API key. Provide a valid X-API-Key header.",
        )
    return key
