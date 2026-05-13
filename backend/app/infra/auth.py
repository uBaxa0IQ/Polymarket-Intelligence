"""JWT authentication for single-user deployment."""
from __future__ import annotations

import hashlib
import hmac
import os
from datetime import datetime, timedelta, timezone

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

TOKEN_TTL_HOURS = 24
SECRET_KEY = os.environ.get("AUTH_SECRET_KEY", "change-me-in-production-env")
ALGORITHM = "HS256"

_bearer = HTTPBearer(auto_error=False)


def _get_credentials() -> tuple[str, str]:
    username = os.environ.get("ADMIN_USERNAME", "admin")
    password = os.environ.get("ADMIN_PASSWORD", "admin")
    return username, password


def _credential_digest(value: str) -> bytes:
    return hashlib.sha256(value.encode("utf-8")).digest()


def verify_login(username: str, password: str) -> bool:
    """Constant-time check; avoids distinguishing wrong username vs wrong password."""
    expected_user, expected_pass = _get_credentials()
    user_ok = hmac.compare_digest(_credential_digest(username), _credential_digest(expected_user))
    pass_ok = hmac.compare_digest(_credential_digest(password), _credential_digest(expected_pass))
    return all((user_ok, pass_ok))


def create_access_token() -> str:
    try:
        from jose import jwt
    except ImportError:
        # Fallback: simple signed token without jose
        import hashlib, hmac, base64, json
        payload = {"exp": (datetime.now(timezone.utc) + timedelta(hours=TOKEN_TTL_HOURS)).timestamp()}
        data = base64.urlsafe_b64encode(json.dumps(payload).encode()).decode()
        sig = hmac.new(SECRET_KEY.encode(), data.encode(), hashlib.sha256).hexdigest()
        return f"{data}.{sig}"

    expire = datetime.now(timezone.utc) + timedelta(hours=TOKEN_TTL_HOURS)
    return jwt.encode({"exp": expire}, SECRET_KEY, algorithm=ALGORITHM)


def _decode_token(token: str) -> bool:
    try:
        from jose import jwt, JWTError
        jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return True
    except Exception:
        pass

    # Fallback verifier
    try:
        import hashlib, hmac, base64, json
        parts = token.rsplit(".", 1)
        if len(parts) != 2:
            return False
        data, sig = parts
        expected = hmac.new(SECRET_KEY.encode(), data.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(sig, expected):
            return False
        payload = json.loads(base64.urlsafe_b64decode(data + "=="))
        if payload.get("exp", 0) < datetime.now(timezone.utc).timestamp():
            return False
        return True
    except Exception:
        return False


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> str:
    if credentials is None or not _decode_token(credentials.credentials):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    username, _ = _get_credentials()
    return username
