"""python -m app.agent.check：接上新的模型端點後先跑這個，確認連線、工具呼叫、繁中輸出都正常。"""

import json
import time

from app.agent.llm import ToolSpec, get_client, not_configured
from app.config import settings

PROBE_TOOL = ToolSpec("get_leave_balance", "查詢特休餘額", {"type": "object", "properties": {}, "required": [],
                                                           "additionalProperties": False})


def run() -> dict:
    out: dict = {"provider": settings.llm_provider, "base_url": settings.llm_base_url or "(official)", "checks": []}
    if reason := not_configured():
        return {**out, "ok": False, "error": reason}
    client = get_client()
    for alias, model in (("fast", settings.llm_model_fast), ("strong", settings.llm_model_strong)):
        t0 = time.monotonic()
        item = {"alias": alias, "model": model}
        try:
            r = client.chat(model, "你是 HR 助理。需要資料時呼叫工具。", "", [client.user("我還剩幾天特休？")], [PROBE_TOOL],
                            effort="low", max_tokens=512)
            item["tool_call"] = bool(r.tool_calls and r.tool_calls[0].name == "get_leave_balance")
            r2 = client.chat(model, "用繁體中文一句話回答。", "", [client.user("請說明什麼是特休。")], [], effort="low",
                             max_tokens=300)
            item["zh_tw_output"] = any("一" <= ch <= "鿿" for ch in r2.text)
            item["latency_ms"] = int((time.monotonic() - t0) * 1000)
            item["ok"] = item["tool_call"] and item["zh_tw_output"]
        except Exception as e:  # 自檢工具：把錯誤類型回給管理員看，不含金鑰
            item.update(ok=False, error=type(e).__name__)
        out["checks"].append(item)
    out["ok"] = all(c["ok"] for c in out["checks"])
    return out


if __name__ == "__main__":
    print(json.dumps(run(), ensure_ascii=False, indent=2))
