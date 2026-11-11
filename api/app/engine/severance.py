"""資遣費（勞工退休金條例 §12，新制）與預告期間（勞基法 §16）。"""

from datetime import date
from decimal import Decimal
from fractions import Fraction

from app.engine.dates import full_months_between, ymd_between
from app.engine.result import CalcResult, ceil_int, fmt
from app.engine.rules import rule


def average_monthly_wage(wages_last_6_months: list[int], total_days: int) -> Fraction:
    """平均工資：事由發生前 6 個月工資總額 ÷ 該期間總日數 × 30（勞基法第2條第4款）。"""
    return Fraction(sum(wages_last_6_months), total_days) * 30


def severance_pay(seniority_start: date, termination_date: date, avg_monthly_wage: Fraction | int) -> CalcResult:
    r = rule("severance_new", termination_date)
    p = r.params
    y, m, d = ymd_between(seniority_start, termination_date)
    base = Fraction(y) * p["months_per_year"] + Fraction(m, 12) * p["months_per_year"] + Fraction(d, 365) * p["months_per_year"]
    capped = min(base, Fraction(p["cap_months"]))
    amount = ceil_int(capped * Fraction(avg_monthly_wage))
    steps = [
        f"年資 {seniority_start} 至 {termination_date}：{y} 年 {m} 個月 {d} 日",
        f"基數 = {y}×0.5 + {m}/12×0.5 + {d}/365×0.5 = {fmt(base)} 個月",
    ]
    if capped < base:
        steps.append(f"超過上限 {p['cap_months']} 個月，以 {p['cap_months']} 個月計")
    steps.append(f"資遣費 = {fmt(capped)} × 平均工資 {fmt(Fraction(avg_monthly_wage))} = {amount:,} 元（無條件進位）")
    return CalcResult(
        value=Decimal(amount),
        unit="TWD",
        steps=steps,
        law_refs=[r.source],
        rule_version=r.version,
        basis={"system": "new_pension", "base_months": str(fmt(capped)), "rounding": "ceil_to_dollar"},
    )


def notice_period_days(seniority_start: date, notice_date: date) -> CalcResult:
    r = rule("notice_period", notice_date)
    months = full_months_between(seniority_start, notice_date)
    days = 0
    for threshold, d in r.params["tiers"]:
        if months >= threshold:
            days = d
    return CalcResult(
        value=Decimal(days),
        unit="day",
        steps=[f"至 {notice_date} 年資 {months // 12} 年 {months % 12} 個月 → 預告期間 {days} 日"],
        law_refs=[r.source],
        rule_version=r.version,
        basis={"seniority_months": months},
    )
