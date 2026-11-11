"""執行期數字檢查：回答裡出現的數字，必須能在本輪工具結果或使用者問題中找到。

抓的是「模型自己算出來或編出來的數字」（例如把 13 小時換成 1.6 天、把金額四捨五入成 2.2 萬）。
口徑是否說反由 eval 的 LLM-as-judge 檢查，這裡只做零成本的確定性檢查。
"""

import re
from collections.abc import Collection

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
          # 小模型實測會沒呼叫工具就說「檔案已在下方準備下載連結，請點擊即可取得」，所以連「叫人去下載」也算宣稱
          "export_report": re.compile(r"(?<![未沒])已(經)?(為您|幫你)?(匯出|產生|整理好|準備好)|檔案已|下方.{0,10}下載|點(擊|選)?.{0,6}(下載|取得)"),
          "create_hr_ticket": re.compile(r"(?<![未沒])已(經)?(為您|幫你)?(開立|建立).{0,4}工單|(?<![未沒])已(經)?轉(給|交)人資")}


def ungrounded(answer: str, sources: list[str], outcomes: list | None = None, check_claims: Collection[str] = ()) -> list[str]:
    """回傳有問題的片段；空 list 代表通過。

    check_claims：要檢查「宣稱做了某動作，但工具其實沒成功執行」的工具名稱，只在「辦事」類意圖傳入；
    查詢類回答提到先前已建立的草稿是正常的，不檢查以免誤擋。各意圖只查自己的動作：
    請假回答常寫「請點擊確認送出」，若也套用匯出的規則會被誤判成宣稱已匯出。
    """
    problems: list[str] = []
    if PLACEHOLDER.search(answer):
        problems.append("placeholder")
    done = {o.name for o in outcomes or [] if not (o.error or o.denied)}
    if check_claims:
        problems += [f"claimed:{tool}" for tool in check_claims if CLAIMS[tool].search(answer) and tool not in done]
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
