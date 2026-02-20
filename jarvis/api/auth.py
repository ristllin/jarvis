"""Google OAuth authentication with email allowlist."""

from authlib.integrations.starlette_client import OAuth
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import RedirectResponse

from jarvis.config import settings
from jarvis.observability.logger import get_logger

log = get_logger("auth")

router = APIRouter(prefix="/api/auth", tags=["auth"])

# OAuth client (initialized when auth is enabled)
_oauth: OAuth | None = None


def _get_oauth() -> OAuth:
    global _oauth
    if _oauth is None:
        _oauth = OAuth()
        _oauth.register(
            name="google",
            client_id=settings.google_client_id,
            client_secret=settings.google_client_secret,
            server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
            client_kwargs={"scope": "openid email profile"},
        )
    return _oauth


def get_current_user(request: Request) -> dict:
    """Dependency: require authenticated user. Raises 401 if not logged in."""
    if not settings.auth_enabled:
        return {"email": "local", "name": "Local User"}
    user = request.session.get("user")
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return user


def optional_user(request: Request) -> dict | None:
    """Dependency: return user if logged in, else None."""
    if not settings.auth_enabled:
        return {"email": "local", "name": "Local User"}
    return request.session.get("user")


@router.get("/login")
async def login(request: Request):
    """Redirect to Google OAuth."""
    if not settings.auth_enabled:
        return RedirectResponse(url="/", status_code=302)
    if not settings.google_client_id or not settings.google_client_secret:
        raise HTTPException(
            status_code=500,
            detail="Google OAuth not configured. Set GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET.",
        )
    base = settings.auth_base_url.rstrip("/")
    redirect_uri = f"{base}/api/auth/callback"
    oauth = _get_oauth()
    return await oauth.google.authorize_redirect(request, redirect_uri)


@router.get("/callback")
async def auth_callback(request: Request):
    """Handle Google OAuth callback."""
    if not settings.auth_enabled:
        return RedirectResponse(url="/", status_code=302)
    oauth = _get_oauth()
    try:
        token = await oauth.google.authorize_access_token(request)
    except Exception as e:
        log.warning("oauth_callback_failed", error=str(e))
        raise HTTPException(status_code=400, detail="OAuth callback failed") from e
    userinfo = token.get("userinfo") or {}
    email = (userinfo.get("email") or "").strip().lower()
    if not email:
        raise HTTPException(status_code=403, detail="No email in user info")
    allowed = settings.allowed_emails_set
    if email not in allowed:
        log.warning("auth_rejected", email=email, allowed=list(allowed))
        raise HTTPException(status_code=403, detail="Access denied: email not authorized")
    request.session["user"] = {
        "email": email,
        "name": userinfo.get("name", ""),
        "picture": userinfo.get("picture"),
    }
    log.info("auth_success", email=email)
    return RedirectResponse(url="/", status_code=302)


@router.get("/me")
async def me(request: Request):
    """Return current user or 401."""
    if not settings.auth_enabled:
        return {"email": "local", "name": "Local User", "auth_enabled": False}
    user = request.session.get("user")
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return {**user, "auth_enabled": True}


@router.get("/logout")
@router.post("/logout")
async def logout(request: Request):
    """Clear session and redirect to login."""
    request.session.clear()
    if settings.auth_enabled:
        return RedirectResponse(url="/api/auth/login", status_code=302)
    return RedirectResponse(url="/", status_code=302)
