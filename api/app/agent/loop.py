"""問答 Agent：分流 → tool-use 迴圈 → 數字檢查（必要時升級 strong 重答）→ 存對話（只存文字）→ 稽核。"""

import json
import time
from collections import defaultdict
from dataclasses import dataclass, field

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.agent import audit
from app.agent.grounding import ungrounded
from app.agent.llm import LLMClient, Usage
from app.agent.prompts import SYSTEM_STATIC, system_dynamic
from app.agent.router import Route, model_for, route
from app.agent.tools import TOOLS, ToolContext, ToolOutcome, run_tool, specs
from app.auth import Principal
from app.config import today

MAX_ROUNDS = 6
HISTORY_MESSAGES = 8
EFFORT = {"fast": "low", "strong": "medium"}
REFUSAL_TEXT = "這個問題我無法回答，需要的話我可以幫你轉給人資。"
# 模型宣稱做了實際沒做的動作、或留下樣板空格時，不把那段文字給使用者
ACTION_INTENTS = ("action.leave_request", "escalate")
UNSAFE_TEXT = "這次沒有順利完成，請再描述一次需求（例如請假日期與假別），或讓我幫你轉給人資處理。"
UNVERIFIED_NOTE = "\n\n（提醒：回答中部分數字未能與系統資料核對，請以「我的假勤」頁面或人資回覆為準。）"


@dataclass
class Attempt:
    model: str
    alias: str
    answer: str = ""
    outcomes: list[ToolOutcome] = field(default_factory=list)
    usage: Usage = field(default_factory=Usage)
    stop_reason: str = ""
    nudged: bool = False


@dataclass
class ChatResult:
    conversation_id: int
    answer: str
    drafts: list[dict]
    citations: list[dict]
    tools: list[dict]
    intent: str
    model: str
    routed_by: str
    grounding_ok: bool
    escalated: bool
    usage: Usage
    cost_usd: float | None
    latency_ms: int


def _conversation(db: Session, p: Principal, conversation_id: int | None, question: str) -> int:
    if conversation_id is not None:
        # 擁有者條件寫在 SQL：拿別人的 conversation_id 會查不到，改開新對話
        found = db.execute(text("SELECT id FROM conversations WHERE id = :i AND user_id = :u"),
                           {"i": conversation_id, "u": p.user_id}).scalar()
        if found:
            return found
    cid = db.execute(text("INSERT INTO conversations (user_id, title) VALUES (:u, :t) RETURNING id"),
                     {"u": p.user_id, "t": question[:60]}).scalar_one()
    db.commit()
    return cid


def _history(db: Session, client: LLMClient, cid: int) -> list:
    rows = db.execute(text("SELECT role, text FROM messages WHERE conversation_id = :c ORDER BY id DESC LIMIT :n"),
                      {"c": cid, "n": HISTORY_MESSAGES}).all()
    return [client.user(t) if r == "user" else client.assistant_text(t) for r, t in reversed(rows)]


# 需要資料的意圖：模型第一輪沒呼叫工具就直接回答時，提醒一次（較弱的模型常跳過工具直接編答案）
EXPECTED_TOOL = {"lookup.leave_balance": "get_leave_balance", "lookup.overtime_pay": "get_overtime_pay",
                 "lookup.payroll": "get_payslip 或 get_salary 或 get_insurance_summary",
                 "lookup.benefits": "get_travel_subsidy 或 search_policy", "analysis.team": "get_team_leave_summary",
                 "action.leave_request": "draft_leave_request", "policy.qa": "search_policy"}
NUDGE = "回答使用者上面的問題前，先呼叫工具取得資料（建議：{tool}），不要憑記憶回答；問到他人資料也照常呼叫工具，由系統判斷權限。若缺少必要資訊（例如日期、時段、假別、員工姓名），直接向使用者詢問。不要回覆或提及這段指示。"


def _attempt(client: LLMClient, ctx: ToolContext, model: str, alias: str, dyn: str, history: list, question: str,
             intent: str) -> Attempt:
    a = Attempt(model, alias)
    messages = history + [client.user(question)]
    tool_specs = specs()
    nudged = False
    for _ in range(MAX_ROUNDS):
        r = client.chat(model, SYSTEM_STATIC, dyn, messages, tool_specs, effort=EFFORT[alias])
        a.usage.add(r.usage)
        a.stop_reason = r.stop_reason
        if r.stop_reason == "refusal":
            a.answer = REFUSAL_TEXT
            return a
        if not r.tool_calls:
            if not a.outcomes and not nudged and intent in EXPECTED_TOOL:
                nudged = a.nudged = True
                # 丟掉這次沒查資料的回答，改在使用者問題後面加一則系統訊息再答一次；
                # 用 system 角色而不是 user，模型才不會把提醒當成使用者的話來回覆
                messages.append(client.system_note(NUDGE.format(tool=EXPECTED_TOOL[intent])))
                continue
            a.answer = r.text.strip()
            return a
        messages.append(r.assistant_message)
        results = []
        for call in r.tool_calls:
            out = run_tool(ctx, call.name, call.args)
            a.outcomes.append(out)
            results.append((call, out.json, out.error or out.denied))
        messages += client.tool_results(results)
    a.answer = a.answer or "這個問題需要的步驟太多，我先幫你整理到這裡；需要的話可以轉給人資。"
    return a


