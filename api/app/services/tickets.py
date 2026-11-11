import json

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.auth import Principal
from app.config import TZ

CATEGORIES = ("leave", "payroll", "insurance", "benefits", "policy", "harassment", "dispute", "other")


def create(db: Session, p: Principal, category: str, summary: str, conversation_id: int | None = None,
           context: dict | None = None) -> dict:
    category = category if category in CATEGORIES else "other"
    confidential = category == "harassment"
    # 性騷擾申訴不保存對話內容快照，只留摘要，由申訴處理小組另行聯繫
    snapshot = None if confidential else context
    tid = db.execute(text("""
        INSERT INTO tickets (requester_id, conversation_id, category, summary, context_snapshot, status, confidential)
        VALUES (:u, :c, :cat, :s, CAST(:ctx AS jsonb), 'open', :conf) RETURNING id
    """), {"u": p.user_id, "c": conversation_id, "cat": category, "s": summary[:2000],
           "ctx": json.dumps(snapshot, ensure_ascii=False, default=str) if snapshot else None, "conf": confidential}).scalar_one()
    db.commit()
    return {"ticket_id": tid, "status": "open", "confidential": confidential,
            "next_step": "已轉交人資部，可在「我的工單」查看進度" + ("；性騷擾申訴由申訴處理小組保密處理" if confidential else "")}


def list_for(db: Session, p: Principal) -> list[dict]:
    hr = bool(p.roles & {"hrbp", "payroll"})
    # HR 看得到全部一般工單；機密工單只有人資經理（全公司 HRBP）看得到
    sees_confidential = any(path.count("/") == 2 for path in p.hrbp_paths)
    rows = db.execute(text("""
        SELECT t.id, t.category, t.summary, t.status, t.confidential, t.created_at, u.username AS requester
        FROM tickets t JOIN users u ON u.id = t.requester_id
        WHERE t.requester_id = :u OR (:hr AND (NOT t.confidential OR :conf))
        ORDER BY t.created_at DESC LIMIT 100
    """), {"u": p.user_id, "hr": hr, "conf": sees_confidential}).mappings().all()
    return [{**dict(r), "created_at": r["created_at"].astimezone(TZ).isoformat(timespec="minutes")} for r in rows]
