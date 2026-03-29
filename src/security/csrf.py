"""CSRF protection middleware — Double Submit Cookie pattern.

Sets a csrf_token cookie on every response. POST/PUT/DELETE requests
with Content-Type form data must include a matching csrf_token field.
JSON API requests (Content-Type: application/json) are exempt — they
are protected by CORS + SameSite cookie policy.
"""

from __future__ import annotations

import secrets

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

_SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})
_COOKIE_NAME = "csrf_token"
_FIELD_NAME = "csrf_token"


class CSRFMiddleware(BaseHTTPMiddleware):
    """Double Submit Cookie CSRF protection for HTML form submissions."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        # Make CSRF token available on request.state for Jinja2 templates
        token = request.cookies.get(_COOKIE_NAME) or secrets.token_urlsafe(32)
        request.state.csrf_token = token

        # Safe methods: just ensure cookie exists on response
        if request.method in _SAFE_METHODS:
            response = await call_next(request)
            if _COOKIE_NAME not in request.cookies:
                response.set_cookie(_COOKIE_NAME, token, httponly=False, samesite="lax", path="/")
            return response

        # Exempt JSON API requests (protected by CORS + SameSite)
        content_type = request.headers.get("content-type", "")
        if "application/json" in content_type:
            return await call_next(request)

        # Unsafe methods with form data: verify CSRF token
        cookie_token = request.cookies.get(_COOKIE_NAME)
        if not cookie_token:
            return JSONResponse(
                status_code=403,
                content={"detail": "CSRF cookie missing. Reload the page."},
            )

        # Read form field
        form = await request.form()
        form_token = form.get(_FIELD_NAME, "")
        await request.close()  # release form body

        if not secrets.compare_digest(str(cookie_token), str(form_token)):
            return JSONResponse(
                status_code=403,
                content={"detail": "CSRF token mismatch."},
            )

        return await call_next(request)
