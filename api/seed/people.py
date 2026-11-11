"""組織、職等、班表、員工、眷屬、帳號與角色。"""

import os
from datetime import date, timedelta
from fractions import Fraction

from app.company.policy import COMPANY, JOB_GRADES, PAYROLL, PROBATION_MONTHS
from app.engine.dates import add_months
from app.security import hash_password
from seed.context import AS_OF, SCHEDULES, Ctx, Emp
from seed.fixtures import FIXTURES
from seed.names import SURNAMES, address, fake_national_id, mobile, pick_name
from seed.org import FAMILIES, UNIT_BY_CODE, UNITS, staff_title

HEAD_GRADE = {"section": 4, "department": 5, "center": 6, "company": 7}
EN_SURNAME = {s: en for s, en, _ in SURNAMES}


def grade_band(grade: int, step: int) -> tuple[int, int]:
    _, lo, hi = JOB_GRADES[grade]
    width = (hi - lo) / 3
    return int(lo + width * (step - 1)), int(lo + width * step)


def build_org(ctx: Ctx) -> None:
    for i, u in enumerate(UNITS, start=1):
        parent = ctx.units[u.parent] if u.parent else None
        path = (parent["path"] if parent else "/") + f"{i}/"
        ctx.units[u.code] = {
            "id": i, "code": u.code, "name": u.name, "level": u.level, "parent_id": parent["id"] if parent else None,
            "path": path, "head_emp_id": None, "site": u.site,
        }
    gid = 0
    for grade, (band, _, _) in JOB_GRADES.items():
        for step in (1, 2, 3):
            gid += 1
            lo, hi = grade_band(grade, step)
            ctx.add("job_grades", {"id": gid, "grade": grade, "step": step, "title_band": band, "salary_min": lo, "salary_max": hi})
    for code, s in SCHEDULES.items():
        ctx.add("work_schedules", {
            "id": s["id"], "code": code, "name": s["name"], "daily_hours": 8,
            "work_blocks": [[b[0].strftime("%H:%M"), b[1].strftime("%H:%M")] for b in s["blocks"]],
            "flex_start_from": s["flex"][0], "flex_start_to": s["flex"][1], "rest_day_weekday": 5, "regular_leave_weekday": 6,
        })


def _random_tenure_hire(ctx: Ctx, min_years: float = 0, max_years: float = 18.5) -> date:
    r = ctx.rng
    bucket = r.choices([(0, 1), (1, 3), (3, 5), (5, 10), (10, 18.5)], weights=[16, 26, 20, 24, 14])[0]
    lo, hi = max(bucket[0], min_years), min(max(bucket[1], min_years + 1), max_years)
    years = r.uniform(lo, hi)
    hire = AS_OF - timedelta(days=int(years * 365.25))
    hire = max(hire, COMPANY["founded"])
    while hire.weekday() != 0:  # 新人多在週一報到
        hire -= timedelta(days=1)
    return max(hire, COMPANY["founded"])


def _new_emp(ctx: Ctx, **kw) -> Emp:
    e = Emp(id=len(ctx.emps) + 1, emp_no="", **kw)
    ctx.emps.append(e)
    return e


def _salary_history(ctx: Ctx, e: Emp) -> None:
    """e.base 是 2026-04 調薪後的本薪，往回推 2025-04、2024-04 的本薪；早於到職日的生效日以到職日計。"""
    r = ctx.rng
    points = [(date(2026, 4, 1), e.base)]
    cur = e.base
    for eff in (date(2026, 4, 1), date(2025, 4, 1)):
        if e.hire >= eff:
            break
        pct = r.choices([0, 0.02, 0.03, 0.04, 0.05, 0.08], weights=[10, 25, 30, 20, 10, 5])[0]
        cur = int(round(cur / (1 + pct), -2))
        points.append((date(eff.year - 1, 4, 1), cur))
    e.salary_history = [(max(eff, e.hire), b) for eff, b in sorted(points)]


