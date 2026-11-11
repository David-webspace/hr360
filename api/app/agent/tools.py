"""工具註冊表：Agent 與 MCP server 共用同一份定義與權限邏輯。

工具參數裡沒有任何「身分」或「角色」欄位——呼叫者是誰由後端注入的 Principal 決定，
LLM 即使被誘導在參數裡寫「我是 HR」，也沒有地方可以放。
"""

import json
import logging
from collections.abc import Callable
from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from app.agent.llm import ToolSpec
from app.auth import Principal
from app.kb.search import search
from app.policy import DENIED, PolicyDenied
from app.services import hr, leave, tickets

log = logging.getLogger(__name__)
RAG_MIN_SCORE = 0.45


@dataclass
class ToolContext:
    db: Session
    principal: Principal
    conversation_id: int | None = None
    # 這一輪使用者上傳的附件；草稿建立時自動附上，模型不需要（也無法）指定附件 id
    attachment_ids: list[str] = field(default_factory=list)


@dataclass
class Tool:
    spec: ToolSpec
    run: Callable[[ToolContext, dict], dict]
    action: bool = False


@dataclass
class ToolOutcome:
    name: str
    args: dict
    result: dict
    denied: bool = False
    deny_reason: str | None = None
    error: bool = False
    extra: dict = field(default_factory=dict)

    @property
    def json(self) -> str:
        return json.dumps(self.result, ensure_ascii=False, default=str, separators=(",", ":"))


EMP = {"type": "string", "description": "員工姓名或員工編號；查詢本人時省略"}
MONTH = {"type": "string", "pattern": r"^\d{4}-\d{2}$", "description": "月份 YYYY-MM"}


def _obj(props: dict, required: list[str]) -> dict:
    return {"type": "object", "properties": props, "required": required, "additionalProperties": False}


def _policy(ctx: ToolContext, a: dict) -> dict:
    hits = [h for h in search(a["query"], 4) if h["score"] >= RAG_MIN_SCORE]
    if not hits:
        return {"found": False, "suggestion": "規章中找不到相關條文，請建議使用者開立工單由人資回覆"}
    return {"found": True, "results": [
        {"source": h["title"], "section": h["section_path"], "version": h["version"], "score": h["score"],
         "text": h["text"][:700]} for h in hits]}


