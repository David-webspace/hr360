"""Judge 校準：python -m app.evals.calibrate

用 cases.yaml 的 reference_answer（人工撰寫的正確回答）與 mutations（故意改錯的版本）測 judge：
原文必須判通過、每個改錯版本必須判不通過。全部答對才採信 judge 的口徑分數。
"""

import json
from concurrent.futures import ThreadPoolExecutor

from app.agent import audit
from app.agent.llm import Usage, get_client
from app.agent.router import model_for
from app.evals.judge import judge
from app.evals.run import ROOT, load_cases


def main() -> None:
    client, model = get_client(), model_for("strong")
    jobs = []
    for c in load_cases():
        if "reference_answer" not in c:
            continue
        e = c["expect"]
        jobs.append((c["id"], "original", c["reference_answer"], True, c["question"], e))
        for i, (src, dst) in enumerate(c.get("mutations", [])):
            assert src in c["reference_answer"], f"{c['id']} mutation 原文不存在：{src}"
            jobs.append((c["id"], f"mutation{i + 1}", c["reference_answer"].replace(src, dst), False, c["question"], e))

    def one(job):
        cid, kind, answer, should_pass, q, e = job
        verdict, usage = judge(client, model, q, answer, e.get("claims", []), e.get("forbidden_claims", []))
        return {"case": cid, "kind": kind, "expected_pass": should_pass, "judge_pass": verdict["pass"],
                "correct": verdict["pass"] == should_pass, "verdict": verdict, "usage": usage}

    with ThreadPoolExecutor(4) as pool:
        rows = list(pool.map(one, jobs))
    total = Usage()
    for r in rows:
        total.add(r.pop("usage"))
    correct = sum(r["correct"] for r in rows)
    lines = ["# Judge 校準", "", f"judge 模型：{model}；{correct}/{len(rows)} 判斷正確", "",
             "| 題號 | 版本 | 應判 | judge 判 | 結果 |", "|---|---|---|---|---|"]
    lines += [f"| {r['case']} | {r['kind']} | {'通過' if r['expected_pass'] else '不通過'} | "
              f"{'通過' if r['judge_pass'] else '不通過'} | {'✓' if r['correct'] else '✗'} |" for r in rows]
    (ROOT / "CALIBRATION.md").write_text("\n".join(lines) + "\n")
    for r in rows:
        if not r["correct"]:
            print("WRONG", r["case"], r["kind"], json.dumps(r["verdict"], ensure_ascii=False))
    print(f"judge {model}: {correct}/{len(rows)} correct; cost USD {audit.cost_usd({model: total})}")


if __name__ == "__main__":
    main()
