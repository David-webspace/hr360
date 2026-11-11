"""唯讀查詢服務。每個函式第一步都是 resolve_employee / scope_sql，權限在這裡決定，不在 LLM。"""

from datetime import date, timedelta
from fractions import Fraction

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.auth import Principal
from app.company import policy as P
from app.company.benefits import travel_entitlement
from app.config import today
from app.engine.annual_leave import calendar_year_entitlement
from app.engine.dates import add_months
from app.engine.insurance import monthly_premiums
from app.engine.leave import LEAVE_TYPES, marriage_leave_days
from app.engine.overtime import OvertimeEntry, monthly_overtime
from app.policy import PolicyDenied, resolve_employee, scope_sql
from app.services import ledger


def num(x: Fraction | float | int) -> float | int:
    x = Fraction(str(x)) if isinstance(x, float) else Fraction(x)
    return int(x) if x.denominator == 1 else round(float(x), 2)


def leave_name(code: str) -> str:
    return "生日假" if code == "birthday" else LEAVE_TYPES[code].name


def find_employee(db: Session, p: Principal, query: str) -> dict:
    scope, sp = scope_sql(p, "S0")
    rows = db.execute(text(f"""
        SELECT e.name, e.emp_no, o.name AS unit, e.title, e.phone_ext, e.email
        FROM employees e JOIN org_units o ON o.id = e.org_unit_id
        WHERE e.status <> 'terminated' AND (e.name LIKE :q OR e.emp_no = :exact OR e.english_name ILIKE :q) AND {scope}
        ORDER BY e.name LIMIT 10
    """), {"q": f"%{query.strip()}%", "exact": query.strip(), **sp}).mappings().all()
    return {"matches": [dict(r) for r in rows], "note": "通訊錄只提供公開資訊（S0）"}


def _salary_profile(db: Session, emp_id: int, on: date) -> dict:
    r = db.execute(text("""
        SELECT base_monthly, regular_allowances, attendance_bonus FROM salary_profiles
        WHERE emp_id = :e AND effective_from <= :d ORDER BY effective_from DESC LIMIT 1
    """), {"e": emp_id, "d": on}).mappings().one()
    allowances = dict(r["regular_allowances"])
    return {"base": r["base_monthly"], "allowances": allowances, "attendance_bonus": r["attendance_bonus"],
            "monthly_wage": r["base_monthly"] + sum(allowances.values()) + r["attendance_bonus"]}


def leave_balance(db: Session, p: Principal, employee: str | None = None) -> dict:
    e = resolve_employee(db, p, employee, "S2")
    t = today()
    out: dict = {"employee": e["name"], "as_of": t.isoformat(), "unit": "hour"}
    annual = ledger.periods(db, e["id"], "annual", e["birth_date"], t)
    valid = [x for x in annual if x.valid_from <= t <= x.expires]
    ent = calendar_year_entitlement(e["seniority_start_date"], t.year)
    out["annual"] = {
        "system": "曆年制（年度未休自動遞延一年）",
        "periods": [{"period": x.key, "granted": num(x.granted), "used": num(x.used), "pending_hold": num(x.held),
                     "remaining": num(x.remaining), "available": num(x.available), "expires": x.expires.isoformat()}
                    for x in valid],
        "remaining_total": num(sum((x.remaining for x in valid), Fraction(0))),
        "available_total": num(sum((x.available for x in valid), Fraction(0))),
        "basis": {"remaining": "已扣除已核准假單，未扣待簽核", "available": "再扣除待簽核預扣，為目前可申請時數"},
        "entitlement_this_year": {"hours": num(ent.value), "steps": ent.steps},
    }
    if not any(x.granted for x in valid):
        out["annual"]["note"] = f"尚未取得特休；年資滿 6 個月之日（{add_months(e['seniority_start_date'], 6)}）給 3 日（24 小時）"
    comp = [x for x in ledger.periods(db, e["id"], "comp_time", e["birth_date"], t) if x.available > 0 and x.expires >= t]
    out["comp_time"] = {"available": num(sum((x.available for x in comp), Fraction(0))),
                        "items": [{"overtime_date": x.key, "available": num(x.available), "expires": x.expires.isoformat()} for x in comp]}
    bday = [x for x in ledger.periods(db, e["id"], "birthday", e["birth_date"], t) if x.key == str(t.year)]
    if bday:
        b = bday[0]
        out["birthday"] = {"available": num(b.available), "window": f"{b.valid_from}～{b.expires}",
                           "expired": t > b.expires}
    used = dict(db.execute(text("""
        SELECT leave_type, SUM(hours) FROM leave_requests
        WHERE emp_id = :e AND status = 'approved' AND EXTRACT(YEAR FROM start_at AT TIME ZONE 'Asia/Taipei') = :y
        GROUP BY leave_type
    """), {"e": e["id"], "y": t.year}).all())
    sick = Fraction(str(used.get("sick", 0)))
    personal = Fraction(str(used.get("personal", 0))) + Fraction(str(used.get("family_care", 0)))
    out["statutory"] = {
        "sick_unhospitalized": {"used": num(sick), "cap": 240, "remaining": num(240 - sick),
                                "full_pay_remaining": num(max(Fraction(0), P.COMPANY_LEAVE["sick_full_pay_days"] * 8 - sick)),
                                "rule": "每年前 5 日全薪，其後半薪，上限 30 日"},
        "personal_incl_family_care": {"used": num(personal), "cap": 112, "remaining": num(112 - personal)},
        "family_care": {"used": num(Fraction(str(used.get("family_care", 0)))), "cap": 56},
    }
    wedding = db.execute(text("""
        SELECT event_date FROM benefit_claims WHERE emp_id = :e AND benefit_code = 'wedding' ORDER BY event_date DESC LIMIT 1
    """), {"e": e["id"]}).scalar()
    if wedding and wedding >= t - timedelta(days=400):
        m = marriage_leave_days(wedding, 0, extended_window=True)
        m_used = Fraction(str(used.get("marriage", 0)))
        out["marriage"] = {"registered": wedding.isoformat(), "entitled_days": num(m.value), "used_hours": num(m_used),
                           "remaining_hours": num(int(m.value) * 8 - m_used), "steps": m.steps,
                           "basis": "已用時數包含已核准但尚未開始的婚假（例如 12 月已核准者），不含待簽核"}
    return out


