"""評測：python -m app.evals.run [--models fast,strong] [--cases L1,S1] [--write-router]

每題在獨立的資料庫交易中執行、結束後回滾，評測建立的草稿與稽核不會留在資料庫。
結果寫入 eval/results/、eval/REPORT.md，並記錄到 eval_runs 表。
"""

import argparse
import json
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path

import yaml
from sqlalchemy import insert, text
from sqlalchemy.orm import Session

from app.agent.llm import Usage, get_client
from app.agent.loop import run_chat
from app.services import attachments
from app.agent.router import model_for
from app.agent import audit
from app.auth import load_principal
from app.config import TZ, settings
from app.db import engine
from app.evals.checks import evaluate
from app.evals.judge import judge
from app.models import EvalRun

ROOT = Path(__file__).resolve().parents[2] / "eval"
MIN_CASES = 3
CHECK_KEYS = ("tool_ok", "numeric_ok", "refuse_ok", "draft_ok", "no_draft_ok", "export_ok", "no_export_ok", "citation_ok", "semantic_ok")


def load_cases(only: set[str] | None = None) -> list[dict]:
    cases = yaml.safe_load((ROOT / "cases.yaml").read_text())["cases"]
    return [c for c in cases if not only or c["id"] in only]


def run_case(case: dict, alias: str, judge_model: str) -> dict:
    client = get_client()
    conn = engine.connect()
    outer = conn.begin()
    db = Session(bind=conn, join_transaction_mode="create_savepoint")
    try:
        uid = db.execute(text("SELECT id FROM users WHERE username = :u"), {"u": case["user"]}).scalar_one()
        t0 = time.monotonic()
        p = load_principal(db, uid)
        # 附件題：把合成的證明文件圖片走正式的上傳流程（驗證、重新編碼）存進交易，結束時一起回滾
        ids = [attachments.save(db, p, (ROOT / "fixtures" / f).read_bytes(), f)["id"] for f in case.get("attachments", [])]
        r = run_chat(db, client, p, case["question"], force_alias=alias, attachment_ids=ids)
        latency = int((time.monotonic() - t0) * 1000)
    finally:
        db.close()
        outer.rollback()
        conn.close()
    result = evaluate(case, r)
    e = case.get("expect", {})
    judge_usage = Usage()
    if e.get("claims") or e.get("forbidden_claims"):
        verdict, judge_usage = judge(client, judge_model, case["question"], r.answer, e.get("claims", []), e.get("forbidden_claims", []))
        result["semantic_ok"] = verdict["pass"]
        result["judge"] = verdict
    passed = all(result[k] for k in CHECK_KEYS if k in result) and not result["leaked"]
    return {
        "case": case["id"], "intent": case["intent"], "alias": alias, "model": r.model, "passed": passed, **result,
        "answer": r.answer, "tools": r.tools, "routed_intent": r.intent, "grounding_ok": r.grounding_ok,
        "latency_ms": latency, "cost_usd": r.cost_usd, "tokens": vars(r.usage),
        "judge_cost_usd": audit.cost_usd({judge_model: judge_usage}),
    }


def summarize(rows: list[dict]) -> dict:
    by: dict = defaultdict(lambda: defaultdict(list))
    for r in rows:
        by[r["model"]]["_all"].append(r)
        by[r["model"]][r["intent"]].append(r)
    out: dict = {}
    for model, groups in by.items():
        out[model] = {}
        for intent, rs in groups.items():
            sem = [r["semantic_ok"] for r in rs if "semantic_ok" in r]
            num = [r["numeric_ok"] for r in rs if "numeric_ok" in r]
            ref = [r for r in rs if "refuse_ok" in r]
            out[model][intent] = {
                "n": len(rs), "cases": len({r["case"] for r in rs}), "pass_rate": round(sum(r["passed"] for r in rs) / len(rs), 3),
                "numeric_acc": round(sum(num) / len(num), 3) if num else None,
                "semantic_acc": round(sum(sem) / len(sem), 3) if sem else None,
                "refusal_n": len(ref), "leak_rate": round(sum(r["leaked"] for r in ref) / len(ref), 3) if ref else None,
                "avg_latency_ms": int(sum(r["latency_ms"] for r in rs) / len(rs)),
                "avg_cost_usd": round(sum(r["cost_usd"] or 0 for r in rs) / len(rs), 6),
            }
    return out


def router_table(summary: dict, fast: str, strong: str) -> dict:
    """每個意圖選「通過率 100%、零洩漏」中最便宜的模型；都不達標就用 strong。"""
    routes, evidence = {}, {}
    intents = sorted({i for m in summary.values() for i in m if i != "_all"})
    for intent in intents:
        f = summary.get(fast, {}).get(intent)
        s = summary.get(strong, {}).get(intent)
        # 樣本少於 MIN_CASES 題的意圖證據不足，維持 strong
        ok = lambda x: x and x["cases"] >= MIN_CASES and x["pass_rate"] == 1.0 and not x["leak_rate"]  # noqa: E731
        routes[intent] = "fast" if ok(f) else "strong"
        evidence[intent] = {"fast": f and {k: f[k] for k in ("cases", "n", "pass_rate", "avg_cost_usd")},
                            "strong": s and {k: s[k] for k in ("cases", "n", "pass_rate", "avg_cost_usd")}}
    routes.setdefault("other", "strong")
    return {"routes": routes, "evidence": evidence}


def pct(x: float | None) -> str:
    return "—" if x is None else f"{x:.0%}"


