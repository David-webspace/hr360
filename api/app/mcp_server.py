"""MCP server（Streamable HTTP，掛在 /mcp）：接入方自己的 Agent 平台直接呼叫 hr360 的工具。

模型完全是接入方的；權限、計算、稽核仍在 hr360 這一側——每次呼叫都從 Authorization 標頭
解析出 Principal，再走和網頁聊天同一套 Tool Registry 與 Policy Layer。
"""

import json
from typing import Annotated, Any

from mcp.server.mcpserver import Context, MCPServer
from mcp.server.transport_security import TransportSecuritySettings
from pydantic import Field
from sqlalchemy.orm import Session
from starlette.types import ASGIApp, Receive, Scope, Send

from app import tokens
from app.agent import audit
from app.agent.tools import TOOLS, ToolContext, run_tool
from app.auth import load_principal
from app.db import SessionLocal
from app.policy import DENIED, PolicyDenied
from app.services import leave

INSTRUCTIONS = """曜川科技 HR 工具。所有數字由系統依勞基法與公司規定計算，請直接引用工具結果，不要自行換算。
身分由權杖決定：employee 參數省略代表本人；查他人資料時由系統判斷權限，回傳「無權限或查無此人」就照實告知。
請假流程：draft_leave_request 只建立草稿；確認使用者同意後才呼叫 submit_leave_request。"""

mcp = MCPServer("hr360", instructions=INSTRUCTIONS)

Emp = Annotated[str | None, Field(description="員工姓名或員工編號；查詢本人時省略")]
Month = Annotated[str, Field(description="月份 YYYY-MM", pattern=r"^\d{4}-\d{2}$")]


def _bearer(headers: Any) -> str:
    value = (headers or {}).get("authorization", "")
    return value[7:].strip() if value.lower().startswith("bearer ") else ""


def _call(ctx: Context, name: str, args: dict, action: bool = False) -> dict:
    with SessionLocal() as db:
        resolved = tokens.resolve(db, _bearer(ctx.headers))
        if resolved is None:
            return {"error": "權杖無效或已過期"}
        uid, scope = resolved
        p = load_principal(db, uid, channel="mcp")
        if action and scope != "action":
            audit.write(db, p, "mcp_tool", channel="mcp", question=name, denied=True, deny_reason="read_only_token")
            return {"error": "這個權杖是唯讀（read），不能建立或送出假單、開立工單"}
        args = {k: v for k, v in args.items() if v is not None}
        out = run_tool(ToolContext(db, p), name, args)
        audit.write(db, p, "mcp_tool", channel="mcp", question=f"{name} {json.dumps(args, ensure_ascii=False)}",
                    tools=[{"name": name, "denied": out.denied, "error": out.error}], denied=out.denied,
                    deny_reason=out.deny_reason)
        return out.result


def _doc(name: str) -> str:
    return TOOLS[name].spec.description


@mcp.tool(description=_doc("find_employee"))
def find_employee(ctx: Context, query: str) -> dict:
    return _call(ctx, "find_employee", {"query": query})


@mcp.tool(description=_doc("get_leave_balance"))
def get_leave_balance(ctx: Context, employee: Emp = None) -> dict:
    return _call(ctx, "get_leave_balance", {"employee": employee})


@mcp.tool(description=_doc("get_overtime_pay"))
def get_overtime_pay(ctx: Context, month: Month, employee: Emp = None) -> dict:
    return _call(ctx, "get_overtime_pay", {"month": month, "employee": employee})


@mcp.tool(description=_doc("get_team_leave_summary"))
def get_team_leave_summary(ctx: Context, start_date: Annotated[str, Field(description="YYYY-MM-DD")],
                           end_date: Annotated[str, Field(description="YYYY-MM-DD")], leave_type: str | None = None) -> dict:
    return _call(ctx, "get_team_leave_summary", {"start_date": start_date, "end_date": end_date, "leave_type": leave_type})


@mcp.tool(description=_doc("get_salary"))
def get_salary(ctx: Context, employee: Emp = None) -> dict:
    return _call(ctx, "get_salary", {"employee": employee})


@mcp.tool(description=_doc("get_payslip"))
def get_payslip(ctx: Context, month: Month, employee: Emp = None) -> dict:
    return _call(ctx, "get_payslip", {"month": month, "employee": employee})


@mcp.tool(description=_doc("get_insurance_summary"))
def get_insurance_summary(ctx: Context, employee: Emp = None) -> dict:
    return _call(ctx, "get_insurance_summary", {"employee": employee})


@mcp.tool(description=_doc("get_travel_subsidy"))
def get_travel_subsidy(ctx: Context, year: int | None = None) -> dict:
    return _call(ctx, "get_travel_subsidy", {"year": year})


@mcp.tool(description=_doc("search_policy"))
def search_policy(ctx: Context, query: str) -> dict:
    return _call(ctx, "search_policy", {"query": query})


@mcp.tool(description=_doc("draft_leave_request") + "（需要 action 權杖）")
def draft_leave_request(ctx: Context, leave_type: Annotated[str, Field(json_schema_extra={"enum": list(leave.SELF_SERVICE)})],
                        start: str, end: str, reason: str | None = None) -> dict:
    return _call(ctx, "draft_leave_request", {"leave_type": leave_type, "start": start, "end": end, "reason": reason}, action=True)


@mcp.tool(description=_doc("create_hr_ticket") + "（需要 action 權杖）")
def create_hr_ticket(ctx: Context, category: str, summary: str) -> dict:
    return _call(ctx, "create_hr_ticket", {"category": category, "summary": summary}, action=True)


@mcp.tool(description="送出本人的請假草稿進入主管簽核。只能在使用者明確確認草稿內容後呼叫（需要 action 權杖）。")
def submit_leave_request(ctx: Context, draft_id: int) -> dict:
    with SessionLocal() as db:
        resolved = tokens.resolve(db, _bearer(ctx.headers))
        if resolved is None:
            return {"error": "權杖無效或已過期"}
        uid, scope = resolved
        p = load_principal(db, uid, channel="mcp")
        if scope != "action":
            return {"error": "這個權杖是唯讀（read），不能送出假單"}
        try:
            out = leave.submit(db, p, draft_id)
        except PolicyDenied:
            return {"error": DENIED}
        except leave.LeaveError as e:
            return {"error": str(e)}
        audit.write(db, p, "leave_submit", channel="mcp", question=f"leave_request:{draft_id}")
        return out


class BearerGate:
    """沒有有效權杖的請求在 HTTP 層就擋掉，連工具清單都看不到。"""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http" and scope["path"].startswith("/mcp"):
            headers = {k.decode().lower(): v.decode() for k, v in scope["headers"]}
            with SessionLocal() as db:
                ok = _valid(db, _bearer(headers))
            if not ok:
                body = json.dumps({"error": "需要有效的 hr360 個人存取權杖（Authorization: Bearer hr360_…）"}, ensure_ascii=False).encode()
                await send({"type": "http.response.start", "status": 401,
                            "headers": [(b"content-type", b"application/json"), (b"www-authenticate", b"Bearer")]})
                await send({"type": "http.response.body", "body": body})
                return
        await self.app(scope, receive, send)


def _valid(db: Session, token: str) -> bool:
    return tokens.resolve(db, token) is not None


# 權杖驗證已取代 DNS rebinding 防護的用途：瀏覽器不會自動帶 Authorization 標頭，惡意網頁拿不到權杖
http_app = BearerGate(mcp.streamable_http_app(
    streamable_http_path="/mcp", stateless_http=True, json_response=True,
    transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False),
))