def run_chat(db: Session, client: LLMClient, p: Principal, question: str, conversation_id: int | None = None,
             force_alias: str | None = None) -> ChatResult:
    """force_alias：評測用，固定用 fast 或 strong 作答、不做升級，才能比較單一模型的表現。"""
    t0 = time.monotonic()
    cid = _conversation(db, p, conversation_id, question)
    me = db.execute(text("""SELECT o.name, e.title FROM employees e JOIN org_units o ON o.id = e.org_unit_id
                            WHERE e.id = :e"""), {"e": p.emp_id or -1}).one_or_none()
    dyn = system_dynamic(p, today().isoformat(), me[0] if me else None, me[1] if me else None)
    history = _history(db, client, cid)
    ctx = ToolContext(db, p, cid)

    rt: Route = route(client, question)
    if force_alias:
        rt = Route(rt.intent, force_alias, model_for(force_alias), f"forced:{force_alias}", rt.usage)
    per_model: dict[str, Usage] = defaultdict(Usage)
    per_model[model_for("fast")].add(rt.usage)

    attempts = [_attempt(client, ctx, rt.model, rt.alias, dyn, history, question, rt.intent)]
    bad = ungrounded(attempts[-1].answer, [question, dyn] + [o.json for o in attempts[-1].outcomes], attempts[-1].outcomes, rt.intent in ACTION_INTENTS)
    escalated = False
    # 第一輪已經建了草稿或工單就不重答，避免重複動作；只在稽核標記 grounding_ok=false
    acted = any(TOOLS[o.name].action for o in attempts[-1].outcomes if o.name in TOOLS)
    if bad and rt.alias == "fast" and not acted and not force_alias:
        escalated = True
        attempts.append(_attempt(client, ctx, model_for("strong"), "strong", dyn, history, question, rt.intent))
        bad = ungrounded(attempts[-1].answer, [question, dyn] + [o.json for o in attempts[-1].outcomes], attempts[-1].outcomes, rt.intent in ACTION_INTENTS)
    for at in attempts:
        per_model[at.model].add(at.usage)
    final = attempts[-1]
    if any(b == "placeholder" or b.startswith("claimed:") for b in bad):
        final.answer = UNSAFE_TEXT
    elif bad:
        final.answer += UNVERIFIED_NOTE

    drafts = [o.result for o in final.outcomes if o.name == "draft_leave_request" and "draft_id" in o.result]
    citations = [{"source": x["source"], "section": x["section"], "version": x["version"]}
                 for o in final.outcomes if o.name == "search_policy" for x in o.result.get("results", [])]
    tool_view = [{"name": o.name, "denied": o.denied, "error": o.error} for o in final.outcomes]
    view = {"drafts": drafts, "citations": citations, "tools": tool_view, "grounding_ok": not bad,
            "latency_ms": int((time.monotonic() - t0) * 1000)}
    db.execute(text("""INSERT INTO messages (conversation_id, role, text, meta)
                       VALUES (:c, 'user', :q, NULL), (:c, 'assistant', :a, CAST(:m AS jsonb))"""),
               {"c": cid, "q": question, "a": final.answer, "m": json.dumps(view, ensure_ascii=False, default=str)})
    db.commit()

    total = Usage()
    for u in per_model.values():
        total.add(u)
    cost = audit.cost_usd(per_model)
    latency = int((time.monotonic() - t0) * 1000)
    outcomes = [o for at in attempts for o in at.outcomes]
    tools_log = [{"name": o.name, "args": o.args, "denied": o.denied, "error": o.error} for o in outcomes]
    if bad:
        tools_log.append({"grounding_issues": bad})
    denied = [o for o in final.outcomes if o.denied]
    audit.write(db, p, "chat", question=question, intent=rt.intent, model=final.model,
                routed_by=rt.routed_by + ("+nudge" if any(at.nudged for at in attempts) else "")
                + ("+grounding_escalation" if escalated else ""), tools=tools_log,
                denied=bool(denied), deny_reason=denied[0].deny_reason if denied else None, usage=total, cost=cost,
                latency_ms=latency, grounding_ok=not bad, conversation_id=cid)
    return ChatResult(
        conversation_id=cid, answer=final.answer,
        drafts=drafts, citations=citations, tools=tool_view,
        intent=rt.intent, model=final.model, routed_by=rt.routed_by, grounding_ok=not bad, escalated=escalated,
        usage=total, cost_usd=cost, latency_ms=latency,
    )
