"""Shared-secret gate for the demo's write paths.

The public demo has no user accounts. With PUBLIC_WRITES on (the default)
anyone may use the three workflow systems - a saved draft, a submitted
revision, a review decision, a confirmed docket - under a per-address write
limit; the working copy returns to the build on every cold start. Resetting the
demo always needs the operator's secret, sent as `X-Write-Token` (visit once
with `?write_token=<value>`; the frontend keeps it in sessionStorage).

With PUBLIC_WRITES off every write needs the secret. Fail closed: no token
configured then means writes are refused everywhere.

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


async def require_write(request: Request) -> None:
    """FastAPI dependency for the workflow systems' writes."""
    if has_write_token(request):
        return
    if not settings.public_writes:
        await require_write_token(request)
        return
    from src.app.services.rate_limit import enforce_write_rate_limit  # rate_limit imports this module
    enforce_write_rate_limit(request)


def actor(request: Request) -> str:
    name = (request.headers.get("x-actor") or "Operator").strip()[:40]
    return name or "Operator"
