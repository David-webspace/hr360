from datetime import date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, Index, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, Timestamped


class OrgUnit(Base):
    __tablename__ = "org_units"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(32), unique=True)
    name: Mapped[str] = mapped_column(String(64))
    level: Mapped[str] = mapped_column(String(16))  # company / center / department / section
    parent_id: Mapped[int | None] = mapped_column(ForeignKey("org_units.id"))
    # 物化路徑 "/1/3/7/"：主管查「所有下層單位」用前綴比對，一個查詢完成
    path: Mapped[str] = mapped_column(String(255))
    head_emp_id: Mapped[int | None] = mapped_column(ForeignKey("employees.id", use_alter=True))
    site: Mapped[str] = mapped_column(String(16))  # taipei / hsinchu

    __table_args__ = (Index("ix_org_units_path_prefix", "path", postgresql_ops={"path": "text_pattern_ops"}),)


class JobGrade(Base):
    __tablename__ = "job_grades"

    id: Mapped[int] = mapped_column(primary_key=True)
    grade: Mapped[int] = mapped_column(Integer)  # 職等 1-6
    step: Mapped[int] = mapped_column(Integer)  # 職級 1-3
    title_band: Mapped[str] = mapped_column(String(32))
    salary_min: Mapped[int] = mapped_column(Integer)
    salary_max: Mapped[int] = mapped_column(Integer)

    __table_args__ = (UniqueConstraint("grade", "step"),)


class WorkSchedule(Base):
    __tablename__ = "work_schedules"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(32), unique=True)
    name: Mapped[str] = mapped_column(String(64))
    daily_hours: Mapped[int] = mapped_column(Integer, default=8)
    # [["09:00","12:00"],["13:00","18:00"]]，請假時數依此切
    work_blocks: Mapped[list] = mapped_column(JSONB)
    flex_start_from: Mapped[str] = mapped_column(String(5))
    flex_start_to: Mapped[str] = mapped_column(String(5))
    rest_day_weekday: Mapped[int] = mapped_column(Integer, default=5)  # Mon=0
    regular_leave_weekday: Mapped[int] = mapped_column(Integer, default=6)


class Employee(Base, Timestamped):
    __tablename__ = "employees"

    id: Mapped[int] = mapped_column(primary_key=True)
    emp_no: Mapped[str] = mapped_column(String(16), unique=True)
    name: Mapped[str] = mapped_column(String(32))
    english_name: Mapped[str | None] = mapped_column(String(64))
    gender: Mapped[str] = mapped_column(String(1))
    birth_date: Mapped[date] = mapped_column(Date)
    national_id: Mapped[str] = mapped_column(String(10))  # 格式正確、檢查碼刻意錯誤，不會對到真人
    email: Mapped[str] = mapped_column(String(128), unique=True)
    phone_ext: Mapped[str | None] = mapped_column(String(8))
    mobile: Mapped[str | None] = mapped_column(String(16))
    address: Mapped[str | None] = mapped_column(Text)
    org_unit_id: Mapped[int] = mapped_column(ForeignKey("org_units.id"))
    manager_id: Mapped[int | None] = mapped_column(ForeignKey("employees.id"))
    title: Mapped[str] = mapped_column(String(64))
    job_grade_id: Mapped[int] = mapped_column(ForeignKey("job_grades.id"))
    employment_type: Mapped[str] = mapped_column(String(16))  # full_time / part_time / contract
    schedule_id: Mapped[int] = mapped_column(ForeignKey("work_schedules.id"))
    hire_date: Mapped[date] = mapped_column(Date)
    seniority_start_date: Mapped[date] = mapped_column(Date)  # 併計年資時與 hire_date 不同
    probation_end_date: Mapped[date | None] = mapped_column(Date)
    termination_date: Mapped[date | None] = mapped_column(Date)
    termination_reason: Mapped[str | None] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(String(16))  # active / parental_leave / terminated