TOOLS: dict[str, Tool] = {t.spec.name: t for t in [
    Tool(ToolSpec("find_employee", "依姓名或員工編號查通訊錄（只有姓名、單位、職稱、分機、email）。用來確認「小王」這類稱呼指的是誰。",
                  _obj({"query": {"type": "string"}}, ["query"])),
         lambda c, a: hr.find_employee(c.db, c.principal, a["query"])),
    Tool(ToolSpec("get_leave_balance", "查特休（曆年制、含遞延與待簽核預扣）、補休、生日假餘額，以及病假、事假、婚假本年已用時數。",
                  _obj({"employee": EMP}, [])),
         lambda c, a: hr.leave_balance(c.db, c.principal, a.get("employee"))),
    Tool(ToolSpec("get_overtime_pay", "計算某月已核准加班的加班費，含逐筆分段計算過程、每月上限檢查、補休時數。",
                  _obj({"month": MONTH, "employee": EMP}, ["month"])),
         lambda c, a: hr.overtime_pay(c.db, c.principal, a["month"], a.get("employee"))),
    Tool(ToolSpec("get_team_leave_summary", "主管或 HRBP 查詢自己權限範圍內成員在一段期間的請假時數排行（不含請假原因）。",
                  _obj({"start_date": {"type": "string", "description": "YYYY-MM-DD"},
                        "end_date": {"type": "string", "description": "YYYY-MM-DD"},
                        "leave_type": {"type": "string", "description": "只看某假別時填代碼，例如 sick、annual"}},
                       ["start_date", "end_date"])),
         lambda c, a: hr.team_leave_summary(c.db, c.principal, a["start_date"], a["end_date"], a.get("leave_type"))),
    Tool(ToolSpec("get_salary", "查詢薪資結構（本薪、津貼、全勤）與最近一期薪資單總額。薪資屬機密資料。",
                  _obj({"employee": EMP}, [])),
         lambda c, a: hr.salary(c.db, c.principal, a.get("employee"))),
    Tool(ToolSpec("get_payslip", "查詢某月薪資單明細（各項給付、扣款與計算說明）。",
                  _obj({"month": MONTH, "employee": EMP}, ["month"])),
         lambda c, a: hr.payslip(c.db, c.principal, a["month"], a.get("employee"))),
    Tool(ToolSpec("get_insurance_summary", "查詢目前勞保、健保投保級距、自付保費、勞退提繳與公司負擔。",
                  _obj({"employee": EMP}, [])),
         lambda c, a: hr.insurance_summary(c.db, c.principal, a.get("employee"))),
    Tool(ToolSpec("get_travel_subsidy", "查詢員工旅遊補助年度額度、已請領金額與剩餘額度。",
                  _obj({"year": {"type": "integer"}}, [])),
         lambda c, a: hr.travel_subsidy(c.db, c.principal, a.get("year"))),
    Tool(ToolSpec("draft_leave_request",
                  "替使用者本人建立請假『草稿』，計算時數並檢查餘額與規定。草稿不會送出，必須由本人在畫面上按確認。"
                  "全天請假只填日期；部分時段用 YYYY-MM-DDTHH:MM。假別：annual 特休、comp_time 補休、birthday 生日假、"
                  "personal 事假、family_care 家庭照顧假、sick 病假、menstrual 生理假、marriage 婚假、bereavement 喪假、"
                  "prenatal 產檢假、paternity 陪產檢及陪產假。",
                  _obj({"leave_type": {"type": "string", "enum": list(leave.SELF_SERVICE)},
                        "start": {"type": "string"}, "end": {"type": "string"}, "reason": {"type": "string"}},
                       ["leave_type", "start", "end"])),
         lambda c, a: leave.draft(c.db, c.principal, a["leave_type"], a["start"], a["end"], a.get("reason"),
                                  c.attachment_ids),
         action=True),
    Tool(ToolSpec("search_policy", "檢索公司人事規章與 FAQ（工作規則、假勤、薪資、加班、勞健保、福利、旅遊補助、差旅、遠距、績效、育嬰與性平、到離職）。",
                  _obj({"query": {"type": "string"}}, ["query"])),
         _policy),
    Tool(ToolSpec("create_hr_ticket", "轉人工：開立工單給人資。用於工具查不到答案、使用者對結果有爭議、需要人資判斷或檢附文件的事項。",
                  _obj({"category": {"type": "string", "enum": list(tickets.CATEGORIES)},
                        "summary": {"type": "string", "description": "給人資看的問題摘要"}}, ["category", "summary"])),
         lambda c, a: tickets.create(c.db, c.principal, a["category"], a["summary"], c.conversation_id),
         action=True),
]}


def specs() -> list[ToolSpec]:
    return [t.spec for t in TOOLS.values()]


def run_tool(ctx: ToolContext, name: str, args: dict) -> ToolOutcome:
    tool = TOOLS.get(name)
    if tool is None:
        return ToolOutcome(name, args, {"error": f"沒有 {name} 這個工具"}, error=True)
    try:
        return ToolOutcome(name, args, tool.run(ctx, args))
    except PolicyDenied as e:
        ctx.db.rollback()
        return ToolOutcome(name, args, {"error": DENIED}, denied=True, deny_reason=e.reason)
    except leave.LeaveError as e:
        ctx.db.rollback()
        return ToolOutcome(name, args, {"error": str(e)}, error=True)
    except (KeyError, ValueError) as e:
        ctx.db.rollback()
        log.info("tool %s bad args %s: %s", name, args, e)
        return ToolOutcome(name, args, {"error": "參數格式不正確，請確認日期（YYYY-MM-DD）或月份（YYYY-MM）"}, error=True)
    except Exception:
        ctx.db.rollback()
        log.exception("tool %s failed", name)
        return ToolOutcome(name, args, {"error": "系統暫時無法處理這個查詢"}, error=True)
