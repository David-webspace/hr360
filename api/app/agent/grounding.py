"""執行期數字檢查：回答裡出現的數字，必須能在本輪工具結果或使用者問題中找到。

抓的是「模型自己算出來或編出來的數字」（例如把 13 小時換成 1.6 天、把金額四捨五入成 2.2 萬）。
口徑是否說反由 eval 的 LLM-as-judge 檢查，這裡只做零成本的確定性檢查。
"""

import re

_NUM = re.compile(r"\d[\d,]*(?:\.\d+)?")
# 條次、序號、月份日期這類小整數太常見，不列入檢查
SMALL = 31


def _norm(s: str) -> str:
    s = s.replace(",", "")
    return s.rstrip("0").rstrip(".") if "." in s else s


def numbers(text: str) -> set[str]:
    return {_norm(m) for m in _NUM.findall(text)}


PLACEHOLDER = re.compile(r"[\[【［][^\]】］]{0,20}(數值|結果|餘額|金額|日期|時數)[^\]】］]{0,20}[\]】］]")
# 只認「已經做了」的正面說法；「沒辦法幫你建立草稿」「我會建立草稿」都不算宣稱
CLAIMS = {"draft_leave_request": re.compile(r"(?<![未沒])已(經)?(為您|幫你|替你)?(建立|建好|送出|送交).{0,6}(草稿|假單)|草稿已(經)?(建立|送出)"),
          "create_hr_ticket": re.compile(r"(?<![未沒])已(經)?(為您|幫你)?(開立|建立).{0,4}工單|(?<![未沒])已(經)?轉(給|交)人資")}


def ungrounded(answer: str, sources: list[str], outcomes: list | None = None, check_claims: bool = False) -> list[str]:
    """回傳有問題的片段；空 list 代表通過。

    check_claims：只在「辦事」類意圖檢查「宣稱做了某動作，但工具其實沒成功執行」；
    查詢類回答提到先前已建立的草稿是正常的，不檢查以免誤擋。
    """
    problems: list[str] = []
    if PLACEHOLDER.search(answer):
        problems.append("placeholder")
    done = {o.name for o in outcomes or [] if not (o.error or o.denied)}
    if check_claims:
        problems += [f"claimed:{tool}" for tool, pat in CLAIMS.items() if pat.search(answer) and tool not in done]
    allowed: set[str] = set()
    for s in sources:
        allowed |= numbers(s)
    out = []
    for n in numbers(answer):
        if n in allowed:
            continue
        try:
            if float(n) <= SMALL and float(n).is_integer():
                continue
        except ValueError:
            continue
        out.append(n)
    return problems + sorted(out)
