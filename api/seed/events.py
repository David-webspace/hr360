"""請假、加班、假勤帳本（特休／補休／生日假）、出勤打卡。"""

from collections import defaultdict
from datetime import date, datetime, time, timedelta
from fractions import Fraction

from app.engine.annual_leave import calendar_year_entitlement
from app.engine.calendar_tw import working_hours_between
from app.engine.dates import add_months
from app.engine.leave import BEREAVEMENT_DAYS, marriage_leave_days
from seed.context import AS_OF, DATA_START, GEN_END, SCHEDULES, TZ, Ctx, Emp, LeaveReq, OtRec, at

H8 = Fraction(8)
BRIDGES = {
    2025: [date(2025, 1, 2), date(2025, 1, 24), date(2025, 2, 3), date(2025, 4, 2), date(2025, 5, 2), date(2025, 10, 7),
           date(2025, 10, 8), date(2025, 10, 9), date(2025, 10, 23), date(2025, 12, 26)],
    2026: [date(2026, 1, 2), date(2026, 2, 12), date(2026, 2, 13), date(2026, 2, 23), date(2026, 4, 7), date(2026, 4, 8),
           date(2026, 6, 18), date(2026, 9, 24), date(2026, 9, 29), date(2026, 10, 8), date(2026, 10, 27), date(2026, 12, 24),
           date(2026, 12, 28), date(2026, 12, 29), date(2026, 12, 30), date(2026, 12, 31)],
}
CRUNCH = {(2025, 3), (2025, 9), (2026, 4), (2026, 10)}
RD_FAMILIES = {"fw", "sw", "hw", "qa"}


class Book:
    """單一員工某假別的帳本：依期間 FIFO 扣抵，不允許透支。"""

    def __init__(self) -> None:
        self.grants: list[tuple[date, str, Fraction, date]] = []  # (生效日, period, 時數, 失效日)
        self.used: dict[str, Fraction] = defaultdict(Fraction)

    def grant(self, d: date, period: str, hours: Fraction, expires: date) -> None:
        self.grants.append((d, period, Fraction(hours), expires))

    def balance(self, period: str) -> Fraction:
        return sum((g[2] for g in self.grants if g[1] == period), Fraction(0)) - self.used[period]

    def allocate(self, d: date, hours: Fraction) -> list[tuple[str, Fraction]] | None:
        valid = sorted({g[1]: g[3] for g in self.grants if g[0] <= d <= g[3]}.items(), key=lambda x: x[1])
        avail = [(p, self.balance(p)) for p, _ in valid]
        if sum((a for _, a in avail), Fraction(0)) < hours:
            return None
        out, need = [], hours
        for p, a in avail:
            take = min(a, need)
            if take > 0:
                out.append((p, take))
                self.used[p] += take
                need -= take
        return out


def blocks_of(e: Emp):
    return SCHEDULES[e.schedule]["blocks"]


def day_hours(ctx: Ctx, e: Emp, code: str, start: datetime, end: datetime) -> dict[date, Fraction]:
    out: dict[date, Fraction] = {}
    d = start.date()
    while d <= end.date():
        if code == "maternity":
            out[d] = H8
        else:
            s = max(start, at(d, time(0)))
            t = min(end, at(d, time(23, 59)))
            h = working_hours_between(s, t, ctx.cal, blocks_of(e))
            if h:
                out[d] = h
        d += timedelta(days=1)
    return out


