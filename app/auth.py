"""HTTP Basic Auth gate for the dashboard, the API and generated clips.

The README has always promised this protection; the previous code imported the helpers but never
installed any middleware, so every route was publicly reachable. This is a pure ASGI middleware so
large uploads are streamed through untouched.
"""
import base64
import binascii
import os
import secrets

from starlette.responses import JSONResponse, Response

PUBLIC_PATHS = {"/health"}


def _credentials() -> tuple[str, str]:
    return os.getenv("CLIPRUSH_AUTH_USERNAME", ""), os.getenv("CLIPRUSH_AUTH_PASSWORD", "")


def _header_matches(header: str, username: str, password: str) -> bool:
    scheme, _, value = (header or "").partition(" ")
    if scheme.lower() != "basic" or not value:
        return False
    try:
        supplied = base64.b64decode(value.strip(), validate=True).decode("utf-8")
    except (binascii.Error, UnicodeDecodeError, ValueError):
        return False
    given_user, sep, given_pass = supplied.partition(":")
    if not sep:
        return False
    # Evaluate both comparisons (no short-circuit) and compare in constant time.
    user_ok = secrets.compare_digest(given_user.encode(), username.encode())
    pass_ok = secrets.compare_digest(given_pass.encode(), password.encode())
    return user_ok and pass_ok


class BasicAuthMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope.get("path") in PUBLIC_PATHS:
            return await self.app(scope, receive, send)
        if os.getenv("CLIPRUSH_DISABLE_AUTH") == "1":
            return await self.app(scope, receive, send)

        username, password = _credentials()
        if not username or not password:
            response: Response = JSONResponse(
                {"detail": "Deployment credentials are not configured. Set CLIPRUSH_AUTH_USERNAME and "
                           "CLIPRUSH_AUTH_PASSWORD (or CLIPRUSH_DISABLE_AUTH=1 for local-only use)."},
                status_code=503)
            return await response(scope, receive, send)

        headers = {k.decode("latin-1").lower(): v.decode("latin-1") for k, v in scope.get("headers", [])}
        if _header_matches(headers.get("authorization", ""), username, password):
            return await self.app(scope, receive, send)

        response = Response("Authentication required.", status_code=401,
                            headers={"WWW-Authenticate": 'Basic realm="ClipRush AI", charset="UTF-8"'})
        return await response(scope, receive, send)
