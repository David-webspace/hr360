import logging
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from urllib.parse import quote

from fastapi import Depends, FastAPI, HTTPException, Query, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.agent import audit
from app.agent.check import run as llm_check
from app.agent.llm import get_client, not_configured
from app.agent.loop import run_chat
from app.auth import COOKIE, LOGIN_FAILED, Principal, authenticate, current_principal, issue_token, load_principal, require_role
from app.config import TZ, settings
from app.db import engine, get_db
from app.policy import DENIED, PolicyDenied
from app.ratelimit import SlidingWindow
from app import tokens
from app.mcp_server import http_app as mcp_http_app
from app.mcp_server import mcp
from app.services import attachments, hr, leave, reports, tickets

log = logging.getLogger("hr360")


@asynccontextmanager
async def lifespan(_: FastAPI):
    async with mcp.session_manager.run():
        yield


app = FastAPI(title="hr360", lifespan=lifespan, docs_url="/docs" if settings.enable_api_docs else None,
              redoc_url=None, openapi_url="/openapi.json" if settings.enable_api_docs else None)

login_limit = SlidingWindow(10, 300)
chat_limit = SlidingWindow(settings.chat_rate_per_minute, 60)
# 每張上傳的圖都會送進看圖模型（付費），跟聊天分開限流
upload_limit = SlidingWindow(settings.upload_daily_limit, 86400)


@app.exception_handler(PolicyDenied)
def _denied(_: Request, __: PolicyDenied) -> JSONResponse:
    return JSONResponse({"detail": DENIED}, status_code=404)


@app.exception_handler(attachments.AttachmentError)
def _attachment_error(_: Request, e: attachments.AttachmentError) -> JSONResponse:
    return JSONResponse({"detail": str(e)}, status_code=400)


@app.exception_handler(leave.LeaveError)
def _leave_error(_: Request, e: leave.LeaveError) -> JSONResponse:
    return JSONResponse({"detail": str(e)}, status_code=400)


@app.get("/health")
def health() -> dict:
    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))
    return {"status": "ok"}


class LoginIn(BaseModel):
    username: str = Field(max_length=64)
    password: str = Field(max_length=128)


@app.post("/api/auth/login")
def login(body: LoginIn, request: Request, response: Response, db: Session = Depends(get_db)) -> dict:
    login_limit.check(f"{request.client.host if request.client else '-'}:{body.username}")
    uid = authenticate(db, body.username, body.password)
    if uid is None:
        audit.write(db, None, "login_failed", question=body.username)
        raise HTTPException(401, LOGIN_FAILED)
    p = load_principal(db, uid)
    response.set_cookie(COOKIE, issue_token(uid), httponly=True, samesite="lax", secure=settings.cookie_secure,
                        max_age=settings.jwt_ttl_hours * 3600)
    audit.write(db, p, "login")
    return {"username": p.username, "name": p.name, "roles": sorted(p.roles)}


@app.post("/api/auth/logout")
def logout(response: Response) -> dict:
    response.delete_cookie(COOKIE)
    return {"ok": True}


@app.get("/api/me")
def me(p: Principal = Depends(current_principal), db: Session = Depends(get_db)) -> dict:
    row = db.execute(text("""SELECT e.emp_no, o.name AS unit, e.title FROM employees e JOIN org_units o ON o.id = e.org_unit_id
                             WHERE e.id = :e"""), {"e": p.emp_id or -1}).mappings().one_or_none()
    return {"username": p.username, "name": p.name, "roles": sorted(p.roles), "is_manager": bool(p.managed_paths),
            "is_hr": bool(p.roles & {"hrbp", "payroll"}), **(dict(row) if row else {})}


class ChatIn(BaseModel):
    message: str = Field(min_length=1, max_length=2000)
    conversation_id: int | None = None
    attachment_ids: list[str] = Field(default_factory=list, max_length=3)


def _tokens_today(db: Session, user_id: int) -> int:
    start = datetime.now(TZ).replace(hour=0, minute=0, second=0, microsecond=0).astimezone(UTC)
    return db.execute(text("""SELECT COALESCE(SUM(input_tokens + output_tokens + cache_read_tokens + cache_write_tokens), 0)
                              FROM audit_log WHERE user_id = :u AND ts >= :s"""), {"u": user_id, "s": start}).scalar()


@app.post("/api/chat")
def chat(body: ChatIn, p: Principal = Depends(current_principal), db: Session = Depends(get_db)) -> dict:
    # 會呼叫付費模型的端點：單獨限流＋每人每日 token 上限，不跟其他端點共用額度
    if reason := not_configured():
        raise HTTPException(503, f"HR 助理尚未接上模型（{reason}）。假勤、薪資、簽核頁面不受影響；請管理員依 README 設定 .env 後重啟。")
    chat_limit.check(str(p.user_id))
    if _tokens_today(db, p.user_id) >= settings.chat_daily_token_cap:
        raise HTTPException(429, "今日 HR 助理使用量已達上限，請明天再試或洽人資")
    try:
        r = run_chat(db, get_client(), p, body.message.strip(), body.conversation_id,
                     attachment_ids=body.attachment_ids)
    except Exception:
        db.rollback()
        log.exception("chat failed")
        raise HTTPException(503, "HR 助理暫時無法回應，請稍後再試")
    return {"conversation_id": r.conversation_id, "answer": r.answer, "drafts": r.drafts, "citations": r.citations,
            "suggestions": r.suggestions, "exports": r.exports, "meta": {"intent": r.intent, "model": r.model, "routed_by": r.routed_by, "grounding_ok": r.grounding_ok,
                     "escalated": r.escalated, "tools": r.tools, "latency_ms": r.latency_ms, "cost_usd": r.cost_usd,
                     "tokens": vars(r.usage)}}