def write_report(rows: list[dict], summary: dict, stamp: str) -> None:
    repeats = len(rows) // max(1, len({(r["case"], r["model"]) for r in rows}))
    lines = [f"# 評測報告（{stamp}）", "", f"評測集：eval/cases.yaml，{len({r['case'] for r in rows})} 題 × 每題 {repeats} 次；judge 模型：{settings.llm_model_strong}（校準見 CALIBRATION.md）", "",
             "## 各模型總表", "", "| 模型 | 題數 | 通過率 | 數字正確率 | 口徑正確率（judge） | 越權洩漏率 | 平均延遲 | 平均成本 USD |", "|---|---|---|---|---|---|---|---|"]
    for model, s in summary.items():
        a = s["_all"]
        lines.append(f"| {model} | {a['n']} | {pct(a['pass_rate'])} | {pct(a['numeric_acc'])} | {pct(a['semantic_acc'])} | "
                     f"{pct(a['leak_rate'])} | {a['avg_latency_ms'] / 1000:.1f}s | {a['avg_cost_usd']:.4f} |")
    lines += ["", "## 依意圖", "", "| 意圖 | " + " | ".join(summary) + " |", "|---|" + "---|" * len(summary)]
    intents = sorted({i for m in summary.values() for i in m if i != "_all"})
    for i in intents:
        lines.append(f"| {i} | " + " | ".join(
            f"{s[i]['pass_rate']:.0%}（{s[i]['n']}）" if i in s else "—" for s in summary.values()) + " |")
    lines += ["", "## 未通過的題目", ""]
    for r in rows:
        if not r["passed"]:
            why = [k for k in CHECK_KEYS if r.get(k) is False] + (["leaked"] if r["leaked"] else [])
            detail = r.get("judge", {})
            lines.append(f"- **{r['case']}**（{r['model']}）：{', '.join(why)}"
                         + (f"；judge missing={detail.get('missing')} violations={detail.get('violations')}" if detail and not detail.get("pass") else "")
                         + (f"；缺數字 {r.get('numbers_missing')}" if r.get("numbers_missing") else ""))
    (ROOT / "REPORT.md").write_text("\n".join(lines) + "\n")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--models", default="fast,strong")
    ap.add_argument("--cases", default="")
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--write-router", action="store_true")
    ap.add_argument("--repeats", type=int, default=1, help="每題重跑次數；路由要求每一次都通過")
    ap.add_argument("--merge", default="", help="與先前的 run-*.jsonl 合併：本次重跑的題目取代舊結果，其餘沿用")
    args = ap.parse_args()
    cases = load_cases(set(args.cases.split(",")) if args.cases else None)
    aliases = args.models.split(",")
    judge_model = model_for("strong")
    stamp = datetime.now(TZ).strftime("%Y%m%d-%H%M")
    jobs = [(c, a) for a in aliases for c in cases for _ in range(args.repeats)]
    with ThreadPoolExecutor(args.workers) as pool:
        rows = list(pool.map(lambda j: run_case(j[0], j[1], judge_model), jobs))
    if args.merge:
        rerun = {(r["case"], r["model"]) for r in rows}
        prev = [json.loads(line) for line in Path(args.merge).read_text().splitlines() if line.strip()]
        rows = [r for r in prev if (r["case"], r["model"]) not in rerun] + rows
    out_dir = ROOT / "results"
    out_dir.mkdir(exist_ok=True)
    (out_dir / f"run-{stamp}.jsonl").write_text("\n".join(json.dumps(r, ensure_ascii=False, default=str) for r in rows) + "\n")
    summary = summarize(rows)
    (out_dir / f"summary-{stamp}.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2))
    write_report(rows, summary, stamp)
    with engine.begin() as conn:
        conn.execute(insert(EvalRun), [{
            "run_id": stamp, "model": r["model"], "case_id": r["case"], "category": r["intent"],
            "numeric_ok": r.get("numeric_ok"), "semantic_ok": r.get("semantic_ok"), "leaked": r["leaked"],
            "refused_ok": r.get("refuse_ok"), "action_ok": r.get("draft_ok"), "input_tokens": r["tokens"]["input"],
            "output_tokens": r["tokens"]["output"], "cost_usd": r["cost_usd"], "latency_ms": r["latency_ms"],
            "detail": {"answer": r["answer"], "judge": r.get("judge"), "passed": r["passed"]},
        } for r in rows])
    if args.write_router and set(aliases) >= {"fast", "strong"}:
        rt = router_table(summary, model_for("fast"), model_for("strong"))
        body = {"version": f"eval-{stamp}", "source": f"eval/results/summary-{stamp}.json",
                "rule": "每個意圖選通過率 100%、零洩漏、且至少 3 題的最便宜模型；否則 strong", **rt}
        Path(settings.llm_router_file).write_text(
            "# 由 python -m app.evals.run --write-router 產生，請勿手改 routes 以外的欄位\n"
            + yaml.safe_dump(body, allow_unicode=True, sort_keys=False))
    for model, s in summary.items():
        a = s["_all"]
        print(f"{model}: pass {a['pass_rate']:.0%}  numeric {a['numeric_acc']}  semantic {a['semantic_acc']}  leak {a['leak_rate']}  "
              f"cost/q {a['avg_cost_usd']}  latency {a['avg_latency_ms']}ms")
    total = sum((r["cost_usd"] or 0) + (r["judge_cost_usd"] or 0) for r in rows)
    print(f"total cost USD {total:.4f}; report: eval/REPORT.md")


if __name__ == "__main__":
    main()