def overtime_pay(db: Session, p: Principal, month: str, employee: str | None = None) -> dict:
    e = resolve_employee(db, p, employee, "S3")
    y, m = map(int, month.split("-"))
    first = date(y, m, 1)
    last = date(y + (m == 12), m % 12 + 1, 1) - timedelta(days=1)
    rows = db.execute(text("""
        SELECT work_date, day_type, hours, compensation, status FROM overtime_records
        WHERE emp_id = :e AND work_date BETWEEN :a AND :b ORDER BY work_date
    """), {"e": e["id"], "a": first, "b": last}).mappings().all()
    approved = [r for r in rows if r["status"] == "approved"]
    out = {"employee": e["name"], "month": month,
           "records": [{"date": r["work_date"].isoformat(), "day_type": r["day_type"], "hours": num(r["hours"]),
                        "compensation": "補休" if r["compensation"] == "comp_time" else "加班費", "status": r["status"]} for r in rows]}
    if not approved:
        out["result"] = "本月沒有已核准的加班紀錄"
        return out
    wage = _salary_profile(db, e["id"], last)["monthly_wage"]
    r = monthly_overtime(wage, [OvertimeEntry(x["work_date"], x["day_type"], Fraction(str(x["hours"])), x["compensation"]) for x in approved])
    out.update({"overtime_pay": int(r.value), "steps": r.steps, "warnings": r.warnings, "basis": r.basis,
                "law_refs": r.law_refs, "pay_date": f"{last + timedelta(days=5)}（隨 {month} 月薪資發放）",
                "pending_not_included": [x["date"] for x in out["records"] if x["status"] == "pending"]})
    return out


def team_leave_summary(db: Session, p: Principal, start: str, end: str, leave_type: str | None = None) -> dict:
    if not (p.managed_paths or p.hrbp_paths):
        raise PolicyDenied("not_manager")
    scope, sp = scope_sql(p, "S1")
    rows = db.execute(text(f"""
        SELECT e.name, o.name AS unit, r.leave_type, SUM(r.hours) AS hours, COUNT(*) AS n
        FROM leave_requests r JOIN employees e ON e.id = r.emp_id JOIN org_units o ON o.id = e.org_unit_id
        WHERE r.status = 'approved' AND e.id <> :me_id AND {scope}
          AND (r.start_at AT TIME ZONE 'Asia/Taipei')::date BETWEEN :a AND :b
          AND (CAST(:lt AS text) IS NULL OR r.leave_type = :lt)
        GROUP BY e.name, o.name, r.leave_type
    """), {**sp, "me_id": p.emp_id or -1, "a": date.fromisoformat(start), "b": date.fromisoformat(end), "lt": leave_type}).mappings().all()
    people: dict[str, dict] = {}
    for r in rows:
        x = people.setdefault(r["name"], {"name": r["name"], "unit": r["unit"], "total_hours": 0, "by_type": {}})
        x["by_type"][leave_name(r["leave_type"])] = num(r["hours"])
        x["total_hours"] = num(Fraction(str(x["total_hours"])) + Fraction(str(r["hours"])))
    ranked = sorted(people.values(), key=lambda x: -x["total_hours"])
    headcount = db.execute(text(f"SELECT COUNT(*) FROM employees e WHERE e.status <> 'terminated' AND e.id <> :me_id AND {scope}"),
                           {**sp, "me_id": p.emp_id or -1}).scalar()
    return {"period": f"{start}～{end}", "scope_headcount": headcount, "people_with_leave": len(ranked),
            "ranking": ranked[:15], "basis": "只計已核准假單、依請假開始日歸屬期間；不含請假原因（S3）"}


