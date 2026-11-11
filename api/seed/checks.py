"""產生後的一致性檢查與資料品質報告。任何檢查失敗就不寫入資料庫。"""

from collections import Counter, defaultdict
from datetime import date, timedelta
from fractions import Fraction
from statistics import median

from app.engine.overtime import OvertimeEntry, counted_extended_hours
from app.engine.rules import rule
from seed.context import AS_OF, Ctx
from seed.events import Planner
from seed.names import is_valid_national_id
from seed.people import allowances_for, attendance_bonus_for


def run_checks(ctx: Ctx, p: Planner) -> list[tuple[str, bool, str]]:
    out: list[tuple[str, bool, str]] = []
    emps = ctx.emps

    def check(name: str, bad: list) -> None:
        out.append((name, not bad, "; ".join(map(str, bad[:5])) if bad else f"OK"))

    active = [lv for lv in ctx.leaves if lv.status in ("approved", "pending")]
    check("請假時數皆大於 0", [lv.id for lv in ctx.leaves if lv.hours <= 0])
    per_day: dict[tuple[int, date], Fraction] = defaultdict(Fraction)
    for lv in active:
        for d, h in lv.day_hours.items():
            per_day[(lv.emp_id, d)] += h
    check("同一人同一天請假不超過 8 小時（無重疊）", [k for k, v in per_day.items() if v > 8])
    check("請假皆在在職期間", [lv.id for lv in active if not all(ctx.emp(lv.emp_id).employed_on(d) for d in lv.day_hours)])
    check("沒有自己簽自己的假", [lv.id for lv in ctx.leaves if lv.approver_id == lv.emp_id])
    check("除 GM 外每個在職者都有主管", [e.name for e in emps if e.manager_id is None and e.head_level != "company"])
    sick_year: dict[tuple[int, int], Fraction] = defaultdict(Fraction)
    for lv in active:
        if lv.leave_type == "sick":
            for d, h in lv.day_hours.items():
                sick_year[(lv.emp_id, d.year)] += h
    check("未住院病假每年不超過 30 日", [k for k, v in sick_year.items() if v > 240])
    for code, books in (("特休", p.annual), ("補休", p.comp), ("生日假", p.bday)):
        bad = [(eid, per) for eid, b in books.items() for per in {g[1] for g in b.grants} if b.balance(per) < 0]
        check(f"{code}帳本各期間餘額不為負", bad)
    ot_month: dict[tuple[int, str], Fraction] = defaultdict(Fraction)
    for o in ctx.overtime:
        if o.day_type == "weekday" and o.hours > 4:
            out.append(("平日加班不超過 4 小時", False, str(o)))
        ot_month[(o.emp_id, o.work_date.strftime("%Y-%m"))] += counted_extended_hours(OvertimeEntry(o.work_date, o.day_type, o.hours))
    check("每月延長工時不超過 46 小時", [k for k, v in ot_month.items() if v > 46])
    check("加班日不在請假日（全天）", [o.id for o in ctx.overtime if per_day.get((o.emp_id, o.work_date), 0) >= 8])
    check("身分證字號檢查碼全部無效（不會對到真人）", [e.national_id for e in emps if is_valid_national_id(e.national_id)])
    bad_wage = []
    for e in emps:
        for eff, base in e.salary_history:
            mw = rule("minimum_wage", max(eff, date(2025, 1, 1))).params["monthly"]
            if base + sum(allowances_for(e).values()) + attendance_bonus_for(e) < mw:
                bad_wage.append((e.name, eff, base))
    check("月薪資不低於當年最低工資", bad_wage)
    att = ctx.rows.get("attendance_records", [])
    check("離職後沒有出勤紀錄", [a["emp_id"] for a in att if ctx.emp(a["emp_id"]).termination and a["work_date"] > ctx.emp(a["emp_id"]).termination])
    check("打卡下班晚於上班", [a for a in att if a["clock_in"] and a["clock_out"] and a["clock_out"] <= a["clock_in"]])
    check("員工 email 不重複", [k for k, v in Counter(e.email for e in emps).items() if v > 1])
    check("薪資單淨額為正", [r["id"] for r in ctx.rows.get("payslips", []) if r["net"] <= 0])
    return out


