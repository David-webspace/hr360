"""法定假別（勞工請假規則、性別平等工作法、勞基法 §50）。

這裡只放法定最低標準；公司優於法令的規定（例如特休多給、病假全薪天數）由 company_settings 疊加。
"""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from fractions import Fraction
from typing import Literal

from app.engine.dates import add_months, full_months_between
from app.engine.overtime import hourly_wage
from app.engine.result import CalcResult, LaborLawViolation, fmt
from app.engine.rules import rule


@dataclass(frozen=True)
class LeaveTypeDef:
    code: str
    name: str
    pay_ratio: Fraction
    annual_quota_hours: int | None
    min_unit_hours: Fraction
    counts_calendar_days: bool
    reason_sensitivity: str
    law_ref: str


F = Fraction

LEAVE_TYPES: dict[str, LeaveTypeDef] = {
    t.code: t
    for t in [
        LeaveTypeDef("annual", "特別休假", F(1), None, F(1), False, "S2", "勞動基準法第38條"),
        LeaveTypeDef("personal", "事假", F(0), 14 * 8, F(1), False, "S2", "勞工請假規則第7條"),
        LeaveTypeDef("family_care", "家庭照顧假", F(0), 7 * 8, F(1), False, "S2", "性別平等工作法第20條；勞工請假規則第7條第2項（併入事假，得以小時請）"),
        LeaveTypeDef("sick", "普通傷病假（未住院）", F(1, 2), 30 * 8, F(1), False, "S3", "勞工請假規則第4條"),
        LeaveTypeDef("sick_hospital", "普通傷病假（住院）", F(1, 2), None, F(1), False, "S3", "勞工請假規則第4條（二年內合計不超過一年）"),
        LeaveTypeDef("menstrual", "生理假", F(1, 2), 12 * 8, F(1), False, "S3", "性別平等工作法第14條（每月1日，全年3日不併入病假）"),
        LeaveTypeDef("marriage", "婚假", F(1), None, F(1), False, "S2", "勞工請假規則第2條"),
        LeaveTypeDef("bereavement", "喪假", F(1), None, F(1), False, "S2", "勞工請假規則第3條"),
        LeaveTypeDef("maternity", "產假", F(1), None, F(8), True, "S3", "勞動基準法第50條；性別平等工作法第15條"),
        LeaveTypeDef("prenatal", "產檢假", F(1), 7 * 8, F(1), False, "S3", "性別平等工作法第15條第4項"),
        LeaveTypeDef("paternity", "陪產檢及陪產假", F(1), 7 * 8, F(1), False, "S2", "性別平等工作法第15條第5項"),
        LeaveTypeDef("occupational", "公傷病假", F(1), None, F(1), False, "S3", "勞動基準法第59條；勞工請假規則第6條"),
        LeaveTypeDef("official", "公假", F(1), None, F(1), False, "S2", "勞工請假規則第8條"),
        LeaveTypeDef("comp_time", "加班補休", F(1), None, F(1), False, "S2", "勞動基準法第32條之1"),
        LeaveTypeDef("parental_daily", "育嬰留職停薪（以日申請）", F(0), 30 * 8, F(8), False, "S2", "育嬰留職停薪實施辦法（115年1月1日起可以日申請，合計30日）"),
    ]
}

BEREAVEMENT_DAYS = {
    "parent": 8, "adoptive_parent": 8, "step_parent": 8, "spouse": 8,
    "grandparent": 6, "child": 6, "spouse_parent": 6, "spouse_adoptive_parent": 6, "spouse_step_parent": 6,
    "great_grandparent": 3, "sibling": 3, "spouse_grandparent": 3,
}