def build_people(ctx: Ctx) -> None:
    r = ctx.rng
    used: set[str] = set()
    fixture_heads = {f["role_unit"] for f in FIXTURES if f.get("role_unit")}
    fixture_staff_count: dict[str, int] = {}

    for f in FIXTURES:
        used.add(f["name"])
        surname = f["name"][0]
        unit = UNIT_BY_CODE[f["unit"]]
        e = _new_emp(
            ctx, name=f["name"], en=f["en"], surname_en=EN_SURNAME.get(surname, "Su"), gender=f["gender"],
            birth=f["birth"], unit=f["unit"], title=f["title"], grade=f["grade"][0], step=f["grade"][1],
            hire=f["hire"], base=f["base"], family=unit.family or "gmo",
            head_level=UNIT_BY_CODE[f["role_unit"]].level if f.get("role_unit") else None, fixture=f,
            marital=f.get("marital", "single"), marriage_registered=f.get("marriage_registered"),
            child_born=f.get("child_born"), roles=list(f.get("roles", [])),
        )
        if f.get("termination"):
            e.termination, e.term_reason = f["termination"]
        if not f.get("role_unit"):
            fixture_staff_count[f["unit"]] = fixture_staff_count.get(f["unit"], 0) + 1

    for u in UNITS:
        if u.head_title and u.code not in fixture_heads:
            level = u.level
            grade = HEAD_GRADE[level]
            hire = _random_tenure_hire(ctx, min_years={"section": 5, "department": 7, "center": 10}[level])
            gender = "M" if r.random() < 0.65 else "F"
            name, en, s_en = pick_name(r, gender, used)
            step = r.choice([1, 2, 3])
            _new_emp(
                ctx, name=name, en=en, surname_en=s_en, gender=gender,
                birth=hire - timedelta(days=int(r.uniform(28, 38) * 365.25)), unit=u.code, title=u.head_title,
                grade=grade, step=step, hire=hire, base=int(round(r.uniform(*grade_band(grade, step)), -2)),
                family=u.family or "gmo", head_level=level, marital="married" if r.random() < 0.85 else "single",
            )

    def make_staff(u, terminated: bool = False) -> None:
        _, male_ratio, grade_w, _, _ = FAMILIES[u.family]
        gender = "M" if r.random() < male_ratio else "F"
        grade = r.choices(list(grade_w), weights=list(grade_w.values()))[0]
        hire = _random_tenure_hire(ctx, min_years={1: 0, 2: 0, 3: 2, 4: 5}[grade])
        termination = None
        if terminated:
            termination = AS_OF - timedelta(days=r.randint(10, 640))
            hire = min(hire, termination - timedelta(days=r.randint(120, 1500)))
            while hire.weekday() != 0:
                hire -= timedelta(days=1)
            hire = max(hire, COMPANY["founded"])
        tenure = ((termination or AS_OF) - hire).days / 365.25
        step = 1 if tenure < 2 else (2 if tenure < 5 else 3)
        age_at_hire = r.uniform(22, 27) + (grade - 2) * 3
        name, en, s_en = pick_name(r, gender, used)
        age_now = age_at_hire + tenure
        e = _new_emp(
            ctx, name=name, en=en, surname_en=s_en, gender=gender,
            birth=hire - timedelta(days=int(age_at_hire * 365.25)), unit=u.code, title=staff_title(u.family, grade),
            grade=grade, step=step, hire=hire, base=int(round(r.uniform(*grade_band(grade, step)), -2)),
            family=u.family, marital="married" if age_now > 30 and r.random() < 0.6 else "single",
        )
        if terminated:
            e.termination = termination
            e.term_reason = r.choices(["resignation", "layoff", "contract_end"], weights=[88, 6, 6])[0]

    for u in UNITS:
        for _ in range(u.staff - fixture_staff_count.get(u.code, 0)):
            make_staff(u)
    staff_units = [u for u in UNITS if u.staff and u.family != "gmo"]
    for _ in range(24):
        make_staff(r.choices(staff_units, weights=[u.staff for u in staff_units])[0], terminated=True)

    _finish_people(ctx)


def _finish_people(ctx: Ctx) -> None:
    r = ctx.rng
    heads = {e.unit: e for e in ctx.emps if e.head_level}
    for code, e in heads.items():
        ctx.units[code]["head_emp_id"] = e.id
    seq: dict[int, int] = {}
    emails: set[str] = set()
    for e in sorted(ctx.emps, key=lambda x: (x.hire, x.id)):
        seq[e.hire.year] = seq.get(e.hire.year, 0) + 1
        e.emp_no = f"YC{e.hire.year % 100:02d}{seq[e.hire.year]:03d}"
    for e in ctx.emps:
        unit = UNIT_BY_CODE[e.unit]
        # 主管：往上找最近一個「主管不是自己」的單位主管
        code = unit.parent if e.head_level else unit.code
        while code and (code not in heads or heads[code].id == e.id):
            code = UNIT_BY_CODE[code].parent
        e.manager_id = heads[code].id if code else None
        site = ctx.units[e.unit]["site"]
        e.schedule = "MFG" if e.family == "mfg" and not e.head_level else "STD"
        e.remote_ok = FAMILIES.get(e.family, ("", 0, {}, None, False))[4] and not e.head_level
        e.remote_days_per_week = r.choices([0, 1, 2], weights=[45, 35, 20])[0] if e.remote_ok else 0
        e.voluntary_rate = r.choices([Fraction(0), Fraction(3, 100), Fraction(6, 100)], weights=[62, 8, 30])[0]
        letter, e.address = address(r)
        e.national_id = fake_national_id(r, letter, e.gender)
        e.mobile = mobile(r)
        e.ext = f"{2 if site == 'taipei' else 6}{r.randint(100, 999)}"
        local = f"{e.en}.{e.surname_en}".lower()
        n = 2
        while local in emails:
            local = f"{e.en}.{e.surname_en}{n}".lower()
            n += 1
        emails.add(local)
        e.email = f"{local}@{COMPANY['email_domain']}"
        if not e.salary_history:
            _salary_history(ctx, e)


