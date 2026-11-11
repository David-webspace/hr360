"""薪資單、投保紀錄、福利請領、人事異動、考核、行事曆、法規與公司參數。"""

import calendar
from collections import defaultdict
from datetime import date, time, timedelta
from fractions import Fraction

from app.company import policy
from app.company.benefits import travel_entitlement
from app.company.payroll import PayInputs, compute_payslip
from app.engine.calendar_tw import HOLIDAYS_2025, HOLIDAYS_2026
from app.engine.insurance import monthly_premiums
from app.engine.leave import LEAVE_TYPES
from app.engine.overtime import OvertimeEntry
from app.engine.rules import RULES
from seed.context import AS_OF, DATA_START, Ctx, Emp, at
from seed.events import Planner
from seed.people import allowances_for, attendance_bonus_for

REVIEWS = {"2025H1": date(2025, 6, 30), "2025H2": date(2025, 12, 31), "2026H1": date(2026, 6, 30)}
FESTIVALS = [("春節", date(2025, 1, 20)), ("端午節", date(2025, 5, 23)), ("中秋節", date(2025, 9, 26)),
             ("春節", date(2026, 2, 6)), ("端午節", date(2026, 6, 12)), ("中秋節", date(2026, 9, 18))]
FUNERAL_BY_RELATION = {"parent": "父母、配偶、子女", "adoptive_parent": "父母、配偶、子女", "step_parent": "父母、配偶、子女",
                       "spouse": "父母、配偶、子女", "child": "父母、配偶、子女", "spouse_parent": "配偶之父母"}


def jsonable(x):
    if isinstance(x, Fraction):
        return str(x)
    if isinstance(x, date):
        return x.isoformat()
    if isinstance(x, dict):
        return {str(k): jsonable(v) for k, v in x.items()}
    if isinstance(x, (list, tuple, set, frozenset)):
        return [jsonable(v) for v in x]
    return x


def months(first: date, last: date):
    m = date(first.year, first.month, 1)
    while m <= last:
        yield m
        m = date(m.year + (m.month == 12), m.month % 12 + 1, 1)


def build_reviews(ctx: Ctx) -> None:
    r = ctx.rng
    dist = policy.PERFORMANCE["distribution"]
    for e in ctx.emps:
        for period, d in REVIEWS.items():
            if e.employed_on(d) and e.hire + timedelta(days=90) <= d:
                e.perf[period] = r.choices(list(dist), weights=list(dist.values()))[0]
                ctx.add("employment_history", {"emp_id": e.id, "effective_date": d, "event": "performance_review",
                                               "detail": {"period": period, "rating": e.perf[period]}})


def emit_history_and_salary(ctx: Ctx) -> None:
    for e in ctx.emps:
        ctx.add("employment_history", {"emp_id": e.id, "effective_date": e.hire, "event": "hire",
                                       "detail": {"unit": e.unit, "title": e.title}})
        prev = None
        for eff, base in e.salary_history:
            ctx.add("salary_profiles", {
                "emp_id": e.id, "effective_from": eff, "base_monthly": base, "regular_allowances": allowances_for(e),
                "attendance_bonus": attendance_bonus_for(e), "bank_account_masked": f"***-****-{ctx.rng.randint(1000, 9999)}",
            })
            if prev is not None:
                ctx.add("employment_history", {"emp_id": e.id, "effective_date": eff, "event": "salary_adjust",
                                               "detail": {"from": prev, "to": base, "reason": "年度調薪"}})
            prev = base
        if e.termination:
            ctx.add("employment_history", {"emp_id": e.id, "effective_date": e.termination, "event": "terminate",
                                           "detail": {"reason": e.term_reason}})


def nhi_dependents(ctx: Ctx, emp_id: int, on: date) -> int:
    return sum(1 for d in ctx.rows.get("dependents", []) if d["emp_id"] == emp_id and d["nhi_enrolled"] and d["birth_date"] <= on)


def emit_insurance(ctx: Ctx) -> None:
    for e in ctx.emps:
        dates = {max(e.hire, DATA_START), date(2026, 1, 1)} | {eff for eff, _ in e.salary_history if eff >= DATA_START}
        for eff in sorted(d for d in dates if e.employed_on(d)):
            wage = e.base_on(eff) + sum(allowances_for(e).values()) + attendance_bonus_for(e)
            deps = nhi_dependents(ctx, e.id, eff)
            b = monthly_premiums(wage, eff, deps, e.voluntary_rate, policy.OCCUPATIONAL_RATE_DEMO).basis
            ctx.add("insurance_enrollments", {
                "emp_id": e.id, "effective_from": eff, "labor_insured_salary": b["labor_insured_salary"],
                "health_insured_salary": b["health_insured_amount"], "pension_contribution_wage": b["pension_contribution_wage"],
                "pension_voluntary_rate": float(e.voluntary_rate * 100), "nhi_dependents": deps,
            })


