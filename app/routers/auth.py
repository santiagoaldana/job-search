"""Google OAuth authentication router."""

import os
from typing import Optional
from fastapi import APIRouter, Request, Response, HTTPException
from fastapi.responses import RedirectResponse
from authlib.integrations.httpx_client import AsyncOAuth2Client
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired

router = APIRouter()

GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_URL = "https://www.googleapis.com/oauth2/v3/userinfo"

SESSION_DAYS = 7


def _signer():
    secret = os.environ.get("SESSION_SECRET", "dev-secret-change-me")
    return URLSafeTimedSerializer(secret)


def get_session_email(request: Request) -> Optional[str]:
    token = request.cookies.get("session")
    if not token:
        return None
    try:
        data = _signer().loads(token, max_age=SESSION_DAYS * 86400)
        return data.get("email")
    except (BadSignature, SignatureExpired):
        return None


def _make_session_cookie(email: str) -> str:
    return _signer().dumps({"email": email})


def _redirect_uri(request: Request) -> str:
    # Use the request's base URL so it works both locally and via tunnel
    base = str(request.base_url).rstrip("/")
    return f"{base}/auth/callback"


@router.get("/login")
async def login(request: Request):
    client_id = os.environ.get("GOOGLE_CLIENT_ID")
    if not client_id:
        raise HTTPException(status_code=500, detail="Google OAuth not configured. Set GOOGLE_CLIENT_ID in .env")

    redirect_uri = _redirect_uri(request)
    client = AsyncOAuth2Client(client_id=client_id, redirect_uri=redirect_uri)
    uri, state = client.create_authorization_url(
        GOOGLE_AUTH_URL,
        scope="openid email profile",
        access_type="offline",
        prompt="select_account",
    )
    response = RedirectResponse(uri)
    response.set_cookie("oauth_state", state, httponly=True, samesite="lax", max_age=600)
    return response


@router.get("/callback")
async def callback(request: Request, code: str = None, state: str = None, error: str = None):
    if error:
        return RedirectResponse("/?auth_error=" + error)

    client_id = os.environ.get("GOOGLE_CLIENT_ID")
    client_secret = os.environ.get("GOOGLE_CLIENT_SECRET")
    allowed_email = os.environ.get("ALLOWED_EMAIL", "aldana.santiago@gmail.com")
    redirect_uri = _redirect_uri(request)

    client = AsyncOAuth2Client(
        client_id=client_id,
        client_secret=client_secret,
        redirect_uri=redirect_uri,
    )

    token = await client.fetch_token(GOOGLE_TOKEN_URL, code=code)
    userinfo_resp = await client.get(GOOGLE_USERINFO_URL)
    userinfo = userinfo_resp.json()
    email = userinfo.get("email", "")

    if email.lower() != allowed_email.lower():
        return RedirectResponse("/?auth_error=unauthorized")

    session_token = _make_session_cookie(email)
    response = RedirectResponse("/")
    response.set_cookie(
        "session", session_token,
        httponly=True, samesite="lax",
        max_age=SESSION_DAYS * 86400,
        secure=False,  # set True when behind HTTPS-only tunnel
    )
    response.delete_cookie("oauth_state")
    return response


@router.get("/logout")
def logout():
    response = RedirectResponse("/auth/login")
    response.delete_cookie("session")
    return response


@router.get("/me")
def me(request: Request):
    email = get_session_email(request)
    if not email:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return {"email": email, "authenticated": True}
