from __future__ import annotations

import hashlib
import hmac
import secrets
from datetime import datetime, timedelta

from fastapi import Cookie, Depends, Header, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.settings import settings
from app.models.user_account import UserAccount
from app.models.user_session import UserSession


SESSION_COOKIE_NAME = "yj_v2_token"


def hash_password(password: str, salt: str | None = None) -> str:
    salt = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), 120000)
    return f"{salt}${digest.hex()}"


def verify_password(password: str, password_hash: str) -> bool:
    try:
        salt, expected = password_hash.split("$", 1)
    except ValueError:
        return False
    actual = hash_password(password, salt).split("$", 1)[1]
    return hmac.compare_digest(actual, expected)


def parse_bearer_token(authorization: str | None) -> str | None:
    if not authorization:
        return None
    if authorization.lower().startswith("bearer "):
        return authorization.split(" ", 1)[1].strip()
    return authorization.strip()


def create_session(db: Session, user: UserAccount) -> str:
    token = secrets.token_urlsafe(32)
    session = UserSession(
        user_id=user.id,
        token=token,
        expires_at=datetime.utcnow() + timedelta(hours=settings.auth_session_hours),
    )
    user.last_login_at = datetime.utcnow()
    db.add(session)
    db.commit()
    return token


def get_user_by_token(db: Session, token: str | None) -> UserAccount | None:
    if not token:
        return None
    session = db.scalar(
        select(UserSession).where(
            UserSession.token == token,
            UserSession.expires_at > datetime.utcnow(),
        )
    )
    if not session:
        return None
    return db.get(UserAccount, session.user_id)


def get_current_user(
    authorization: str | None = Header(default=None),
    access_token: str | None = Query(default=None),
    session_cookie: str | None = Cookie(default=None, alias=SESSION_COOKIE_NAME),
    db: Session = Depends(get_db),
) -> UserAccount:
    token = parse_bearer_token(authorization) or access_token or session_cookie
    user = get_user_by_token(db, token)
    if not user:
        raise HTTPException(status_code=401, detail="authentication_required")
    if user.status != "active":
        raise HTTPException(status_code=403, detail="account_not_active")
    return user


def require_roles(*roles: str):
    def dependency(user: UserAccount = Depends(get_current_user)) -> UserAccount:
        if roles and user.role not in roles:
            raise HTTPException(status_code=403, detail="insufficient_permissions")
        return user

    return dependency