def salary(db: Session, p: Principal, employee: str | None = None) -> dict:
    e = resolve_employee(db, p, employee, "S3")
    prof = _salary_profile(db, e["id"], today())
    last = db.execute(text("SELECT pay_month, gross, deductions, net FROM payslips WHERE emp_id = :e ORDER BY pay_month DESC LIMIT 1"),
                      {"e": e["id"]}).mappings().one_or_none()
    return {"employee": e["name"], "salary": prof, "latest_payslip": dict(last) if last else None}


def payslip(db: Session, p: Principal, month: str, employee: str | None = None) -> dict:
    e = resolve_employee(db, p, employee, "S3")
    ps = db.execute(text("SELECT id, pay_month, gross, deductions, net, paid_on FROM payslips WHERE emp_id = :e AND pay_month = :m"),
                    {"e": e["id"], "m": month}).mappings().one_or_none()
    if ps is None:
        return {"employee": e["name"], "month": month, "result": "查無該月薪資單"}
    items = db.execute(text("SELECT category, label, amount, calc_note FROM payslip_items WHERE payslip_id = :i ORDER BY id"),
                       {"i": ps["id"]}).mappings().all()
    return {"employee": e["name"], "month": month, "paid_on": ps["paid_on"].isoformat(), "gross": ps["gross"],
            "deductions": ps["deductions"], "net": ps["net"],
            "items": [{"type": "給付" if i["category"] == "earning" else "扣款", "label": i["label"], "amount": i["amount"],
                       **({"steps": i["calc_note"]["steps"]} if i["calc_note"] and "steps" in i["calc_note"] else {})} for i in items]}


def insurance_summary(db: Session, p: Principal, employee: str | None = None) -> dict:
    e = resolve_employee(db, p, employee, "S3")
    t = today()
    enr = db.execute(text("""
        SELECT nhi_dependents, pension_voluntary_rate FROM insurance_enrollments
        WHERE emp_id = :e AND effective_from <= :d ORDER BY effective_from DESC LIMIT 1
    """), {"e": e["id"], "d": t}).mappings().one()
    wage = _salary_profile(db, e["id"], t)["monthly_wage"]
    r = monthly_premiums(wage, t, enr["nhi_dependents"], Fraction(str(enr["pension_voluntary_rate"])) / 100, P.OCCUPATIONAL_RATE_DEMO)
    return {"employee": e["name"], "monthly_wage": wage, "employee_pays_total": int(r.value), **r.basis,
            "steps": r.steps, "rule_version": r.rule_version}


def travel_subsidy(db: Session, p: Principal, year: int | None = None, employee: str | None = None) -> dict:
    e = resolve_employee(db, p, employee, "S2")
    y = year or today().year
    ent = travel_entitlement(e["seniority_start_date"], y)
    claims = db.execute(text("""
        SELECT event_date, amount, status FROM benefit_claims WHERE emp_id = :e AND benefit_code = 'travel' AND claim_year = :y
    """), {"e": e["id"], "y": y}).mappings().all()
    used = sum(c["amount"] for c in claims)
    return {"employee": e["name"], "year": y, "entitlement": ent["amount"], "basis": ent["basis"], "claimed": used,
            "remaining": ent["amount"] - used, "claims": [{**dict(c), "event_date": c["event_date"].isoformat()} for c in claims],
            "family_extra": f"眷屬每人 {P.TRAVEL_SUBSIDY['family_per_person']:,} 元，最多 {P.TRAVEL_SUBSIDY['family_max_persons']} 人（另計）",
            "deadline": f"{y} 年 {P.TRAVEL_SUBSIDY['claim_deadline']}", "no_cash_out": True}
