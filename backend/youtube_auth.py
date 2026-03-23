"""YouTube Auth Manager: Google OAuth2 flow and token lifecycle for YouTube downloads."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

from backend.errors import AuthenticationError

_AUTH_DIR = Path.home() / ".soccer-tracker"
_TOKEN_PATH = _AUTH_DIR / "auth.json"

# OAuth2 scopes for YouTube read-only access
_SCOPES = ["https://www.googleapis.com/auth/youtube.readonly"]

# Redirect URI must match the one configured in Google Cloud Console
_REDIRECT_URI = "http://127.0.0.1:8000/auth/youtube/callback"


def _get_client_config() -> dict:
    """Get OAuth client config from environment variables."""
    client_id = os.environ.get("GOOGLE_CLIENT_ID")
    client_secret = os.environ.get("GOOGLE_CLIENT_SECRET")
    if not client_id or not client_secret:
        raise AuthenticationError(
            "YouTube OAuth not configured. Set GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET."
        )
    return {
        "web": {
            "client_id": client_id,
            "client_secret": client_secret,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": [_REDIRECT_URI],
        }
    }


class YouTubeAuthManager:
    """Manages Google OAuth2 tokens for authenticated YouTube downloads."""

    def get_auth_url(self) -> str:
        """Return the Google OAuth2 consent URL for the user to authorize."""
        from google_auth_oauthlib.flow import Flow

        flow = Flow.from_client_config(
            _get_client_config(),
            scopes=_SCOPES,
            redirect_uri=_REDIRECT_URI,
        )
        auth_url, _ = flow.authorization_url(
            access_type="offline",
            include_granted_scopes="true",
            prompt="consent",
        )
        return auth_url

    def exchange_code(self, code: str) -> None:
        """Exchange the auth code for tokens and save to ~/.soccer-tracker/auth.json."""
        from google_auth_oauthlib.flow import Flow

        flow = Flow.from_client_config(
            _get_client_config(),
            scopes=_SCOPES,
            redirect_uri=_REDIRECT_URI,
        )
        try:
            flow.fetch_token(code=code)
            credentials = flow.credentials
        except Exception as exc:
            raise AuthenticationError(f"OAuth flow failed: {exc}") from exc

        refresh_token = getattr(credentials, "refresh_token", None)
        if not refresh_token and _TOKEN_PATH.exists():
            import json
            with open(_TOKEN_PATH, encoding="utf-8") as f:
                existing = json.load(f)
            refresh_token = existing.get("refresh_token")

        _AUTH_DIR.mkdir(parents=True, exist_ok=True)
        creds_dict = {
            "token": credentials.token,
            "refresh_token": refresh_token,
            "token_uri": getattr(credentials, "token_uri", "https://oauth2.googleapis.com/token"),
            "client_id": credentials.client_id,
            "client_secret": credentials.client_secret,
            "scopes": getattr(credentials, "scopes", None) or _SCOPES,
        }
        import json

        with open(_TOKEN_PATH, "w", encoding="utf-8") as f:
            json.dump(creds_dict, f, indent=2)

    def get_credentials(self) -> Optional[object]:
        """Return valid credentials or None if not connected."""
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials

        if not _TOKEN_PATH.exists():
            return None

        try:
            import json

            with open(_TOKEN_PATH, encoding="utf-8") as f:
                data = json.load(f)
            creds = Credentials(
                token=data.get("token"),
                refresh_token=data.get("refresh_token"),
                token_uri=data.get("token_uri", "https://oauth2.googleapis.com/token"),
                client_id=data.get("client_id"),
                client_secret=data.get("client_secret"),
                scopes=data.get("scopes", _SCOPES),
            )
            if creds.expired and creds.refresh_token:
                creds.refresh(Request())
            return creds
        except Exception:
            return None

    def revoke(self) -> None:
        """Delete the stored token file."""
        if _TOKEN_PATH.exists():
            _TOKEN_PATH.unlink()

    def is_connected(self) -> bool:
        """Return True if a valid (non-expired or refreshable) token exists."""
        return self.get_credentials() is not None

    def get_refresh_token(self) -> Optional[str]:
        """Return the refresh token for yt-dlp, or None if not connected."""
        creds = self.get_credentials()
        if creds is None:
            return None
        return getattr(creds, "refresh_token", None)
