"""python -m seed.run：重建示範資料（不動知識庫表）。固定 seed，每次結果相同。"""

import sys
import time
from pathlib import Path

from sqlalchemy import insert, text

from app.db import engine
from app.models import Base
from seed.checks import run_checks, write_report
from seed.context import Ctx
from seed.events import (
    Planner, emit_attendance, emit_leaves_and_ledger, emit_overtime, plan_comp_time_usage, plan_fixture, plan_overtime,
    plan_random, settle_ledgers,
)
from seed.people import build_org, build_people, emit_people
from seed.records import build_reviews, emit_benefits, emit_history_and_salary, emit_insurance, emit_payslips, emit_reference

KEEP = {"policy_documents", "policy_chunks"}
ORDER = [
    "org_units", "job_grades", "work_schedules", "employees", "users", "user_roles", "dependents", "employment_history",
    "salary_profiles", "insurance_enrollments", "calendar_days", "leave_types", "leave_requests", "leave_ledger",
    "overtime_records", "attendance_records", "payslips", "payslip_items", "benefit_claims", "law_rules", "company_settings",
]
HEAD_RANK = {"company": 0, "center": 1, "department": 2, "section": 3, None: 4}


def build() -> tuple[Ctx, Planner]:
    ctx = Ctx()
    build_org(ctx)
    build_people(ctx)
    p = Planner(ctx)
    for e in ctx.emps:
        (plan_fixture if e.fixture else plan_random)(p, e)
    for e in ctx.emps:
        plan_overtime(p, e)
    plan_comp_time_usage(p)
    payouts = settle_ledgers(p)
    emit_people(ctx)
    build_reviews(ctx)
    emit_history_and_salary(ctx)
    emit_insurance(ctx)
    emit_leaves_and_ledger(p)
    emit_overtime(ctx)
    emit_attendance(p)
    emit_payslips(ctx, p, payouts)
    emit_benefits(ctx)
    emit_reference(ctx)
    return ctx, p


def load(ctx: Ctx) -> None:
    tables = Base.metadata.tables
    rank = {e.id: HEAD_RANK[e.head_level] for e in ctx.emps}
    ctx.rows["employees"].sort(key=lambda r: (rank[r["id"]], r["id"]))
    heads = {r["id"]: r["head_emp_id"] for r in ctx.rows["org_units"]}
    with engine.begin() as conn:
        names = ", ".join(t for t in tables if t not in KEEP)
        conn.execute(text(f"TRUNCATE {names} RESTART IDENTITY CASCADE"))
        for t in ORDER:
            rows = ctx.rows.get(t, [])
            if t == "org_units":
                rows = [{**r, "head_emp_id": None} for r in rows]
            for i in range(0, len(rows), 5000):
                conn.execute(insert(tables[t]), rows[i : i + 5000])
        for uid, head in heads.items():
            conn.execute(text("UPDATE org_units SET head_emp_id = :h WHERE id = :i"), {"h": head, "i": uid})
        for t in ORDER:
            if "id" in tables[t].c and tables[t].c.id.autoincrement:
                conn.execute(text(f"SELECT setval(pg_get_serial_sequence('{t}', 'id'), COALESCE((SELECT MAX(id) FROM {t}), 1))"))


def main() -> None:
    t0 = time.time()
    ctx, p = build()
    checks = run_checks(ctx, p)
    report = Path(__file__).parent / "REPORT.md"
    write_report(ctx, checks, str(report))
    failed = [c for c in checks if not c[1]]
    for name, ok, detail in checks:
        print(("PASS " if ok else "FAIL ") + name + ("" if ok else f" → {detail}"))
    if failed:
        sys.exit(f"{len(failed)} 項一致性檢查失敗，未寫入資料庫")
    if "--dry-run" not in sys.argv:
        load(ctx)
    print(f"done in {time.time() - t0:.1f}s; " + ", ".join(f"{t}={len(r)}" for t, r in sorted(ctx.rows.items())))


if __name__ == "__main__":
    main()
