import random
from dataclasses import dataclass, field
from datetime import date, datetime, time
from fractions import Fraction
from zoneinfo import ZoneInfo

from app.engine.calendar_tw import WorkCalendar

TZ = ZoneInfo("Asia/Taipei")
SEED = 20261110
DATA_START = date(2025, 1, 1)
AS_OF = date(2026, 11, 10)
GEN_END = date(2026, 12, 31)

SCHEDULES = {
    "STD": {"id": 1, "name": "標準彈性班", "blocks": ((time(9), time(12)), (time(13), time(18))),
            "flex": ("08:00", "10:00"), "late_after": time(10, 0)},
    "MFG": {"id": 2, "name": "製造日班", "blocks": ((time(8), time(12)), (time(13), time(17))),
            "flex": ("08:00", "08:00"), "late_after": time(8, 0)},
}


@dataclass
class Emp:
    id: int
    emp_no: str
    name: str
    en: str
    surname_en: str
    gender: str
    birth: date
    unit: str
    title: str
    grade: int
    step: int
    hire: date
    base: int
    family: str
    head_level: str | None = None  # section / department / center / company
    fixture: dict | None = None
    termination: date | None = None
    term_reason: str | None = None
    manager_id: int | None = None
    marital: str = "single"
    marriage_registered: date | None = None
    child_born: date | None = None
    roles: list[tuple[str, str | None]] = field(default_factory=list)
    schedule: str = "STD"
    remote_ok: bool = False
    remote_days_per_week: int = 0
    voluntary_rate: Fraction = Fraction(0)
    national_id: str = ""
    address: str = ""
    mobile: str = ""
    email: str = ""
    ext: str = ""
    salary_history: list[tuple[date, int]] = field(default_factory=list)  # (生效日, 本薪)
    perf: dict[str, str] = field(default_factory=dict)

    def employed_on(self, d: date) -> bool:
        return self.hire <= d and (self.termination is None or d <= self.termination)

    def base_on(self, d: date) -> int:
        return max((h for h in self.salary_history if h[0] <= d), key=lambda h: h[0], default=self.salary_history[0])[1]


@dataclass
class LeaveReq:
    id: int
    emp_id: int
    leave_type: str
    start: datetime
    end: datetime
    hours: Fraction
    day_hours: dict[date, Fraction]
    status: str
    created_at: datetime
    decided_at: datetime | None
    approver_id: int | None
    reason: str | None = None


@dataclass
class OtRec:
    id: int
    emp_id: int
    work_date: date
    day_type: str
    hours: Fraction
    compensation: str
    status: str
    approver_id: int | None


@dataclass
class Ctx:
    rng: random.Random = field(default_factory=lambda: random.Random(SEED))
    cal: WorkCalendar = field(default_factory=WorkCalendar)
    units: dict[str, dict] = field(default_factory=dict)  # code -> row
    emps: list[Emp] = field(default_factory=list)
    leaves: list[LeaveReq] = field(default_factory=list)
    overtime: list[OtRec] = field(default_factory=list)
    rows: dict[str, list[dict]] = field(default_factory=dict)

    def add(self, table: str, row: dict) -> None:
        self.rows.setdefault(table, []).append(row)

    def emp(self, emp_id: int) -> Emp:
        return self.emps[emp_id - 1]


def at(d: date, t: time) -> datetime:
    return datetime.combine(d, t, TZ)
