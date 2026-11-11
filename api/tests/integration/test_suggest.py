"""回答後的「接著問」建議：依工具與角色用規則產生。"""

from app.agent.suggest import TEAM, suggest


def t(name, denied=False):
    return {"name": name, "denied": denied, "error": False}


def test_leave_balance_suggests_next_steps_and_team_only_for_managers(as_user):
    emp = suggest("我今年還剩多少特休？", "lookup.leave_balance", [t("get_leave_balance")], [], as_user("grace.lin"))
    boss = suggest("我今年還剩多少特休？", "lookup.leave_balance", [t("get_leave_balance")], [], as_user("kevin.chen"))
    hrbp = suggest("我今年還剩多少特休？", "lookup.leave_balance", [t("get_leave_balance")], [], as_user("vivian.wu"))
    assert emp[0] == "幫我請下週一的特休" and TEAM not in emp and len(emp) == 3
    assert TEAM in boss and TEAM in hrbp


def test_draft_denied_silent_and_fallback_cases(as_user):
    p = as_user("grace.lin")
    assert suggest("幫我請明天的特休", "action.leave_request", [t("draft_leave_request")], [{"draft_id": 1}], p)[0] == "我今年還剩多少特休？"
    assert suggest("陳冠宇特休剩多少", "lookup.leave_balance", [t("get_leave_balance", denied=True)], [], p) == \
        ["我今年還剩多少特休？", "我上個月加班費怎麼算？"]
    assert suggest("我要申訴", "escalate", [t("create_hr_ticket")], [], p) == []
    assert suggest("你好", "other", [], [], p) == []
    # 模型沒呼叫工具（反問澄清）時仍依意圖給建議
    assert suggest("十月加班費多少", "lookup.overtime_pay", [], [], p) == ["加班可以選補休嗎？", "每個月加班有上限嗎？"]


def test_policy_fallback_skips_the_question_just_asked(as_user):
    p = as_user("grace.lin")
    assert suggest("我今年還剩多少特休", "policy.qa", [t("search_policy")], [], p) == ["我上個月加班費怎麼算？"]