class EmploymentHistory(Base):
    __tablename__ = "employment_history"

    id: Mapped[int] = mapped_column(primary_key=True)
    emp_id: Mapped[int] = mapped_column(ForeignKey("employees.id"), index=True)
    effective_date: Mapped[date] = mapped_column(Date)
    event: Mapped[str] = mapped_column(String(24))  # hire / transfer / promotion / salary_adjust / terminate
    detail: Mapped[dict] = mapped_column(JSONB)


class Dependent(Base):
    __tablename__ = "dependents"

    id: Mapped[int] = mapped_column(primary_key=True)
    emp_id: Mapped[int] = mapped_column(ForeignKey("employees.id"), index=True)
    name: Mapped[str] = mapped_column(String(32))
    relation: Mapped[str] = mapped_column(String(16))  # spouse / child / parent
    birth_date: Mapped[date] = mapped_column(Date)
    nhi_enrolled: Mapped[bool]
    group_insurance_enrolled: Mapped[bool]


class User(Base, Timestamped):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    employee_id: Mapped[int | None] = mapped_column(ForeignKey("employees.id"), unique=True)
    username: Mapped[str] = mapped_column(String(64), unique=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(default=True)


class UserRole(Base):
    __tablename__ = "user_roles"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    role: Mapped[str] = mapped_column(String(16))  # employee / manager / hrbp / payroll / sysadmin
    scope_org_unit_id: Mapped[int | None] = mapped_column(ForeignKey("org_units.id"))

    __table_args__ = (UniqueConstraint("user_id", "role", "scope_org_unit_id"),)


class ApiToken(Base, Timestamped):
    __tablename__ = "api_tokens"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    name: Mapped[str] = mapped_column(String(64))
    token_hash: Mapped[str] = mapped_column(String(128), unique=True)
    scope: Mapped[str] = mapped_column(String(16))  # read / action
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked: Mapped[bool] = mapped_column(default=False)


class CompanySetting(Base):
    __tablename__ = "company_settings"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[dict] = mapped_column(JSONB)
    description: Mapped[str] = mapped_column(Text)


class LawRule(Base):
    __tablename__ = "law_rules"

    id: Mapped[int] = mapped_column(primary_key=True)
    rule_key: Mapped[str] = mapped_column(String(64))
    effective_from: Mapped[date] = mapped_column(Date)
    params: Mapped[dict] = mapped_column(JSONB)
    source_ref: Mapped[str] = mapped_column(Text)

    __table_args__ = (UniqueConstraint("rule_key", "effective_from"),)


class SalaryProfile(Base):
    __tablename__ = "salary_profiles"

    id: Mapped[int] = mapped_column(primary_key=True)
    emp_id: Mapped[int] = mapped_column(ForeignKey("employees.id"), index=True)
    effective_from: Mapped[date] = mapped_column(Date)
    base_monthly: Mapped[int] = mapped_column(Integer)
    # 經常性給與：{"meal": 3000, "position": 5000, ...}，加班費時薪基礎要納入
    regular_allowances: Mapped[dict] = mapped_column(JSONB)
    attendance_bonus: Mapped[int] = mapped_column(Integer, default=0)
    bank_account_masked: Mapped[str | None] = mapped_column(String(32))

    __table_args__ = (UniqueConstraint("emp_id", "effective_from"),)


class InsuranceEnrollment(Base):
    __tablename__ = "insurance_enrollments"

    id: Mapped[int] = mapped_column(primary_key=True)
    emp_id: Mapped[int] = mapped_column(ForeignKey("employees.id"), index=True)
    effective_from: Mapped[date] = mapped_column(Date)
    labor_insured_salary: Mapped[int] = mapped_column(Integer)
    health_insured_salary: Mapped[int] = mapped_column(Integer)
    pension_contribution_wage: Mapped[int] = mapped_column(Integer)
    pension_voluntary_rate: Mapped[float] = mapped_column(Numeric(4, 2), default=0)
    nhi_dependents: Mapped[int] = mapped_column(Integer, default=0)
