from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.user_account import UserAccount
from app.schemas.user_account import UserAccountOut, UserAccountUpsert, UserSummaryOut
from app.services.auth import hash_password, require_roles
from app.services.text_normalize import normalize_text


router = APIRouter()

ROLE_MATRIX = {
    "admin": ["平台配置", "授权与年度认证", "事实源接入与导入", "告警策略与阈值", "人员审批与角色分配"],
    "manager": ["告警确认与派工", "工单调度", "巡检计划管理", "控制平台只读审计", "报表与汇总查看"],
    "technician": ["现场维修", "移动端工单执行", "拍照上传", "巡检签到", "设备与点位查询"],
    "viewer": ["只读总览", "告警查看", "拓扑查看", "报表查看"],
}


def _safe_user_text(value: str | None, fallback: str = "") -> str:
    text = normalize_text(value).strip()
    if not text:
        return fallback
    if text.replace("?", "").replace("？", "").strip() == "":
        return fallback or "未命名"
    return text


def _to_out(row: UserAccount) -> UserAccountOut:
    username = normalize_text(row.username)
    return UserAccountOut(
        id=row.id,
        username=username,
        display_name=_safe_user_text(row.display_name, username),
        role=row.role,
        status=row.status,
        department=_safe_user_text(row.department, ""),
        mobile=normalize_text(row.mobile),
        email=normalize_text(row.email),
        account_source=row.account_source,
        password_ready=row.password_ready,
        last_login_at=row.last_login_at,
        approved_at=row.approved_at,
        notes=_safe_user_text(row.notes, ""),
    )


@router.get("/summary", response_model=UserSummaryOut)
def summary(db: Session = Depends(get_db)) -> UserSummaryOut:
    rows = db.scalars(select(UserAccount).order_by(UserAccount.updated_at.desc())).all()
    role_counts: dict[str, int] = {}
    status_counts: dict[str, int] = {}
    active_count = 0
    pending_count = 0
    for row in rows:
        role_counts[row.role] = role_counts.get(row.role, 0) + 1
        status_counts[row.status] = status_counts.get(row.status, 0) + 1
        if row.status == "active":
            active_count += 1
        if row.status == "pending":
            pending_count += 1
    return UserSummaryOut(
        account_count=len(rows),
        active_count=active_count,
        pending_count=pending_count,
        role_breakdown=[
            {"role": key, "count": value}
            for key, value in sorted(role_counts.items(), key=lambda item: (-item[1], item[0]))
        ],
        status_breakdown=[
            {"status": key, "count": value}
            for key, value in sorted(status_counts.items(), key=lambda item: (-item[1], item[0]))
        ],
        recent_accounts=[_to_out(row) for row in rows[:6]],
    )


@router.get("/accounts", response_model=list[UserAccountOut])
def list_accounts(
    db: Session = Depends(get_db),
    q: str = Query(default=""),
    role: str = Query(default=""),
    status: str = Query(default=""),
) -> list[UserAccountOut]:
    stmt = select(UserAccount).order_by(UserAccount.updated_at.desc(), UserAccount.id.desc())
    if q:
        like = f"%{q.strip()}%"
        stmt = stmt.where(
            UserAccount.username.ilike(like)
            | UserAccount.display_name.ilike(like)
            | UserAccount.department.ilike(like)
            | UserAccount.mobile.ilike(like)
        )
    if role:
        stmt = stmt.where(UserAccount.role == role)
    if status:
        stmt = stmt.where(UserAccount.status == status)
    return [_to_out(row) for row in db.scalars(stmt).all()]


@router.get("/role-matrix")
def role_matrix() -> list[dict]:
    return [{"role": role, "capabilities": capabilities} for role, capabilities in ROLE_MATRIX.items()]


@router.post("/accounts", response_model=UserAccountOut)
def create_account(
    payload: UserAccountUpsert,
    db: Session = Depends(get_db),
    _: UserAccount = Depends(require_roles("admin")),
) -> UserAccountOut:
    existing = db.scalar(select(UserAccount).where(UserAccount.username == payload.username.strip()))
    if existing:
        raise HTTPException(status_code=409, detail="username_exists")
    data = payload.model_dump(exclude={"initial_password"})
    row = UserAccount(**data)
    initial_password = payload.initial_password.strip()
    if initial_password:
        row.password_hash = hash_password(initial_password)
        row.password_ready = True
    elif row.password_ready:
        row.password_hash = hash_password(f"{row.role}123")
    if row.status == "active":
        row.approved_at = datetime.utcnow()
    db.add(row)
    db.commit()
    db.refresh(row)
    return _to_out(row)


@router.put("/accounts/{account_id}", response_model=UserAccountOut)
def update_account(
    account_id: int,
    payload: UserAccountUpsert,
    db: Session = Depends(get_db),
    _: UserAccount = Depends(require_roles("admin")),
) -> UserAccountOut:
    row = db.get(UserAccount, account_id)
    if not row:
        raise HTTPException(status_code=404, detail="account_not_found")
    conflict = db.scalar(
        select(UserAccount).where(
            UserAccount.username == payload.username.strip(),
            UserAccount.id != account_id,
        )
    )
    if conflict:
        raise HTTPException(status_code=409, detail="username_exists")
    previous_status = row.status
    for key, value in payload.model_dump(exclude={"initial_password"}).items():
        setattr(row, key, value)
    initial_password = payload.initial_password.strip()
    if initial_password:
        row.password_hash = hash_password(initial_password)
        row.password_ready = True
    if previous_status != "active" and row.status == "active" and not row.approved_at:
        row.approved_at = datetime.utcnow()
    db.commit()
    db.refresh(row)
    return _to_out(row)


@router.post("/accounts/{account_id}/approve", response_model=UserAccountOut)
def approve_account(
    account_id: int,
    db: Session = Depends(get_db),
    _: UserAccount = Depends(require_roles("admin", "manager")),
) -> UserAccountOut:
    row = db.get(UserAccount, account_id)
    if not row:
        raise HTTPException(status_code=404, detail="account_not_found")
    row.status = "active"
    if not row.approved_at:
        row.approved_at = datetime.utcnow()
    db.commit()
    db.refresh(row)
    return _to_out(row)


@router.post("/accounts/{account_id}/disable", response_model=UserAccountOut)
def disable_account(
    account_id: int,
    db: Session = Depends(get_db),
    _: UserAccount = Depends(require_roles("admin", "manager")),
) -> UserAccountOut:
    row = db.get(UserAccount, account_id)
    if not row:
        raise HTTPException(status_code=404, detail="account_not_found")
    row.status = "disabled"
    db.commit()
    db.refresh(row)
    return _to_out(row)


@router.post("/accounts/{account_id}/reset-password")
def reset_password(
    account_id: int,
    db: Session = Depends(get_db),
    _: UserAccount = Depends(require_roles("admin")),
) -> dict:
    row = db.get(UserAccount, account_id)
    if not row:
        raise HTTPException(status_code=404, detail="account_not_found")
    temp_password = f"{row.role}123"
    row.password_hash = hash_password(temp_password)
    row.password_ready = True
    db.commit()
    return {"ok": True, "temporary_password": temp_password}
