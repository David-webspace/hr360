"""個人存取權杖（給 MCP client 用）。

- 明文只在建立時顯示一次，資料庫只存 SHA-256；外洩的資料庫無法還原權杖
- scope 分 read / action：read 只能查詢；action 才能建立、送出假單與開工單
  （給 AI agent 用的權杖應該用 read，外洩時影響範圍小很多）

python -m app.tokens create <username> [--scope read|action] [--days 30] [--name 說明]
"""

import argparse
import hashlib
import secrets
from datetime import UTC, datetime, timedelta

from sqlalchemy import text
from sqlalchemy.orm import Session

SCOPES = ("read", "action")
PREFIX = "hr360_"


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def create(db: Session, user_id: int, name: str, scope: str, days: int) -> dict:
    if scope not in SCOPES:
        raise ValueError("scope 只能是 read 或 action")
    if not 1 <= days <= 90:
        raise ValueError("有效天數 1–90 天")
    token = PREFIX + secrets.token_urlsafe(32)
    expires = datetime.now(UTC) + timedelta(days=days)
    tid = db.execute(text("""
        INSERT INTO api_tokens (user_id, name, token_hash, scope, expires_at, revoked) VALUES (:u, :n, :h, :s, :e, false) RETURNING id
    """), {"u": user_id, "n": name[:64], "h": _hash(token), "s": scope, "e": expires}).scalar_one()
    db.commit()
    return {"id": tid, "token": token, "scope": scope, "expires_at": expires.isoformat(), "note": "權杖只顯示這一次，請妥善保存"}


def resolve(db: Session, token: str) -> tuple[int, str] | None:
    if not token.startswith(PREFIX):
        return None
    row = db.execute(text("""
        UPDATE api_tokens SET last_used_at = now()
        WHERE token_hash = :h AND NOT revoked AND expires_at > now() RETURNING user_id, scope
    """), {"h": _hash(token)}).one_or_none()
    db.commit()
    return (row[0], row[1]) if row else None


def list_for(db: Session, user_id: int) -> list[dict]:
    rows = db.execute(text("""
        SELECT id, name, scope, expires_at, last_used_at, revoked, created_at FROM api_tokens WHERE user_id = :u ORDER BY id DESC
    """), {"u": user_id}).mappings().all()
    return [dict(r) for r in rows]


def revoke(db: Session, user_id: int, token_id: int) -> bool:
    n = db.execute(text("UPDATE api_tokens SET revoked = true WHERE id = :i AND user_id = :u"), {"i": token_id, "u": user_id}).rowcount
    db.commit()
    return n == 1


def main() -> None:
    from app.db import SessionLocal

    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("create")
    c.add_argument("username")
    c.add_argument("--scope", default="read", choices=SCOPES)
    c.add_argument("--days", type=int, default=30)
    c.add_argument("--name", default="MCP client")
    args = ap.parse_args()
    with SessionLocal() as db:
        uid = db.execute(text("SELECT id FROM users WHERE username = :u AND is_active"), {"u": args.username}).scalar()
        if uid is None:
            raise SystemExit("找不到啟用中的帳號")
        out = create(db, uid, args.name, args.scope, args.days)
    print(f"token: {out['token']}\nscope: {out['scope']}  expires: {out['expires_at']}\n（只顯示這一次）")


if __name__ == "__main__":
    main()