def emit_people(ctx: Ctx) -> None:
    for u in ctx.units.values():
        ctx.add("org_units", dict(u))
    grade_id = {(row["grade"], row["step"]): row["id"] for row in ctx.rows["job_grades"]}
    password = os.environ["SEED_DEMO_PASSWORD"]
    pw_hash = hash_password(password)
    uid = 0
    for e in ctx.emps:
        unit_level = ctx.units[e.unit]
        status = "terminated" if e.termination and e.termination < AS_OF else "active"
        if any(lv.leave_type == "parental_daily" and lv.start.date() <= AS_OF <= lv.end.date() for lv in ctx.leaves if lv.emp_id == e.id):
            status = "parental_leave"
        ctx.add("employees", {
            "id": e.id, "emp_no": e.emp_no, "name": e.name, "english_name": f"{e.en} {e.surname_en}", "gender": e.gender,
            "birth_date": e.birth, "national_id": e.national_id, "email": e.email, "phone_ext": e.ext, "mobile": e.mobile,
            "address": e.address, "org_unit_id": unit_level["id"], "manager_id": e.manager_id, "title": e.title,
            "job_grade_id": grade_id[(e.grade, e.step)], "employment_type": "full_time",
            "schedule_id": SCHEDULES[e.schedule]["id"], "hire_date": e.hire, "seniority_start_date": e.hire,
            "probation_end_date": add_months(e.hire, PROBATION_MONTHS) - timedelta(days=1),
            "termination_date": e.termination, "termination_reason": e.term_reason, "status": status,
        })
        uid += 1
        ctx.add("users", {"id": uid, "employee_id": e.id, "username": e.email.split("@")[0], "password_hash": pw_hash,
                          "is_active": status != "terminated"})
        roles = [("employee", None)]
        if e.head_level:
            roles.append(("manager", None))
        roles += e.roles
        for role, scope in roles:
            ctx.add("user_roles", {"user_id": uid, "role": role, "scope_org_unit_id": ctx.units[scope]["id"] if scope else None})
        _dependents(ctx, e)
    uid += 1
    ctx.add("users", {"id": uid, "employee_id": None, "username": "sysadmin", "password_hash": pw_hash, "is_active": True})
    ctx.add("user_roles", {"user_id": uid, "role": "sysadmin", "scope_org_unit_id": None})


def _dependents(ctx: Ctx, e: Emp) -> None:
    r = ctx.rng
    used: set[str] = {e.name}
    if e.marital == "married":
        g = "F" if e.gender == "M" else "M"
        name, _, _ = pick_name(r, g, used)
        ctx.add("dependents", {
            "emp_id": e.id, "name": name, "relation": "spouse",
            "birth_date": e.birth + timedelta(days=r.randint(-1500, 1500)),
            "nhi_enrolled": r.random() < 0.3, "group_insurance_enrolled": r.random() < 0.4,
        })
        age = (AS_OF - e.birth).days / 365.25
        kids = 0 if age < 29 else r.choices([0, 1, 2, 3], weights=[25, 35, 32, 8])[0]
        for _ in range(kids):
            born = e.birth + timedelta(days=int(r.uniform(28, min(age, 42)) * 365.25))
            if born >= AS_OF:
                continue
            _child(ctx, e, born, used)
    if e.child_born:
        _child(ctx, e, e.child_born, used)


def _child(ctx: Ctx, e: Emp, born: date, used: set[str]) -> None:
    r = ctx.rng
    child_name = e.name[0] + r.choice(["子", "宥", "品", "芊", "沛", "睿", "恩", "妍"]) + r.choice(["晴", "安", "宸", "希", "睿", "彤", "恩", "澄"])
    used.add(child_name)
    ctx.add("dependents", {
        "emp_id": e.id, "name": child_name, "relation": "child", "birth_date": born,
        "nhi_enrolled": (AS_OF - born).days < 20 * 365 and r.random() < 0.9, "group_insurance_enrolled": r.random() < 0.3,
    })


def allowances_for(e: Emp) -> dict[str, int]:
    out = {"meal": PAYROLL["meal_allowance"]}
    if e.head_level:
        key = {"section": "section_head", "department": "dept_head", "center": "center_head", "company": "gm"}[e.head_level]
        out["position"] = PAYROLL["position_allowance"][key]
    prof = FAMILIES.get(e.family, ("", 0, {}, None, False))[3]
    if prof:
        out["professional"] = PAYROLL["professional_allowance"][prof]
    return out


def attendance_bonus_for(e: Emp) -> int:
    return 0 if e.head_level else PAYROLL["attendance_bonus"]
