"""回答後的「接著問」建議：依本輪用到的工具與意圖用規則產生，不呼叫模型。

不交給模型產生：模型不知道登入者的權限，會建議出點了也被拒絕的問題（例如員工查別人薪水）。
每個建議都要是工具或規章檢索答得出來的問題。
"""

from app.auth import Principal

TEAM = "我的團隊這一季誰請最多假？"

BY_TOOL = {
    "draft_leave_request": ["我今年還剩多少特休？", "請假忘記事前申請怎麼辦？"],
    "get_leave_balance": ["幫我請下週一的特休", "去年沒休完的特休會不見嗎？", "生日假什麼時候要休完？"],
    "get_overtime_pay": ["加班可以選補休嗎？", "每個月加班有上限嗎？"],
    "get_payslip": ["薪資單上的勞保、健保怎麼算的？", "什麼時候發薪？"],
    "get_salary": ["薪資單上的勞保、健保怎麼算的？", "什麼時候發薪？"],
    "get_insurance_summary": ["勞退自提有什麼好處？", "團體保險保障哪些項目？"],
    "get_travel_subsidy": ["員工旅遊補助怎麼申請？", "我今年還剩多少特休？"],
    "get_team_leave_summary": ["我的團隊上個月誰請最多病假？", "我今年還剩多少特休？"],
}
# 模型沒呼叫工具（例如反問澄清）時，依意圖給同一組建議
BY_INTENT = {
    "lookup.leave_balance": BY_TOOL["get_leave_balance"],
    "lookup.overtime_pay": BY_TOOL["get_overtime_pay"],
    "lookup.payroll": BY_TOOL["get_payslip"],
    "lookup.benefits": ["員工旅遊補助還剩多少？", "團體保險保障哪些項目？"],
    "analysis.team": BY_TOOL["get_team_leave_summary"],
    "action.leave_request": ["我今年還剩多少特休？", "請假忘記事前申請怎麼辦？"],
    "policy.qa": ["我今年還剩多少特休？", "我上個月加班費怎麼算？"],
}
# 被拒絕時改建議本人查得到的版本；薪資以外的拒絕多半是查別人的假勤
ON_DENIED = {
    "get_salary": ["我上個月的薪資單", "薪資單上的勞保、健保怎麼算的？"],
    "get_payslip": ["我上個月的薪資單", "薪資單上的勞保、健保怎麼算的？"],
}
DENIED_DEFAULT = ["我今年還剩多少特休？", "我上個月加班費怎麼算？"]
# 申訴、爭議類對話不推下一題，避免像在打斷使用者
SILENT_INTENTS = {"escalate"}
SILENT_TOOLS = {"create_hr_ticket"}


def suggest(question: str, intent: str, tools: list[dict], drafts: list[dict], p: Principal, limit: int = 3) -> list[str]:
    names = [t["name"] for t in tools]
    if intent in SILENT_INTENTS or SILENT_TOOLS & set(names):
        return []
    denied = [t["name"] for t in tools if t["denied"]]
    if denied:
        pool = ON_DENIED.get(denied[0], DENIED_DEFAULT)
    elif drafts:
        pool = BY_TOOL["draft_leave_request"]
    else:
        pool = [s for n in names for s in BY_TOOL.get(n, [])] or BY_INTENT.get(intent, [])
        # 團隊查詢只建議給主管與 HRBP；員工點了只會被拒絕
        if ("get_leave_balance" in names or intent == "lookup.leave_balance") and (p.managed_paths or p.hrbp_paths):
            pool = pool[:1] + [TEAM] + pool[1:]
    asked = question.strip().rstrip("？?")
    out: list[str] = []
    for s in pool:
        if s not in out and s.rstrip("？?") != asked:
            out.append(s)
    return out[:limit]
