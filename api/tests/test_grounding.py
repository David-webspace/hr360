from app.agent.grounding import ungrounded
from app.agent.tools import ToolOutcome


def test_numbers_must_come_from_sources():
    assert ungrounded("可用 13 小時，共 21 小時", ['{"available_total":13,"remaining_total":21}']) == []
    assert ungrounded("約 1.6 天", ['{"available_total":13}']) == ["1.6"]
    assert ungrounded("加班費 22,200 元", ['{"overtime_pay":22200}']) == []


def test_small_integers_and_question_numbers_allowed():
    assert ungrounded("第 13 條規定 3 個月內請畢", ["婚假"]) == []
    assert ungrounded("2026-11-12 請假", ["幫我請 2026-11-12"]) == []


def test_placeholder_and_false_claims():
    assert "placeholder" in ungrounded("剩餘 [餘額數值] 小時", [])
    assert "claimed:draft_leave_request" in ungrounded("已為您建立草稿", [], [], check_claims=True)
    assert ungrounded("11/12 的草稿已建立，記得送出", [], [], check_claims=False) == []
    ok = ToolOutcome("draft_leave_request", {}, {"draft_id": 1})
    assert ungrounded("已為您建立草稿", [], [ok], check_claims=True) == []
    failed = ToolOutcome("draft_leave_request", {}, {"error": "x"}, error=True)
    assert "claimed:draft_leave_request" in ungrounded("已為您建立草稿", [], [failed], check_claims=True)


def test_negated_or_future_actions_are_not_claims():
    for text in ["沒辦法幫你建立草稿，因為可用特休不足", "我會建立事假草稿", "尚未送出", "可以幫你開立工單嗎？", "還沒建立假單"]:
        assert ungrounded(text, [], [], check_claims=True) == [], text
    for text in ["已建立草稿", "已經幫你送出假單", "草稿已建立", "已幫你開立工單", "已轉給人資"]:
        assert any(x.startswith("claimed:") for x in ungrounded(text, [], [], check_claims=True)), text