@app.post("/api/attachments")
async def upload_attachment(request: Request, name: str = "", p: Principal = Depends(current_principal),
                            db: Session = Depends(get_db)) -> dict:
    # 先看宣稱大小再讀內容，避免把超大檔整個讀進記憶體；讀完再以實際長度檢查一次（宣稱值可以造假）
    if int(request.headers.get("content-length") or 0) > attachments.MAX_BYTES:
        raise HTTPException(413, "檔案超過 5MB，請壓縮或重新拍攝")
    upload_limit.check(str(p.user_id))
    out = attachments.save(db, p, await request.body(), name)
    audit.write(db, p, "attachment_upload", question=out["id"])
    return out


@app.get("/api/attachments/{aid}")
def get_attachment(aid: str, p: Principal = Depends(current_principal), db: Session = Depends(get_db)) -> Response:
    # no-store：快取的原圖會在同一台電腦換人登入後直接從瀏覽器取出，繞過權限檢查
    return Response(attachments.image_bytes(attachments.viewable(db, p, aid)), media_type="image/jpeg",
                    headers={"cache-control": "no-store"})


@app.get("/api/exports/{eid}")
def get_export(eid: str, p: Principal = Depends(current_principal), db: Session = Depends(get_db)) -> Response:
    name, media_type, content = reports.download(db, p, eid)
    audit.write(db, p, "report_download", question=name)
    # filename*：中文檔名用 RFC 5987 編碼；no-store 同附件，換人登入後不能從瀏覽器快取取出
    return Response(content, media_type=media_type, headers={
        "content-disposition": f"attachment; filename=\"export.{name.rsplit('.', 1)[-1]}\"; filename*=UTF-8''{quote(name)}",
        "cache-control": "no-store"})


@app.get("/api/conversations")
def conversations(p: Principal = Depends(current_principal), db: Session = Depends(get_db)) -> list[dict]:
    rows = db.execute(text("""
        SELECT c.id, c.title, COALESCE(MAX(m.created_at), c.created_at) AS last_at
        FROM conversations c LEFT JOIN messages m ON m.conversation_id = c.id
        WHERE c.user_id = :u GROUP BY c.id ORDER BY last_at DESC LIMIT 10
    """), {"u": p.user_id}).mappings().all()
    return [dict(r) for r in rows]


@app.get("/api/conversations/{cid}/messages")
def conversation_messages(cid: int, p: Principal = Depends(current_principal), db: Session = Depends(get_db)) -> list[dict]:
    rows = [dict(r) for r in db.execute(text("""
        SELECT m.role, m.text, m.meta, m.created_at FROM messages m JOIN conversations c ON c.id = m.conversation_id
        WHERE c.id = :c AND c.user_id = :u ORDER BY m.id"""), {"c": cid, "u": p.user_id}).mappings().all()]
    # 草稿卡片要顯示「現在」的狀態（可能已送出、核准或取消），不是建立當下的狀態
    ids = [d["draft_id"] for r in rows if r["meta"] for d in r["meta"].get("drafts", [])]
    if ids:
        status = dict(db.execute(text("SELECT id, status FROM leave_requests WHERE id = ANY(:ids) AND emp_id = :me"),
                                 {"ids": ids, "me": p.emp_id or -1}).all())
        for r in rows:
            for d in (r["meta"] or {}).get("drafts", []):
                d["status"] = status.get(d["draft_id"], d["status"])
    return rows


@app.get("/api/leave/balance")
def my_balance(p: Principal = Depends(current_principal), db: Session = Depends(get_db)) -> dict:
    return hr.leave_balance(db, p)


@app.get("/api/leave/requests")
def my_requests(p: Principal = Depends(current_principal), db: Session = Depends(get_db)) -> list[dict]:
    return leave.my_requests(db, p)


@app.post("/api/leave/requests/{rid}/submit")
def submit(rid: int, p: Principal = Depends(current_principal), db: Session = Depends(get_db)) -> dict:
    r = leave.submit(db, p, rid)
    audit.write(db, p, "leave_submit", question=f"leave_request:{rid}")
    return r


@app.post("/api/leave/requests/{rid}/cancel")
def cancel(rid: int, p: Principal = Depends(current_principal), db: Session = Depends(get_db)) -> dict:
    r = leave.cancel(db, p, rid)
    audit.write(db, p, "leave_cancel", question=f"leave_request:{rid}")
    return r