def leave_pay_deduction(monthly_regular_wage: int, code: str, hours: Fraction, used_hours_this_year: Fraction = F(0)) -> CalcResult:
    lt = LEAVE_TYPES[code]
    if lt.annual_quota_hours is not None and used_hours_this_year + hours > lt.annual_quota_hours:
        raise LaborLawViolation(
            f"{lt.name}本年已用 {fmt(used_hours_this_year)} 小時，再請 {fmt(hours)} 小時將超過上限 {lt.annual_quota_hours} 小時"
            + ("，超過部分須以事假或特別休假抵充" if code == "sick" else "")
        )
    hw = hourly_wage(monthly_regular_wage)
    deduction = hw * hours * (1 - lt.pay_ratio)
    amount = int(deduction)  # 扣款無條件捨去，不多扣勞工
    return CalcResult(
        value=Decimal(amount),
        unit="TWD",
        steps=[
            f"平日每小時工資額 = {monthly_regular_wage:,} ÷ 30 ÷ 8 = {fmt(hw)} 元",
            f"{lt.name} {fmt(hours)} 小時，工資給付比例 {fmt(lt.pay_ratio)}",
            f"應扣 = {fmt(hw)} × {fmt(hours)} × (1 − {fmt(lt.pay_ratio)}) = {fmt(deduction)} → {amount:,} 元（無條件捨去）",
        ],
        law_refs=[lt.law_ref],
        rule_version=f"leave.{code}",
        basis={"pay_ratio": str(lt.pay_ratio), "used_hours_before": str(fmt(used_hours_this_year)), "rounding": "floor_deduction"},
    )


def marriage_leave_days(registration_date: date, used_days_before_change: int = 0, extended_window: bool = False) -> CalcResult:
    """婚假：115/10/1 起 14 日。新制上路時仍在請假期間內、且 8 日未請完者，適用 14 日。"""
    new = rule("marriage_leave", date(2026, 10, 1))
    old = rule("marriage_leave", date(2026, 9, 30))
    window_start = date.fromordinal(registration_date.toordinal() - new.params["window_before_days"])
    window_end = add_months(registration_date, 12 if extended_window else new.params["window_months"])
    steps = [f"結婚登記日 {registration_date}，請假期間 {window_start} 至 {window_end}" + ("（經雇主同意延長至 1 年）" if extended_window else "")]
    if window_end < new.effective_from:
        applied, reason = old, "請假期間在新制施行（2026-10-01）前已結束，適用舊制"
    elif used_days_before_change >= old.params["days"]:
        applied, reason = old, f"新制施行前已請畢 {old.params['days']} 日，不得補請新增日數"
    else:
        applied, reason = new, "新制施行時仍在請假期間內且尚未請畢，適用新制"
    steps.append(f"{reason} → {applied.params['days']} 日，工資照給")
    return CalcResult(
        value=Decimal(applied.params["days"]),
        unit="day",
        steps=steps,
        law_refs=[applied.source],
        rule_version=applied.version,
        basis={"window_start": window_start.isoformat(), "window_end": window_end.isoformat(), "excludes_non_workdays": True},
    )


MaternityCase = Literal["birth", "miscarriage_3m_plus", "miscarriage_2_3m", "miscarriage_under_2m"]
MATERNITY_DAYS = {"birth": 56, "miscarriage_3m_plus": 28, "miscarriage_2_3m": 7, "miscarriage_under_2m": 5}


def maternity_leave(case: MaternityCase, seniority_start: date, leave_start: date) -> CalcResult:
    days = MATERNITY_DAYS[case]
    months = full_months_between(seniority_start, leave_start)
    full_pay = months >= 6
    pay_note = "受僱滿 6 個月，工資照給" if full_pay else "受僱未滿 6 個月，工資減半發給"
    if case in ("miscarriage_2_3m", "miscarriage_under_2m"):
        pay_note = "依性別平等工作法第15條給予產假，工資依公司規定（法未強制給薪）"
    return CalcResult(
        value=Decimal(days),
        unit="calendar_day",
        steps=[f"{case} → 產假 {days} 日（連續計算，含例假日）", f"至 {leave_start} 年資 {months} 個月：{pay_note}"],
        law_refs=["勞動基準法第50條", "性別平等工作法第15條"],
        rule_version="maternity@2023",
        basis={"counts_calendar_days": True, "full_pay": full_pay},
    )


def bereavement_days(relation: str) -> int:
    return BEREAVEMENT_DAYS[relation]
