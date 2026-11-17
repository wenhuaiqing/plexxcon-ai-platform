"""Shared-secret gate for the demo's write paths.

The public demo has no user accounts. Anything that changes state - a saved
draft, a submitted revision, a review decision, a confirmed docket - is gated
on one secret sent as `X-Write-Token`. The operator unlocks a browser session
by visiting once with `?write_token=<value>`; the frontend keeps it in
sessionStorage and adds the header to every call. Without it the site is the
read-only role: every register, report and audit log, and no writes.

Fail closed: no token configured means writes are refused everywhere.

Authority comes from the token. The actor name (`X-Actor`) is recorded and
used for separation of duties - nobody decides their own request - but is
never trusted as identity on its own. A production build would take both from
the identity provider.
"""

from __future__ import annotations

import hmac

from fastapi import HTTPException, Request

from src.settings import settings

HEADER = "x-write-token"


def has_write_token(request: Request) -> bool:
    """True when the request carries the configured write token."""
    configured = settings.demo_write_token
    supplied = request.headers.get(HEADER, "")
    if not configured or not supplied:
        return False
    return hmac.compare_digest(configured.encode("utf-8"), supplied.encode("utf-8"))


async def require_write_token(request: Request) -> None:
    """FastAPI dependency for mutating endpoints."""
    if not settings.demo_write_token:
        raise HTTPException(
            status_code=403,
            detail="Writes are disabled on this deployment (no DEMO_WRITE_TOKEN configured).",
        )
    if not has_write_token(request):
        raise HTTPException(
            status_code=401,
            detail="This needs the operator's write token. The public link is the read-only role.",
        )


def actor(request: Request) -> str:
    name = (request.headers.get("x-actor") or "Operator").strip()[:40]
    return name or "Operator"