class Planner:
    def __init__(self, ctx: Ctx) -> None:
        self.ctx = ctx
        self.occ: dict[int, dict[date, Fraction]] = defaultdict(lambda: defaultdict(Fraction))
        self.annual: dict[int, Book] = defaultdict(Book)
        self.comp: dict[int, Book] = defaultdict(Book)
        self.bday: dict[int, Book] = defaultdict(Book)
        self.ledger_allocs: dict[int, list[tuple[str, Fraction]]] = {}
        self.comp_payouts: dict[tuple[int, str], list[tuple[date, Fraction, str]]] = defaultdict(list)

    # ---- 請假 ----
    def free(self, e: Emp, dh: dict[date, Fraction]) -> bool:
        return all(e.employed_on(d) and DATA_START <= d <= GEN_END and self.occ[e.id][d] + h <= H8 for d, h in dh.items())

    def add_leave(self, e: Emp, code: str, start: datetime, end: datetime, status: str | None = None,
                  check: bool = True, reason: str | None = None) -> LeaveReq | None:
        ctx = self.ctx
        dh = day_hours(ctx, e, code, start, end)
        if not dh or (check and not self.free(e, dh)):
            return None
        hours = sum(dh.values(), Fraction(0))
        if status is None:
            status = "approved" if start.date() <= AS_OF or ctx.rng.random() < 0.55 else "pending"
        lead = 0 if code in ("sick", "menstrual", "bereavement") else ctx.rng.randint(2, 21)
        created = min(at(start.date() - timedelta(days=lead), time(8, 30 + ctx.rng.randint(0, 29))), at(AS_OF, time(8)))
        if code == "sick" and start.date() <= AS_OF:
            created = at(start.date(), time(8, ctx.rng.randint(0, 50)))
        decided = None if status == "pending" else min(created + timedelta(hours=ctx.rng.randint(1, 30)), at(AS_OF, time(9)))
        alloc = None
        if code in ("annual", "comp_time", "birthday") and status in ("approved", "pending"):
            book = {"annual": self.annual, "comp_time": self.comp, "birthday": self.bday}[code][e.id]
            alloc = book.allocate(start.date(), hours)
            if alloc is None:
                if e.fixture:
                    raise ValueError(f"fixture {e.name} {code} {start} 餘額不足")
                return None
        req = LeaveReq(len(ctx.leaves) + 1, e.id, code, start, end, hours, dh, status, created, decided,
                       e.manager_id, reason)
        ctx.leaves.append(req)
        if alloc:
            self.ledger_allocs[req.id] = alloc
        if status in ("approved", "pending"):
            for d, h in dh.items():
                self.occ[e.id][d] += h
        return req

    def full_days(self, e: Emp, first: date, n: int) -> tuple[datetime, datetime] | None:
        days, d = [], first
        while len(days) < n and d <= GEN_END:
            if self.ctx.cal.is_workday(d):
                days.append(d)
            d += timedelta(days=1)
        if len(days) < n:
            return None
        b = blocks_of(e)
        return at(days[0], b[0][0]), at(days[-1], b[-1][1])

    def half_day(self, e: Emp, d: date, morning: bool) -> tuple[datetime, datetime]:
        b = blocks_of(e)
        return (at(d, b[0][0]), at(d, b[0][1])) if morning else (at(d, b[1][0]), at(d, time(b[1][0].hour + 4, b[1][0].minute)))


def _grants(p: Planner, e: Emp, carry_2024: int) -> None:
    for y in (2025, 2026):
        jan1 = date(y, 1, 1)
        ent = calendar_year_entitlement(e.hire, y).value
        six = add_months(e.hire, 6)
        six_in_y = six.year == y
        regular = Fraction(int(ent)) - (24 if six_in_y else 0)
        if regular > 0 and e.employed_on(jan1):
            p.annual[e.id].grant(jan1, str(y), regular, date(y + 1, 12, 31))
        if six_in_y and e.employed_on(six):
            p.annual[e.id].grant(six, str(y), Fraction(24), date(y + 1, 12, 31))
        start = max(jan1, e.hire)
        if e.employed_on(start):
            p.bday[e.id].grant(start, str(y), H8, min(date(y, 12, 31), add_months(date(y, e.birth.month, 1), 2) - timedelta(days=1)))
    if carry_2024 and e.employed_on(date(2025, 1, 1)):
        p.annual[e.id].grant(date(2025, 1, 1), "2024", Fraction(carry_2024), date(2025, 12, 31))


def plan_fixture(p: Planner, e: Emp) -> None:
    f = e.fixture
    _grants(p, e, f.get("carry_2024", 0))
    for spec in f.get("leaves", []):
        code, s, t = spec[:3]
        status = spec[3] if len(spec) > 3 else None
        start = datetime.strptime(s, "%Y-%m-%d %H:%M").replace(tzinfo=TZ)
        end = datetime.strptime(t, "%Y-%m-%d %H:%M").replace(tzinfo=TZ)
        req = p.add_leave(e, code, start, end, status=status or "approved", check=False)
        if req is None:
            raise ValueError(f"fixture {e.name} {spec} 不是有效請假")
    for d, dt_, h, comp in f.get("overtime", []):
        p.ctx.overtime.append(OtRec(len(p.ctx.overtime) + 1, e.id, date.fromisoformat(d), dt_, Fraction(h), comp, "approved", e.manager_id))