def _year_end_bonus(e: Emp) -> int:
    if not (e.hire <= date(2025, 12, 31) and e.employed_on(date(2026, 2, 5))):
        return 0
    worked = 12 if e.hire <= date(2025, 1, 1) else 12 - e.hire.month + (1 if e.hire.day == 1 else 0)
    perf = policy.PAYROLL["year_end_bonus_performance_months"][e.perf.get("2025H2", "B")]
    months_ = (policy.PAYROLL["year_end_bonus_guaranteed_months"] + perf) * worked / 12
    return int(round(e.base_on(date(2025, 12, 31)) * months_, -2))


def emit_payslips(ctx: Ctx, p: Planner, annual_payouts: dict) -> None:
    by_emp_leave: dict[int, list] = defaultdict(list)
    for lv in ctx.leaves:
        if lv.status == "approved":
            by_emp_leave[lv.emp_id].append(lv)
    pay_ot: dict[tuple[int, str], list[OvertimeEntry]] = defaultdict(list)
    for o in ctx.overtime:
        if o.status == "approved" and o.compensation == "pay":
            pay_ot[(o.emp_id, o.work_date.strftime("%Y-%m"))].append(OvertimeEntry(o.work_date, o.day_type, o.hours))
    pid = 0
    for e in ctx.emps:
        last_day = min(e.termination or AS_OF, date(2026, 10, 31))
        for m in months(max(e.hire, DATA_START), last_day):
            ym = m.strftime("%Y-%m")
            dim = calendar.monthrange(m.year, m.month)[1]
            m_end = date(m.year, m.month, dim)
            first, last = max(m, e.hire), min(m_end, e.termination or m_end)
            employed = (last - first).days + 1
            hours: dict[str, Fraction] = defaultdict(Fraction)
            sick_before = Fraction(0)
            parental_days = 0
            for lv in by_emp_leave[e.id]:
                for d, h in lv.day_hours.items():
                    if m <= d <= m_end:
                        hours[lv.leave_type] += h
                        parental_days += lv.leave_type == "parental_daily"
                    elif lv.leave_type == "sick" and d.year == m.year and d < m:
                        sick_before += h
            unpaid = 0 if employed == dim else 30 - min(employed, 30)
            inputs = PayInputs(
                pay_month=ym, base=e.base_on(m_end), allowances=allowances_for(e), attendance_bonus=attendance_bonus_for(e),
                leave_hours=dict(hours), sick_hours_before_month=sick_before, overtime=pay_ot.get((e.id, ym), []),
                comp_time_payout=[OvertimeEntry(d, t, h) for d, h, t in p.comp_payouts.get((e.id, ym), [])],
                annual_leave_payout_hours=annual_payouts.get((e.id, ym), Fraction(0)),
                year_end_bonus=_year_end_bonus(e) if ym == "2026-01" else 0,
                nhi_dependents=nhi_dependents(ctx, e.id, m_end), voluntary_pension_rate=e.voluntary_rate,
                unpaid_days=min(30, unpaid + parental_days),
            )
            items, totals = compute_payslip(inputs)
            pid += 1
            pay_on = date(m.year + (m.month == 12), m.month % 12 + 1, 5)
            ctx.add("payslips", {"id": pid, "emp_id": e.id, "pay_month": ym, "gross": totals["gross"],
                                 "deductions": totals["deductions"], "net": totals["net"], "paid_on": pay_on,
                                 "created_at": at(pay_on, time(9))})
            for it in items:
                ctx.add("payslip_items", {"payslip_id": pid, "category": it.category, "code": it.code, "label": it.label,
                                          "amount": it.amount, "calc_note": jsonable(it.note) if it.note else None})


