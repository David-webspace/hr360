from datetime import date, datetime

from sqlalchemy import CheckConstraint, Date, DateTime, ForeignKey, Index, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, Timestamped


class CalendarDay(Base):
    __tablename__ = "calendar_days"

    day: Mapped[date] = mapped_column(Date, primary_key=True)
    # workday / rest_day / regular_leave / national_holiday / makeup_workday
    day_type: Mapped[str] = mapped_column(String(20))
    name: Mapped[str | None] = mapped_column(String(64))


class AttendanceRecord(Base):
    __tablename__ = "attendance_records"

    id: Mapped[int] = mapped_column(primary_key=True)
    emp_id: Mapped[int] = mapped_column(ForeignKey("employees.id"))
    work_date: Mapped[date] = mapped_column(Date)
    clock_in: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    clock_out: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(16))  # normal / late / early_leave / missing_punch / on_leave / remote
    note: Mapped[str | None] = mapped_column(String(128))

    __table_args__ = (UniqueConstraint("emp_id", "work_date"),)


class LeaveType(Base):
    __tablename__ = "leave_types"

    code: Mapped[str] = mapped_column(String(32), primary_key=True)
    name: Mapped[str] = mapped_column(String(32))
    pay_ratio: Mapped[float] = mapped_column(Numeric(3, 2))
    quota_rule_key: Mapped[str | None] = mapped_column(String(64))
    min_unit_hours: Mapped[float] = mapped_column(Numeric(4, 1))
    counts_calendar_days: Mapped[bool] = mapped_column(default=False)
    requires_attachment: Mapped[bool] = mapped_column(default=False)
    # 例：病假原因屬 S3，主管只看得到時數
    reason_sensitivity: Mapped[str] = mapped_column(String(2), default="S2")
    law_ref: Mapped[str] = mapped_column(Text)


class LeaveRequest(Base, Timestamped):
    __tablename__ = "leave_requests"

    id: Mapped[int] = mapped_column(primary_key=True)
    emp_id: Mapped[int] = mapped_column(ForeignKey("employees.id"), index=True)
    leave_type: Mapped[str] = mapped_column(ForeignKey("leave_types.code"))
    start_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    end_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    hours: Mapped[float] = mapped_column(Numeric(6, 1))
    reason: Mapped[str | None] = mapped_column(Text)
    deputy_emp_id: Mapped[int | None] = mapped_column(ForeignKey("employees.id"))
    status: Mapped[str] = mapped_column(String(16))  # draft / pending / approved / rejected / cancelled
    approver_id: Mapped[int | None] = mapped_column(ForeignKey("employees.id"))
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    decision_note: Mapped[str | None] = mapped_column(Text)
    created_via: Mapped[str] = mapped_column(String(8))  # chat / ui / mcp / seed

    __table_args__ = (
        CheckConstraint("end_at > start_at", name="time_order"),
        Index("ix_leave_requests_status_approver", "status", "approver_id"),
    )


class LeaveLedger(Base, Timestamped):
    __tablename__ = "leave_ledger"

    id: Mapped[int] = mapped_column(primary_key=True)
    emp_id: Mapped[int] = mapped_column(ForeignKey("employees.id"))
    leave_type: Mapped[str] = mapped_column(ForeignKey("leave_types.code"))
    # 特休：週年制為 "2026-03-15~2027-03-14"，曆年制為 "2026"
    period_key: Mapped[str] = mapped_column(String(32))
    delta_hours: Mapped[float] = mapped_column(Numeric(7, 1))
    kind: Mapped[str] = mapped_column(String(16))  # grant / hold / release / use / payout / carry_over / adjust
    ref_request_id: Mapped[int | None] = mapped_column(ForeignKey("leave_requests.id"))
    note: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))

    __table_args__ = (Index("ix_leave_ledger_emp_type_period", "emp_id", "leave_type", "period_key"),)


class OvertimeRecord(Base, Timestamped):
    __tablename__ = "overtime_records"

    id: Mapped[int] = mapped_column(primary_key=True)
    emp_id: Mapped[int] = mapped_column(ForeignKey("employees.id"), index=True)
    work_date: Mapped[date] = mapped_column(Date)
    day_type: Mapped[str] = mapped_column(String(20))  # weekday / rest_day / national_holiday / regular_leave
    hours: Mapped[float] = mapped_column(Numeric(4, 1))
    compensation: Mapped[str] = mapped_column(String(10))  # pay / comp_time
    reason: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(16))  # pending / approved / rejected
    approver_id: Mapped[int | None] = mapped_column(ForeignKey("employees.id"))
    comp_time_expires_on: Mapped[date | None] = mapped_column(Date)


class Payslip(Base, Timestamped):
    __tablename__ = "payslips"

    id: Mapped[int] = mapped_column(primary_key=True)
    emp_id: Mapped[int] = mapped_column(ForeignKey("employees.id"))
    pay_month: Mapped[str] = mapped_column(String(7))  # 2026-10
    gross: Mapped[int] = mapped_column(Integer)
    deductions: Mapped[int] = mapped_column(Integer)
    net: Mapped[int] = mapped_column(Integer)
    paid_on: Mapped[date] = mapped_column(Date)

    __table_args__ = (UniqueConstraint("emp_id", "pay_month"),)


class PayslipItem(Base):
    __tablename__ = "payslip_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    payslip_id: Mapped[int] = mapped_column(ForeignKey("payslips.id"), index=True)
    category: Mapped[str] = mapped_column(String(16))  # earning / deduction
    code: Mapped[str] = mapped_column(String(32))
    label: Mapped[str] = mapped_column(String(32))
    amount: Mapped[int] = mapped_column(Integer)
    calc_note: Mapped[dict | None] = mapped_column(JSONB)


class BenefitClaim(Base, Timestamped):
    __tablename__ = "benefit_claims"

    id: Mapped[int] = mapped_column(primary_key=True)
    emp_id: Mapped[int] = mapped_column(ForeignKey("employees.id"), index=True)
    benefit_code: Mapped[str] = mapped_column(String(32))  # travel / wedding / childbirth / funeral / birthday ...
    claim_year: Mapped[int] = mapped_column(Integer)
    amount: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(16))  # submitted / approved / paid / rejected
    event_date: Mapped[date | None] = mapped_column(Date)
    note: Mapped[str | None] = mapped_column(Text)