def plan_random(p: Planner, e: Emp) -> None:
    r = p.ctx.rng
    carry = r.choice([0, 0, 8, 12, 16, 24, 32, 40]) if add_months(e.hire, 6) <= date(2024, 12, 31) else 0
    _grants(p, e, carry)
    age = (AS_OF - e.birth).days / 365.25

    for y in (2025, 2026):
        y_start, y_end = max(date(y, 1, 1), e.hire), min(date(y, 12, 31), e.termination or GEN_END)
        if y_start > y_end:
            continue

        def rand_day(lo: date = y_start, hi: date = y_end, months: list[int] | None = None) -> date | None:
            for _ in range(30):
                d = lo + timedelta(days=r.randint(0, max(0, (hi - lo).days)))
                if (months is None or d.month in months) and p.ctx.cal.is_workday(d):
                    return d
            return None

        # 人生事件
        if e.marital == "single" and 25 <= age <= 36 and r.random() < 0.03:
            reg = rand_day(hi=min(y_end, AS_OF - timedelta(days=20)))
            if reg:
                e.marital, e.marriage_registered = "married", reg
                days = int(marriage_leave_days(reg, 0).value)
                n = r.choice([days // 2, days])
                span = p.full_days(e, reg + timedelta(days=r.randint(0, 40)), n)
                if span:
                    p.add_leave(e, "marriage", *span)
        if e.marital == "married" and 26 <= age <= 40 and r.random() < 0.025 and not e.child_born:
            born = rand_day(hi=min(y_end, AS_OF - timedelta(days=15)))
            if born:
                e.child_born = born
                if e.gender == "F":
                    start = born - timedelta(days=r.randint(0, 7))
                    p.add_leave(e, "maternity", at(start, time(9)), at(start + timedelta(days=55), time(18)))
                    for k in (90, 45):
                        d = rand_day(lo=born - timedelta(days=k + 10), hi=born - timedelta(days=k))
                        if d:
                            p.add_leave(e, "prenatal", *p.half_day(e, d, True))
                else:
                    span = p.full_days(e, born, r.choice([5, 7]))
                    if span:
                        p.add_leave(e, "paternity", *span)
        if r.random() < 0.03:
            d = rand_day(hi=min(y_end, AS_OF))
            relation = r.choice(list(BEREAVEMENT_DAYS))
            span = p.full_days(e, d, BEREAVEMENT_DAYS[relation]) if d else None
            if span:
                p.add_leave(e, "bereavement", *span, reason=f"relation:{relation}")

        # 特休
        frac = r.uniform(0.6, 0.95) if y == 2025 else r.uniform(0.45, 0.8)
        target = sum((g[2] for g in p.annual[e.id].grants if g[1] in (str(y - 1), str(y))), Fraction(0)) * Fraction(frac).limit_denominator(100)
        used = Fraction(0)
        plans: list[tuple[date, int, str]] = []
        if r.random() < 0.6:
            d = rand_day(months=[7, 8])
            if d:
                plans.append((d, r.choice([3, 4, 5]), "full"))
        for b in BRIDGES[y]:
            if r.random() < 0.18:
                plans.append((b, 1, "full"))
        for _ in range(r.randint(2, 6)):
            d = rand_day()
            if d:
                plans.append((d, 1, "full"))
        for _ in range(r.randint(0, 3)):
            d = rand_day()
            if d:
                plans.append((d, 0, "am" if r.random() < 0.5 else "pm"))
        for d, n, kind in sorted(plans):
            if used >= target or not (y_start <= d <= y_end):
                continue
            if d > AS_OF and r.random() > 0.35:
                continue
            span = p.full_days(e, d, n) if kind == "full" else p.half_day(e, d, kind == "am")
            if span and (req := p.add_leave(e, "annual", *span)):
                used += req.hours

        # 病假、事假、家庭照顧假、生理假、生日假
        past_end = min(y_end, AS_OF)
        if y_start <= past_end:
            for _ in range(r.choices([0, 1, 2, 3, 4, 6], weights=[20, 25, 22, 15, 10, 8])[0]):
                d = rand_day(hi=past_end, months=[1, 2, 3, 11, 12] if r.random() < 0.6 else None)
                if d:
                    span = p.half_day(e, d, True) if r.random() < 0.3 else p.full_days(e, d, 1)
                    if span:
                        p.add_leave(e, "sick", *span)
            for _ in range(r.choices([0, 1, 2, 3], weights=[45, 30, 17, 8])[0]):
                d = rand_day(hi=past_end)
                if d:
                    span = p.half_day(e, d, r.random() < 0.5) if r.random() < 0.5 else p.full_days(e, d, 1)
                    if span:
                        p.add_leave(e, "personal", *span)
            if e.marital == "married" and r.random() < 0.3:
                for _ in range(r.randint(1, 3)):
                    d = rand_day(hi=past_end)
                    if d:
                        b = blocks_of(e)
                        p.add_leave(e, "family_care", at(d, b[1][0]), at(d, time(b[1][0].hour + r.choice([2, 3]), 0)))
            if e.gender == "F" and age < 50 and r.random() < 0.25:
                months = r.sample(range(1, 13), r.randint(3, 7))
                for m in months:
                    d = rand_day(hi=past_end, months=[m])
                    if d:
                        p.add_leave(e, "menstrual", *p.full_days(e, d, 1))
        if r.random() < 0.85:
            d = rand_day(months=[e.birth.month, e.birth.month % 12 + 1])
            if d and (d <= AS_OF or r.random() < 0.4):
                span = p.full_days(e, d, 1)
                if span:
                    p.add_leave(e, "birthday", *span)


def plan_overtime(p: Planner, e: Emp) -> None:
    if e.fixture or e.head_level:
        return
    r, ctx = p.ctx.rng, p.ctx
    month = date(max(e.hire, DATA_START).year, max(e.hire, DATA_START).month, 1)
    end = min(e.termination or AS_OF, AS_OF - timedelta(days=1))
    while month <= end:
        counted = Fraction(0)
        days = [month + timedelta(days=i) for i in range(31) if (month + timedelta(days=i)).month == month.month]
        days = [d for d in days if e.employed_on(d) and d <= end]
        work = [d for d in days if ctx.cal.is_workday(d) and p.occ[e.id][d] == 0]
        rest = [d for d in days if ctx.cal.day_type(d) == "rest_day" and p.occ[e.id][d] == 0]
        plan: list[tuple[date, str, int]] = []
        if e.family in RD_FAMILIES:
            if (month.year, month.month) in CRUNCH and r.random() < 0.55:
                plan += [(d, "weekday", r.choice([1, 2, 2, 3])) for d in r.sample(work, min(len(work), r.randint(4, 10)))]
                if rest and r.random() < 0.5:
                    plan.append((r.choice(rest), "rest_day", r.choice([4, 6, 8])))
            elif work and r.random() < 0.15:
                plan += [(d, "weekday", r.choice([1, 2])) for d in r.sample(work, min(len(work), r.randint(1, 3)))]
        elif e.family == "mfg" and rest and r.random() < 0.6:
            plan += [(d, "rest_day", 8) for d in r.sample(rest, min(len(rest), r.randint(1, 2)))]
        elif e.family == "fae" and rest and r.random() < 0.2:
            plan.append((r.choice(rest), "rest_day", 4))
        for d, kind, h in sorted(plan):
            c = Fraction(h)
            if counted + c > 40:
                continue
            counted += c
            comp = "comp_time" if r.random() < 0.35 else "pay"
            status = "approved" if d < AS_OF - timedelta(days=3) or r.random() < 0.5 else "pending"
            ctx.overtime.append(OtRec(len(ctx.overtime) + 1, e.id, d, kind, c, comp, status, e.manager_id))
        month = add_months(month, 1)


def plan_comp_time_usage(p: Planner) -> None:
    r, ctx = p.ctx.rng, p.ctx
    for ot in ctx.overtime:
        if ot.compensation == "comp_time" and ot.status == "approved":
            p.comp[ot.emp_id].grant(ot.work_date, ot.work_date.isoformat(), ot.hours, add_months(ot.work_date, 6) - timedelta(days=1))
    for e in ctx.emps:
        if e.fixture or not p.comp[e.id].grants:
            continue
        for g in sorted(p.comp[e.id].grants):
            if r.random() < 0.6:
                d = g[0] + timedelta(days=r.randint(7, 120))
                if d <= min(AS_OF, g[3]) and ctx.cal.is_workday(d):
                    span = p.full_days(e, d, 1) if g[2] >= 8 else p.half_day(e, d, r.random() < 0.5)
                    if span:
                        p.add_leave(e, "comp_time", *span)


def emit_leaves_and_ledger(p: Planner) -> None:
    ctx = p.ctx
    for lv in ctx.leaves:
        ctx.add("leave_requests", {
            "id": lv.id, "emp_id": lv.emp_id, "leave_type": lv.leave_type, "start_at": lv.start, "end_at": lv.end,
            "hours": float(lv.hours), "reason": lv.reason, "deputy_emp_id": None, "status": lv.status,
            "approver_id": lv.approver_id, "decided_at": lv.decided_at, "decision_note": None, "created_via": "seed",
            "created_at": lv.created_at,
        })
    for code, books in (("annual", p.annual), ("comp_time", p.comp), ("birthday", p.bday)):
        for emp_id, book in books.items():
            for d, period, hours, _ in book.grants:
                kind = "carry_over" if period == "2024" else "grant"
                note = {"annual": "曆年制特休給假" if kind == "grant" else "2024 年度未休遞延",
                        "comp_time": f"加班補休（{period} 加班）", "birthday": "生日假"}[code]
                ctx.add("leave_ledger", {"emp_id": emp_id, "leave_type": code, "period_key": period, "delta_hours": float(hours),
                                         "kind": kind, "ref_request_id": None, "note": note, "created_at": at(d, time(0, 5))})
    for lv in ctx.leaves:
        for period, h in p.ledger_allocs.get(lv.id, []):
            ctx.add("leave_ledger", {"emp_id": lv.emp_id, "leave_type": lv.leave_type, "period_key": period,
                                     "delta_hours": -float(h), "kind": "use" if lv.status == "approved" else "hold",
                                     "ref_request_id": lv.id, "note": None, "created_at": lv.decided_at or lv.created_at})


def settle_ledgers(p: Planner) -> dict[tuple[int, str], Fraction]:
    """年度終結與離職結算。回傳 {(emp_id, 'YYYY-MM'): 折發特休時數} 給薪資單用；補休到期折發另記在 comp_payouts。"""
    ctx = p.ctx
    payouts: dict[tuple[int, str], Fraction] = defaultdict(Fraction)
    for e in ctx.emps:
        book = p.annual[e.id]
        term = e.termination if e.termination and e.termination <= AS_OF else None
        if (not term or term >= date(2026, 1, 1)) and book.balance("2024") > 0 and e.employed_on(date(2026, 1, 1)):
            h = book.balance("2024")
            book.used["2024"] += h
            payouts[(e.id, "2026-01")] += h
            ctx.add("leave_ledger", {"emp_id": e.id, "leave_type": "annual", "period_key": "2024", "delta_hours": -float(h),
                                     "kind": "payout", "ref_request_id": None, "note": "遞延年度終結未休，折發工資",
                                     "created_at": at(date(2026, 1, 1), time(0, 10))})
        for g_date, period, hours, expires in sorted(p.comp[e.id].grants):
            left = p.comp[e.id].balance(period)
            when = term if term and term < expires else expires
            if left > 0 and when <= AS_OF:
                p.comp[e.id].used[period] += left
                ot = next(o for o in ctx.overtime if o.emp_id == e.id and o.work_date.isoformat() == period)
                p.comp_payouts[(e.id, when.strftime("%Y-%m"))].append((ot.work_date, left, ot.day_type))
                ctx.add("leave_ledger", {"emp_id": e.id, "leave_type": "comp_time", "period_key": period, "delta_hours": -float(left),
                                         "kind": "payout", "ref_request_id": None, "note": "補休期限屆滿未休，折發加班費",
                                         "created_at": at(when, time(23, 0))})
        if term:
            for period in {g[1] for g in book.grants}:
                h = book.balance(period)
                if h > 0:
                    book.used[period] += h
                    payouts[(e.id, term.strftime("%Y-%m"))] += h
                    ctx.add("leave_ledger", {"emp_id": e.id, "leave_type": "annual", "period_key": period, "delta_hours": -float(h),
                                             "kind": "payout", "ref_request_id": None, "note": "離職未休特休折發工資",
                                             "created_at": at(term, time(23, 0))})
    return payouts


def emit_overtime(ctx: Ctx) -> None:
    for o in ctx.overtime:
        ctx.add("overtime_records", {
            "id": o.id, "emp_id": o.emp_id, "work_date": o.work_date, "day_type": o.day_type, "hours": float(o.hours),
            "compensation": o.compensation, "reason": "專案交期" if o.day_type == "weekday" else "排定出勤",
            "status": o.status, "approver_id": o.approver_id,
            "comp_time_expires_on": add_months(o.work_date, 6) - timedelta(days=1) if o.compensation == "comp_time" else None,
            "created_at": at(o.work_date, time(9)),
        })


def emit_attendance(p: Planner) -> None:
    ctx, r = p.ctx, p.ctx.rng
    ot_by = {(o.emp_id, o.work_date): o for o in ctx.overtime if o.status == "approved"}
    leave_spans: dict[int, list[LeaveReq]] = defaultdict(list)
    for lv in ctx.leaves:
        if lv.status == "approved":
            leave_spans[lv.emp_id].append(lv)
    for e in ctx.emps:
        sched = SCHEDULES[e.schedule]
        b = sched["blocks"]
        d = max(e.hire, DATA_START)
        last = min(e.termination or AS_OF, AS_OF - timedelta(days=1))
        remote_weekdays = set(r.sample(range(5), e.remote_days_per_week))
        while d <= last:
            dtype = ctx.cal.day_type(d)
            ot = ot_by.get((e.id, d))
            if dtype != "workday" and not ot:
                d += timedelta(days=1)
                continue
            taken = p.occ[e.id][d]
            day_leaves = [lv for lv in leave_spans[e.id] if d in lv.day_hours]
            if dtype == "workday" and taken >= 8:
                ctx.add("attendance_records", {"emp_id": e.id, "work_date": d, "clock_in": None, "clock_out": None,
                                               "status": "on_leave", "note": day_leaves[0].leave_type if day_leaves else None})
                d += timedelta(days=1)
                continue
            if dtype == "workday":
                base_in = at(d, b[0][0]) - timedelta(minutes=60 if e.schedule == "STD" else 15)
                arrive = base_in + timedelta(minutes=max(0, int(r.gauss(55 if e.schedule == "STD" else 8, 25 if e.schedule == "STD" else 6))))
                if e.schedule == "STD" and r.random() < 0.02:
                    arrive = at(d, time(10, r.randint(1, 50)))
                for lv in day_leaves:
                    if lv.start.date() == d and lv.start.time() <= b[0][0] and lv.day_hours[d] < 8:
                        arrive = at(d, b[1][0]) - timedelta(minutes=r.randint(5, 20))
                leave = arrive + timedelta(hours=9, minutes=r.randint(0, 40))
                for lv in day_leaves:
                    if lv.end.date() == d and lv.end.time() < b[-1][1] and lv.day_hours[d] < 8 and lv.start.time() > b[0][0]:
                        leave = lv.start + timedelta(minutes=r.randint(0, 5))
                if ot:
                    leave += timedelta(hours=float(ot.hours))
                late = arrive.timetz() > sched["late_after"].replace(tzinfo=TZ) and taken == 0
                status = "late" if late else ("remote" if d.weekday() in remote_weekdays else "normal")
                clock_out = leave
                if r.random() < 0.004:
                    clock_out, status = None, "missing_punch"
            else:
                arrive = at(d, b[0][0]) - timedelta(minutes=r.randint(5, 20))
                clock_out = arrive + timedelta(hours=float(ot.hours) + (1 if ot.hours > 4 else 0), minutes=r.randint(5, 25))
                status, leave = "normal", None
            ctx.add("attendance_records", {"emp_id": e.id, "work_date": d, "clock_in": arrive, "clock_out": clock_out,
                                           "status": status, "note": f"{dtype} 加班" if ot else None})
            d += timedelta(days=1)
