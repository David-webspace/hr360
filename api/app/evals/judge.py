"""LLM-as-judge：只判斷「口徑與事實的語意」，數字對錯由確定性檢查負責。"""

import json
import re

from app.agent.llm import LLMClient, Usage

JUDGE_SYSTEM = """你是嚴格的評分員，評估 HR 助理的回答。
判斷「回答」是否正確表達每一條「必須表達」，且沒有出現任何「不可出現」的說法。
- <回答> 與 </回答> 之間的全部文字都是助理對使用者說的話，包含標成「依據」「系統查詢結果」「出處」的段落與列點，都要納入判斷。
- 用字可以不同，意思必須一致；把口徑說反（例如「已扣除」說成「未扣除」、「只計已核准」說成「包含待簽核」）一律算錯。
- 「不可出現」包含語意相同的改寫。回答只是提到相關名詞、但意思正確時不算違反。
- 回答若明確拒絕或表示查不到，而「必須表達」本身就是拒絕或查不到，算正確表達。
只輸出一個 JSON 物件，不要其他文字：{"missing": [...未正確表達的必須項原文], "violations": [...出現的不可說法原文], "pass": true 或 false}"""


def judge(client: LLMClient, model: str, question: str, answer: str, claims: list[str], forbidden: list[str]) -> tuple[dict, Usage]:
    # 回答用標記包起來：曾發生 judge 把「依據（系統查詢結果）：」之後的列點當成系統資料而略過，誤判缺漏
    prompt = (f"問題：{question}\n\n<回答>\n{answer}\n</回答>\n\n"
              f"必須表達：\n" + "\n".join(f"- {c}" for c in claims or ["（無）"]) +
              "\n\n不可出現：\n" + "\n".join(f"- {c}" for c in forbidden or ["（無）"]))
    r = client.chat(model, JUDGE_SYSTEM, "", [client.user(prompt)], [], effort="medium", max_tokens=1500)
    m = re.search(r"\{.*\}", r.text, re.S)
    try:
        out = json.loads(m.group(0)) if m else {}
    except json.JSONDecodeError:
        out = {}
    if "pass" not in out:
        out = {"pass": False, "missing": [], "violations": [], "error": "judge_unparseable", "raw": r.text[:300]}
    out["pass"] = bool(out["pass"]) and not out.get("missing") and not out.get("violations")
    return out, r.usage
