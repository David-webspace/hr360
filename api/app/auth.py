"""登入與身分。Principal 只從資料庫組出，任何對話內容、工具參數都無法改變它。"""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import jwt
from fastapi import Depends, HTTPException, Request
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.config import settings
from app.db import get_db
from app.security import hash_password, verify_password

COOKIE = "hr360_session"
LOGIN_FAILED = "帳號或密碼錯誤"
# 帳號不存在時仍做一次雜湊比對，避免用回應時間差判斷帳號是否存在
_DUMMY_HASH = hash_password("timing-equalizer")


@dataclass(frozen=True)
class Principal:
    user_id: int
    username: str
    emp_id: int | None
    name: str
    roles: frozenset[str]
    managed_paths: tuple[str, ...]  # 自己擔任主管的單位路徑
    hrbp_paths: tuple[str, ...]
    channel: str = "web"

    @property
    def is_payroll(self) -> bool:
        return "payroll" in self.roles


def load_principal(db: Session, user_id: int, channel: str = "web") -> Principal:
    u = db.execute(text("""
        SELECT u.id, u.username, u.employee_id, u.is_active, e.name, e.status
        FROM users u LEFT JOIN employees e ON e.id = u.employee_id WHERE u.id = :id
    """), {"id": user_id}).mappings().one_or_none()
    if u is None or not u["is_active"] or u["status"] == "terminated":
        raise HTTPException(401, "請重新登入")
    roles = db.execute(text("""
        SELECT r.role, o.path FROM user_roles r LEFT JOIN org_units o ON o.id = r.scope_org_unit_id WHERE r.user_id = :id
    """), {"id": user_id}).all()
    managed = db.execute(text("SELECT path FROM org_units WHERE head_emp_id = :e"), {"e": u["employee_id"]}).scalars().all() \
        if u["employee_id"] else []
    return Principal(
        user_id=u["id"], username=u["username"], emp_id=u["employee_id"], name=u["name"] or u["username"],
        roles=frozenset(r for r, _ in roles), managed_paths=tuple(managed),
        hrbp_paths=tuple(p for r, p in roles if r == "hrbp" and p), channel=channel,
    )


def authenticate(db: Session, username: str, password: str) -> int | None:
    row = db.execute(text("""
        SELECT u.id, u.password_hash, u.is_active FROM users u WHERE u.username = :u
    """), {"u": username}).mappings().one_or_none()
    ok = verify_password(password, row["password_hash"] if row else _DUMMY_HASH)
    return row["id"] if row and ok and row["is_active"] else None


def issue_token(user_id: int) -> str:
    now = datetime.now(UTC)
    return jwt.encode({"sub": str(user_id), "iat": now, "exp": now + timedelta(hours=settings.jwt_ttl_hours)},
                      settings.jwt_secret, algorithm="HS256")


def current_principal(request: Request, db: Session = Depends(get_db)) -> Principal:
    token = request.cookies.get(COOKIE)
    if not token:
        raise HTTPException(401, "請先登入")
    try:
        claims = jwt.decode(token, settings.jwt_secret, algorithms=["HS256"])
    except jwt.PyJWTError:
        raise HTTPException(401, "請重新登入")
    return load_principal(db, int(claims["sub"]))


def require_role(*roles: str):
    def dep(p: Principal = Depends(current_principal)) -> Principal:
        if not p.roles & set(roles):
            raise HTTPException(403, "沒有權限")
        return p
    return dep
