"""加班費（勞基法 §24、§39、§40），適用月薪制勞工。

時薪基礎 = （本薪 + 經常性給與）÷ 30 ÷ 8。各段金額以分數精確計算，月合計無條件進位到元。
"""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from fractions import Fraction
from typing import Literal

from app.engine.result import CalcResult, LaborLawViolation, ceil_int, fmt
from app.engine.rules import rule

DayType = Literal["weekday", "rest_day", "national_holiday", "regular_leave"]

DAY_LABEL = {"weekday": "平日", "rest_day": "休息日", "national_holiday": "國定假日", "regular_leave": "例假"}


@dataclass(frozen=True)
class OvertimeEntry:
    work_date: date
    day_type: DayType
    hours: Fraction  # 平日填「延長」的時數；其他日別填當日出勤總時數
    compensation: Literal["pay", "comp_time"] = "pay"


def hourly_wage(monthly_regular_wage: int) -> Fraction:
    return Fraction(monthly_regular_wage, 30 * 8)


def _segments(hours: Fraction, table: list[tuple[int, int, Fraction]]) -> list[tuple[Fraction, Fraction]]:
    out = []
    for lo, hi, mult in table:
        h = min(max(hours - lo, 0), hi - lo)
        if h > 0:
            out.append((Fraction(h), mult))
    return out


def _entry_pay(e: OvertimeEntry, hw: Fraction, p: dict) -> tuple[Fraction, list[str], list[str]]:
    label = f"{e.work_date} {DAY_LABEL[e.day_type]} {fmt(e.hours)} 小時"
    warnings: list[str] = []
    if e.hours <= 0:
        raise LaborLawViolation(f"{label}：時數必須大於 0")
    if e.day_type == "weekday":
        if e.hours > p["weekday_max_extended"]:
            raise LaborLawViolation(f"{label}：平日延長工時連同正常工時不得超過 12 小時（延長至多 4 小時）")
        segs = _segments(e.hours, p["weekday"])
        pay = sum((hw * h * m for h, m in segs), Fraction(0))
        parts = [f"{fmt(h)}h×{fmt(hw)}×{fmt(m)}" for h, m in segs]
        return pay, [f"{label}：{' + '.join(parts)} = {fmt(pay)} 元"], warnings
    if e.hours > p["daily_max_total"]:
        raise LaborLawViolation(f"{label}：單日出勤不得超過 12 小時")
    if e.day_type == "rest_day":
        segs = _segments(e.hours, p["rest_day"])
        pay = sum((hw * h * m for h, m in segs), Fraction(0))
        parts = [f"{fmt(h)}h×{fmt(hw)}×{fmt(m)}" for h, m in segs]
        return pay, [f"{label}：{' + '.join(parts)} = {fmt(pay)} 元"], warnings
    # 國定假日／例假：8 小時內加發 1 日工資（不論實際時數），超過 8 小時依延長工時計
    day_wage = hw * 8
    segs = _segments(e.hours, p["holiday_beyond_8"])
    pay = day_wage + sum((hw * h * m for h, m in segs), Fraction(0))
    parts = [f"8 小時內加發 1 日工資 {fmt(day_wage)}"] + [f"{fmt(h)}h×{fmt(hw)}×{fmt(m)}" for h, m in segs]
    if e.day_type == "regular_leave":
        warnings.append(f"{e.work_date} 為例假：僅限天災、事變或突發事件出勤，且事後應補假 1 日（勞基法第40條）")
    return pay, [f"{label}：{' + '.join(parts)} = {fmt(pay)} 元"], warnings


def counted_extended_hours(e: OvertimeEntry) -> Fraction:
    """計入每月延長工時上限的時數：平日延長、休息日全部、國定假日／例假超過 8 小時部分。"""
    if e.day_type in ("weekday", "rest_day"):
        return e.hours
    return max(e.hours - 8, Fraction(0))


def monthly_overtime(monthly_regular_wage: int, entries: list[OvertimeEntry], agreed_limit: bool = False) -> CalcResult:
    on = max(e.work_date for e in entries)
    r = rule("overtime", on)
    p = r.params
    hw = hourly_wage(monthly_regular_wage)
    steps = [f"平日每小時工資額 = {monthly_regular_wage:,} ÷ 30 ÷ 8 = {fmt(hw)} 元"]
    warnings: list[str] = []
    total_pay = Fraction(0)
    comp_hours = Fraction(0)
    for e in sorted(entries, key=lambda x: x.work_date):
        pay, s, w = _entry_pay(e, hw, p)
        warnings += w
        if e.compensation == "comp_time":
            comp_hours += e.hours
            steps.append(f"{s[0]}（選擇補休 {fmt(e.hours)} 小時，不發加班費；期限屆滿未休依此金額發給）")
        else:
            total_pay += pay
            steps += s
    counted = sum((counted_extended_hours(e) for e in entries), Fraction(0))
    limit = p["monthly_limit_agreed"] if agreed_limit else p["monthly_limit"]
    if counted > limit:
        warnings.append(f"本月延長工時 {fmt(counted)} 小時，超過每月上限 {limit} 小時（勞基法第32條）")
    amount = ceil_int(total_pay)
    steps.append(f"加班費合計 {fmt(total_pay)} 元，無條件進位 → {amount:,} 元")
    return CalcResult(
        value=Decimal(amount),
        unit="TWD",
        steps=steps,
        law_refs=["勞動基準法第24條", "勞動基準法第32條", "勞動基準法第32條之1", "勞動基準法第39條"],
        rule_version=r.version,
        basis={
            "hourly_base": str(fmt(hw)),
            "wage_base": "本薪＋經常性給與",
            "comp_time_hours": str(fmt(comp_hours)),
            "counted_extended_hours": str(fmt(counted)),
            "monthly_limit": limit,
            "rounding": "ceil_to_dollar",
        },
        warnings=warnings,
    )
