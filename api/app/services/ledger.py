"""假勤帳本：餘額＝帳本加總，扣抵依失效日先到先扣（FIFO）。"""

from dataclasses import dataclass
from datetime import date, timedelta
from fractions import Fraction

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.engine.dates import add_months

LEDGER_TYPES = ("annual", "comp_time", "birthday")


@dataclass
class Period:
    key: str
    granted: Fraction
    used: Fraction
    held: Fraction
    paid_out: Fraction
    valid_from: date
    expires: date

    @property
    def remaining(self) -> Fraction:
        """已核准扣除後剩餘（不含待簽核預扣）。"""
        return self.granted - self.used - self.paid_out

    @property
    def available(self) -> Fraction:
        return self.remaining - self.held


def _expiry(db: Session, emp_id: int, leave_type: str, key: str, birth: date) -> tuple[date, date]:
    if leave_type == "annual":
        y = int(key)
        return date(y, 1, 1), date(y + 1, 12, 31)
    if leave_type == "comp_time":
        d = date.fromisoformat(key)
        exp = db.execute(text("SELECT comp_time_expires_on FROM overtime_records WHERE emp_id=:e AND work_date=:d"),
                         {"e": emp_id, "d": d}).scalar()
        return d, exp or add_months(d, 6) - timedelta(days=1)
    y = int(key)
    start = date(y, birth.month, 1)
    return start, min(date(y, 12, 31), add_months(start, 2) - timedelta(days=1))


def periods(db: Session, emp_id: int, leave_type: str, birth: date, on: date) -> list[Period]:
    """on：只計入生效日在 on 之前（含）的給假，例如 11-11 才滿 6 個月的特休，11-10 查詢時不算。"""
    rows = db.execute(text("""
        SELECT period_key,
               SUM(delta_hours) FILTER (WHERE kind IN ('grant', 'carry_over', 'adjust')
                                      AND (created_at AT TIME ZONE 'Asia/Taipei')::date <= :on) AS granted,
               -SUM(delta_hours) FILTER (WHERE kind = 'use') AS used,
               -SUM(delta_hours) FILTER (WHERE kind IN ('hold', 'release')) AS held,
               -SUM(delta_hours) FILTER (WHERE kind = 'payout') AS paid_out
        FROM leave_ledger WHERE emp_id = :e AND leave_type = :t GROUP BY period_key
    """), {"e": emp_id, "t": leave_type, "on": on}).mappings().all()
    out = []
    for r in rows:
        f = lambda v: Fraction(str(v or 0))  # noqa: E731
        vf, exp = _expiry(db, emp_id, leave_type, r["period_key"], birth)
        out.append(Period(r["period_key"], f(r["granted"]), f(r["used"]), f(r["held"]), f(r["paid_out"]), vf, exp))
    return sorted(out, key=lambda p: (p.expires, p.key))


def allocate(ps: list[Period], on: date, hours: Fraction) -> list[tuple[str, Fraction]] | None:
    valid = [p for p in ps if p.valid_from <= on <= p.expires and p.available > 0]
    if sum((p.available for p in valid), Fraction(0)) < hours:
        return None
    out, need = [], hours
    for p in valid:
        take = min(p.available, need)
        out.append((p.key, take))
        need -= take
        if need == 0:
            break
    return out


def write(db: Session, emp_id: int, leave_type: str, rows: list[tuple[str, Fraction]], kind: str, request_id: int,
          sign: int, user_id: int | None, note: str | None = None) -> None:
    for key, h in rows:
        db.execute(text("""
            INSERT INTO leave_ledger (emp_id, leave_type, period_key, delta_hours, kind, ref_request_id, note, created_by)
            VALUES (:e, :t, :k, :h, :kind, :r, :note, :u)
        """), {"e": emp_id, "t": leave_type, "k": key, "h": float(h) * sign, "kind": kind, "r": request_id,
               "note": note, "u": user_id})


def holds_of(db: Session, request_id: int) -> list[tuple[str, Fraction]]:
    rows = db.execute(text("""
        SELECT period_key, -SUM(delta_hours) FROM leave_ledger
        WHERE ref_request_id = :r AND kind IN ('hold', 'release') GROUP BY period_key HAVING SUM(delta_hours) <> 0
    """), {"r": request_id}).all()
    return [(k, Fraction(str(h))) for k, h in rows]