def emit_benefits(ctx: Ctx) -> None:
    r = ctx.rng
    w = policy.WELFARE
    for e in ctx.emps:
        for name, d in FESTIVALS:
            if e.employed_on(d):
                ctx.add("benefit_claims", {"emp_id": e.id, "benefit_code": f"festival_{name}", "claim_year": d.year,
                                           "amount": w["festival_gifts"][name], "status": "paid", "event_date": d, "note": f"{name}禮金"})
        for y in (2025, 2026):
            d = date(y, e.birth.month, 1)
            if d <= AS_OF and e.employed_on(d):
                ctx.add("benefit_claims", {"emp_id": e.id, "benefit_code": "birthday", "claim_year": y,
                                           "amount": w["birthday_gift"], "status": "paid", "event_date": d, "note": "生日禮券"})
        fixture_claims = dict((e.fixture or {}).get("travel_claims", []))
        for y in (2025, 2026):
            if not e.employed_on(date(y, 6, 30)) and not e.employed_on(min(AS_OF, date(y, 12, 15))):
                continue
            ent = travel_entitlement(e.hire, y)["amount"]
            if e.fixture:
                amt = fixture_claims.get(y)
            else:
                amt = int(round(ent * r.uniform(0.6, 1.0), -2)) if r.random() < (0.78 if y == 2025 else 0.55) else None
            if amt:
                d = date(y, r.randint(4, 11), r.randint(1, 28))
                d = min(d, AS_OF - timedelta(days=3))
                ctx.add("benefit_claims", {"emp_id": e.id, "benefit_code": "travel", "claim_year": y, "amount": min(amt, ent),
                                           "status": "paid" if d < AS_OF - timedelta(days=20) else "approved", "event_date": d,
                                           "note": f"年度旅遊補助（額度 {ent:,}）"})
            if not e.fixture and r.random() < 0.35:
                d = date(y, r.randint(2, 11), r.randint(1, 28))
                if d <= AS_OF and e.employed_on(d):
                    ctx.add("benefit_claims", {"emp_id": e.id, "benefit_code": "health_check", "claim_year": y,
                                               "amount": int(round(r.uniform(3000, w["health_check"]["budget"]), -2)),
                                               "status": "paid", "event_date": d, "note": "員工健康檢查"})
        if e.marriage_registered and e.marriage_registered >= DATA_START:
            d = min(e.marriage_registered + timedelta(days=14), AS_OF)
            ctx.add("benefit_claims", {"emp_id": e.id, "benefit_code": "wedding", "claim_year": d.year, "amount": w["wedding_gift"],
                                       "status": "paid", "event_date": e.marriage_registered, "note": "結婚禮金"})
        if e.child_born and e.child_born >= DATA_START:
            ctx.add("benefit_claims", {"emp_id": e.id, "benefit_code": "childbirth", "claim_year": e.child_born.year,
                                       "amount": w["childbirth_gift"], "status": "paid", "event_date": e.child_born, "note": "生育補助"})
    for lv in ctx.leaves:
        if lv.leave_type == "bereavement" and lv.reason:
            group = FUNERAL_BY_RELATION.get(lv.reason.split(":")[1])
            if group:
                ctx.add("benefit_claims", {"emp_id": lv.emp_id, "benefit_code": "funeral", "claim_year": lv.start.year,
                                           "amount": w["funeral"][group], "status": "paid", "event_date": lv.start.date(),
                                           "note": f"喪葬補助（{group}）"})


def emit_reference(ctx: Ctx) -> None:
    holidays = {**HOLIDAYS_2025, **HOLIDAYS_2026}
    d = date(2025, 1, 1)
    while d <= date(2026, 12, 31):
        t = ctx.cal.day_type(d)
        ctx.add("calendar_days", {"day": d, "day_type": "makeup_workday" if d in ctx.cal.makeup_workdays else t,
                                  "name": holidays.get(d) or ("補行上班" if d in ctx.cal.makeup_workdays else None)})
        d += timedelta(days=1)
    for lt in LEAVE_TYPES.values():
        ctx.add("leave_types", {"code": lt.code, "name": lt.name, "pay_ratio": float(lt.pay_ratio),
                                "quota_rule_key": None, "min_unit_hours": float(lt.min_unit_hours),
                                "counts_calendar_days": lt.counts_calendar_days, "requires_attachment": lt.code in
                                ("sick", "marriage", "bereavement", "maternity", "occupational", "official"),
                                "reason_sensitivity": lt.reason_sensitivity, "law_ref": lt.law_ref})
    ctx.add("leave_types", {"code": "birthday", "name": "生日假", "pay_ratio": 1.0, "quota_rule_key": None, "min_unit_hours": 8.0,
                            "counts_calendar_days": False, "requires_attachment": False, "reason_sensitivity": "S2",
                            "law_ref": "曜川科技假勤管理辦法（公司福利假，非法定）"})
    for key, versions in RULES.items():
        for rv in versions:
            ctx.add("law_rules", {"rule_key": key, "effective_from": rv.effective_from, "params": jsonable(rv.params),
                                  "source_ref": rv.source})
    descriptions = {
        "WORK_HOURS": "工時與出勤", "ANNUAL_LEAVE": "特休制度", "COMPANY_LEAVE": "公司福利假", "OVERTIME": "加班與補休",
        "PAYROLL": "薪資結構與發放", "JOB_GRADES": "職等薪資帶", "TRAVEL_SUBSIDY": "員工旅遊補助", "WELFARE": "職工福利",
        "TRAINING": "教育訓練補助", "BUSINESS_TRIP": "差旅", "REMOTE_WORK": "遠距工作", "PERFORMANCE": "績效考核",
        "GROUP_INSURANCE": "團體保險", "HARASSMENT": "性騷擾申訴", "COMPANY": "公司基本資料",
    }
    for name, desc in descriptions.items():
        ctx.add("company_settings", {"key": name.lower(), "value": jsonable(getattr(policy, name)), "description": desc})
    ctx.add("company_settings", {"key": "probation_months", "value": {"months": policy.PROBATION_MONTHS}, "description": "試用期"})
