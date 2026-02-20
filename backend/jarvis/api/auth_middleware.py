"""Middleware to enforce auth on protected API routes."""

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from jarvis.config import settings


class AuthMiddleware(BaseHTTPMiddleware):
    """Require auth for /api/* except /api/health and /api/auth/*."""

    async def dispatch(self, request: Request, call_next):
        if not settings.auth_enabled:
            return await call_next(request)
        path = request.url.path
        if path == "/api/health" or path.startswith("/api/auth/"):
            return await call_next(request)
        if not path.startswith("/api/"):
            return await call_next(request)
        user = request.session.get("user")
        if not user:
            return JSONResponse(
                status_code=401,
                content={"detail": "Not authenticated", "login_url": "/api/auth/login"},
            )
        return await call_next(request)
