"""意圖分流：先用規則（零成本），規則判斷不了再用 fast 模型分類；意圖 → 模型別名查 router_table.yaml。"""

import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import yaml

from app.agent.llm import LLMClient, Usage
from app.agent.prompts import ROUTER_PROMPT
from app.config import settings

INTENTS = ("lookup.leave_balance", "lookup.overtime_pay", "lookup.payroll", "lookup.benefits", "analysis.team",
           "action.leave_request", "report.export", "policy.qa", "escalate", "audit.stats", "other")

RULES = [
    ("escalate", r"申訴|性騷擾|騷擾|算錯|不合理|要找人資|轉人工"),
    ("report.export", r"(?i)匯出|下載|excel|xlsx|csv|整理成.{0,4}(表|檔)"),
    ("analysis.team", r"團隊|部屬|組員|我們(課|部|組)|下屬|誰請(最多|最久)|出勤狀況"),
    ("action.leave_request", r"幫我請|我要請|我想請|請.{0,6}(明天|後天|下週|下周|\d+\s*[/月])|取消.{0,4}假"),
    ("lookup.overtime_pay", r"加班費"),
    ("lookup.payroll", r"薪水|薪資|月薪|底薪|薪資單|勞保|健保|勞退|自提|保費|扣了多少"),
    ("lookup.benefits", r"旅遊補助|禮金|補助還剩|補助額度"),
    ("lookup.leave_balance", r"(特休|補休|生日假|病假|事假).{0,6}(還?剩|幾天|幾小時|餘額|用了)|還有幾天|還剩幾"),
    ("policy.qa", r"規定|辦法|怎麼申請|要準備|流程|可以.{0,10}嗎|多久|上限|是什麼"),
]


@dataclass
class Route:
    intent: str
    alias: str
    model: str
    routed_by: str
    usage: Usage


@lru_cache(maxsize=1)
def table() -> dict:
    return yaml.safe_load(Path(settings.llm_router_file).read_text())


def model_for(alias: str) -> str:
    return settings.llm_model_fast if alias == "fast" else settings.llm_model_strong


def classify_by_rule(question: str) -> str | None:
    return next((intent for intent, pat in RULES if re.search(pat, question)), None)


def fixed(intent: str, by: str) -> Route:
    alias = table()["routes"].get(intent, "strong")
    return Route(intent, alias, model_for(alias), by, Usage())


def route(client: LLMClient, question: str) -> Route:
    usage = Usage()
    intent, by = classify_by_rule(question), "rule"
    if intent is None:
        r = client.chat(settings.llm_model_fast, ROUTER_PROMPT, "", [client.user(question)], [], effort="low", max_tokens=200)
        usage.add(r.usage)
        label = r.text.strip().split()[0] if r.text.strip() else ""
        intent, by = (label, "llm") if label in INTENTS else ("other", "default")
    alias = table()["routes"].get(intent, "strong")
    return Route(intent, alias, model_for(alias), by, usage)