def write_report(ctx: Ctx, checks: list[tuple[str, bool, str]], path: str) -> None:
    emps = ctx.emps
    active = [e for e in emps if not (e.termination and e.termination < AS_OF)]
    by_center = Counter()
    for e in active:
        code = e.unit.split("-")[0]
        by_center[ctx.units[code]["name"]] += 1
    lines = ["# 合成資料品質報告", "", f"基準日：{AS_OF}（固定 seed，可重現）", "", "## 一致性檢查", "", "| 檢查 | 結果 |", "|---|---|"]
    lines += [f"| {n} | {'通過' if ok else '失敗：' + d} |" for n, ok, d in checks]
    lines += ["", "## 人數", "", f"- 在職 {len(active)} 人、近兩年離職 {len(emps) - len(active)} 人", "",
              "| 單位 | 在職人數 |", "|---|---|"]
    lines += [f"| {k} | {v} |" for k, v in by_center.most_common()]
    g = Counter(e.gender for e in active)
    lines += ["", f"- 性別：男 {g['M']}、女 {g['F']}"]
    tenure = Counter()
    for e in active:
        y = (AS_OF - e.hire).days / 365.25
        tenure["未滿1年" if y < 1 else "1–3年" if y < 3 else "3–5年" if y < 5 else "5–10年" if y < 10 else "10年以上"] += 1
    lines += [f"- 年資分布：" + "、".join(f"{k} {tenure[k]}" for k in ["未滿1年", "1–3年", "3–5年", "5–10年", "10年以上"])]
    lines += ["", "## 職等與本薪（在職）", "", "| 職等 | 人數 | 本薪中位數 | 最低 | 最高 |", "|---|---|---|---|---|"]
    for grade in sorted({e.grade for e in active}):
        bases = [e.base_on(AS_OF) for e in active if e.grade == grade]
        lines.append(f"| {grade} | {len(bases)} | {int(median(bases)):,} | {min(bases):,} | {max(bases):,} |")
    lines += ["", "## 資料量", "", "| 表 | 筆數 |", "|---|---|"]
    lines += [f"| {t} | {len(rows):,} |" for t, rows in sorted(ctx.rows.items())]
    leave_c = Counter(lv.leave_type for lv in ctx.leaves)
    lines += ["", "## 假別筆數", "", "、".join(f"{k} {v}" for k, v in leave_c.most_common())]
    lines += ["", "## 關鍵員工（fixtures）", "", "| 代號 | 姓名 | 帳號 | 單位 | 職稱 | 到職日 | 測試重點 |", "|---|---|---|---|---|---|---|"]
    notes = {
        "F00": "總經理", "F13": "處長，間接部屬範圍", "F15": "部門經理", "F02": "課長，查團隊出勤", "F03": "薪資越權測試對象；2026-11-10 滿 5 年",
        "F01": "曆年制特休、遞延、待簽核預扣", "F04": "到職未滿 6 個月（11-11 滿）", "F05": "10 月加班逼近上限、休息日 10h、國定假日出勤、補休",
        "F06": "已離職（2026-08-31）", "F08": "人資經理，全公司 HRBP", "F07": "HRBP（研發、製造）", "F09": "薪酬專員（payroll）",
        "F10": "婚假新制過渡（14 日）、延長請假期間", "F11": "部門經理", "F12": "產假後以日請育嬰留停", "F14": "病假 27 日逼近 30 日上限",
    }
    for e in emps:
        if e.fixture:
            lines.append(f"| {e.fixture['key']} | {e.name} | {e.email.split('@')[0]} | {ctx.units[e.unit]['name']} | {e.title} | {e.hire} | {notes.get(e.fixture['key'], '')} |")
    lines += ["", "系統管理員帳號：`sysadmin`（無員工資料權限）。所有示範帳號密碼為環境變數 `SEED_DEMO_PASSWORD`。", ""]
    lines += ["## 已知簡化", "", "- 薪資單不模擬所得稅扣繳。",
              "- 曆年制特休於 1/1 一次給足當年度比例日數；年度中離職者未按比例收回（對員工有利）。",
              "- 2024 年度遞延特休以隨機時數表示（資料自 2025-01-01 起）。", ""]
    with open(path, "w") as f:
        f.write("\n".join(lines))
    _ = timedelta
