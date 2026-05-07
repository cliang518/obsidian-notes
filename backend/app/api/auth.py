from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.user_account import UserAccount
from app.models.user_session import UserSession
from app.schemas.auth import (
    AuthChangePasswordRequest,
    AuthLoginRequest,
    AuthRegisterRequest,
    AuthTokenResponse,
    AuthUserOut,
)
from app.core.settings import settings
from app.services.auth import SESSION_COOKIE_NAME, create_session, get_current_user, hash_password, verify_password
from app.services.text_normalize import normalize_text


router = APIRouter()


def _to_user(row: UserAccount) -> AuthUserOut:
    return AuthUserOut(
        id=row.id,
        username=normalize_text(row.username),
        display_name=normalize_text(row.display_name),
        role=row.role,
        status=row.status,
        department=normalize_text(row.department),
        mobile=normalize_text(row.mobile),
        email=normalize_text(row.email),
        account_source=row.account_source,
        password_ready=row.password_ready,
        last_login_at=row.last_login_at,
        approved_at=row.approved_at,
        notes=normalize_text(row.notes),
    )


@router.post("/login", response_model=AuthTokenResponse)
def login(payload: AuthLoginRequest, response: Response, db: Session = Depends(get_db)) -> AuthTokenResponse:
    username = normalize_text(payload.username).strip()
    row = db.scalar(select(UserAccount).where(UserAccount.username == username))
    if not row or not verify_password(payload.password, row.password_hash):
        raise HTTPException(status_code=401, detail="invalid_username_or_password")
    if row.status != "active":
        raise HTTPException(status_code=403, detail="account_not_active")
    token = create_session(db, row)
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=token,
        httponly=True,
        samesite="lax",
        secure=False,
        max_age=settings.auth_session_hours * 3600,
        path="/",
    )
    db.refresh(row)
    return AuthTokenResponse(access_token=token, user=_to_user(row))


@router.post("/register")
def register(payload: AuthRegisterRequest, db: Session = Depends(get_db)) -> dict:
    username = normalize_text(payload.username).strip()
    if not username:
        raise HTTPException(status_code=400, detail="username_required")
    existing = db.scalar(select(UserAccount).where(UserAccount.username == username))
    if existing:
        raise HTTPException(status_code=409, detail="username_exists")

    row = UserAccount(
        username=username,
        display_name=normalize_text(payload.display_name).strip() or username,
        role="technician",
        status="pending",
        department=normalize_text(payload.department).strip(),
        mobile=normalize_text(payload.mobile).strip(),
        email=normalize_text(payload.email).strip(),
        account_source="self_signup",
        password_ready=True,
        password_hash=hash_password(payload.password),
        notes=normalize_text(payload.notes).strip() or "用户自主注册，待管理员审批开通。",
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return {
        "ok": True,
        "message": "registration_submitted",
        "account": _to_user(row),
    }


@router.post("/logout")
def logout(response: Response, current_user: UserAccount = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    db.execute(delete(UserSession).where(UserSession.user_id == current_user.id))
    db.commit()
    response.delete_cookie(key=SESSION_COOKIE_NAME, path="/")
    return {"ok": True}


@router.get("/me", response_model=AuthUserOut)
def me(current_user: UserAccount = Depends(get_current_user)) -> AuthUserOut:
    return _to_user(current_user)


@router.post("/change-password")
def change_password(
    payload: AuthChangePasswordRequest,
    current_user: UserAccount = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    row = db.get(UserAccount, current_user.id)
    if not row:
        raise HTTPException(status_code=404, detail="user_not_found")
    if not verify_password(payload.current_password, row.password_hash):
        raise HTTPException(status_code=400, detail="current_password_invalid")
    row.password_hash = hash_password(payload.new_password)
    row.password_ready = True
    row.updated_at = datetime.utcnow()
    db.commit()
    return {"ok": True}