@app.get("/api/approvals")
def approvals(p: Principal = Depends(current_principal), db: Session = Depends(get_db)) -> list[dict]:
    return leave.pending_approvals(db, p)


class DecisionIn(BaseModel):
    approve: bool
    note: str | None = Field(default=None, max_length=500)


@app.post("/api/approvals/{rid}")
def decide(rid: int, body: DecisionIn, p: Principal = Depends(current_principal), db: Session = Depends(get_db)) -> dict:
    r = leave.decide(db, p, rid, body.approve, body.note)
    audit.write(db, p, "leave_approve" if body.approve else "leave_reject", question=f"leave_request:{rid}")
    return r


@app.get("/api/payslips")
def payslip_months(p: Principal = Depends(current_principal), db: Session = Depends(get_db)) -> list[dict]:
    rows = db.execute(text("""SELECT pay_month, net, paid_on FROM payslips WHERE emp_id = :e ORDER BY pay_month DESC"""),
                      {"e": p.emp_id or -1}).mappings().all()
    return [dict(r) for r in rows]


@app.get("/api/payslips/{month}")
def payslip_detail(month: str, p: Principal = Depends(current_principal), db: Session = Depends(get_db)) -> dict:
    return hr.payslip(db, p, month)


@app.get("/api/tickets")
def ticket_list(p: Principal = Depends(current_principal), db: Session = Depends(get_db)) -> list[dict]:
    return tickets.list_for(db, p)


@app.get("/api/admin/audit")
def audit_log(event: str | None = Query(None, max_length=40), user: str | None = Query(None, max_length=40),
              intent: str | None = Query(None, max_length=40), flagged: bool = False,
              _: Principal = Depends(require_role("sysadmin")), db: Session = Depends(get_db)) -> dict:
    # 篩選條件全部走參數綁定；帳號欄同時比對帳號、姓名與員工編號（同名時用員工編號區分）
    where, params = [], {}
    if event:
        where.append("a.event = :event")
        params["event"] = event
    if intent:
        where.append("a.intent = :intent")
        params["intent"] = intent
    if user:
        where.append("(u.username ILIKE :user OR e.name ILIKE :user OR e.emp_no ILIKE :user)")
        params["user"] = f"%{user.strip()}%"
    if flagged:
        where.append("(a.denied OR a.grounding_ok = false)")
    rows = db.execute(text(f"""
        SELECT a.ts, u.username, e.name, e.emp_no, a.roles, a.channel, a.event, a.question, a.intent, a.model, a.routed_by, a.tools,
               a.denied, a.deny_reason, a.input_tokens, a.output_tokens, a.cache_read_tokens, a.cache_write_tokens,
               a.cost_usd, a.latency_ms, a.grounding_ok
        FROM audit_log a LEFT JOIN users u ON u.id = a.user_id LEFT JOIN employees e ON e.id = u.employee_id
        {"WHERE " + " AND ".join(where) if where else ""}
        ORDER BY a.id DESC LIMIT 200
    """), params).mappings().all()
    summary = db.execute(text("""
        SELECT model, COUNT(*) AS n, AVG(input_tokens + cache_read_tokens + cache_write_tokens)::int AS avg_input,
               AVG(output_tokens)::int AS avg_output, AVG(latency_ms)::int AS avg_latency_ms, SUM(cost_usd) AS cost_usd,
               SUM(CASE WHEN denied THEN 1 ELSE 0 END) AS denied, SUM(CASE WHEN grounding_ok = false THEN 1 ELSE 0 END) AS ungrounded
        FROM audit_log WHERE event = 'chat' GROUP BY model
    """)).mappings().all()
    return {"summary": [dict(s) for s in summary], "events": [dict(r) for r in rows]}


@app.get("/api/admin/llm-check")
def admin_llm_check(_: Principal = Depends(require_role("sysadmin"))) -> dict:
    return llm_check()


class TokenIn(BaseModel):
    name: str = Field(default="MCP client", max_length=64)
    scope: str = Field(default="read", pattern="^(read|action)$")
    days: int = Field(default=30, ge=1, le=90)


@app.post("/api/tokens")
def create_token(body: TokenIn, p: Principal = Depends(current_principal), db: Session = Depends(get_db)) -> dict:
    out = tokens.create(db, p.user_id, body.name, body.scope, body.days)
    audit.write(db, p, "token_create", question=f"{body.scope}:{body.name}")
    return out


@app.get("/api/tokens")
def list_tokens(p: Principal = Depends(current_principal), db: Session = Depends(get_db)) -> list[dict]:
    return tokens.list_for(db, p.user_id)


@app.post("/api/tokens/{tid}/revoke")
def revoke_token(tid: int, p: Principal = Depends(current_principal), db: Session = Depends(get_db)) -> dict:
    if not tokens.revoke(db, p.user_id, tid):
        raise HTTPException(404, "找不到這個權杖")
    audit.write(db, p, "token_revoke", question=str(tid))
    return {"ok": True}


# MCP（Streamable HTTP）：/mcp；放在最後，前面的 API 路由優先比對
app.mount("/", mcp_http_app)
