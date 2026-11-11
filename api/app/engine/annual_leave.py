"""特別休假（勞基法 §38）：週年制與曆年制。

曆年制換算採勞動部「比例計算」方式：每個服務年度的應給日數，依該服務年度落在各曆年的日數比例分配；
滿 6 個月的 3 日在取得當年一次給足。換算後以小時計，未滿 1 小時以 1 小時計（不得低於法定）。
"""

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from fractions import Fraction

from app.engine.dates import add_months, full_months_between
from app.engine.result import CalcResult, ceil_int, fmt
from app.engine.rules import rule

HOURS_PER_DAY = 8


@dataclass(frozen=True)
class ServicePeriod:
    """一個特休年度：[start, end) 期間可休 days 日。"""

    start: date
    end: date
    days: int
    seniority_label: str


def _days_for_months(months: int, params: dict) -> int:
    days = 0
    for threshold, d in params["tiers"]:
        if months >= threshold:
            days = d
    if months >= 120:
        extra_years = months // 12 - 10
        days = min(params["cap"], 16 + extra_years * params["per_year_after_10"])
    return days


def service_periods(seniority_start: date, until: date) -> list[ServicePeriod]:
    """列出 until 之前已開始的所有特休年度（週年制的原始切法）。"""
    params = rule("annual_leave", until).params
    periods: list[ServicePeriod] = []
    six = add_months(seniority_start, 6)
    if six <= until:
        periods.append(ServicePeriod(six, add_months(seniority_start, 12), 3, "滿6個月"))
    year = 1
    while (start := add_months(seniority_start, 12 * year)) <= until:
        periods.append(
            ServicePeriod(start, add_months(seniority_start, 12 * (year + 1)), _days_for_months(12 * year, params), f"滿{year}年")
        )
        year += 1
    return periods


def anniversary_entitlement(seniority_start: date, on: date) -> CalcResult:
    r = rule("annual_leave", on)
    months = full_months_between(seniority_start, on)
    current = next((p for p in reversed(service_periods(seniority_start, on)) if p.start <= on < p.end), None)
    if current is None:
        return CalcResult(
            value=Decimal(0),
            unit="day",
            steps=[f"年資起算日 {seniority_start}，至 {on} 未滿 6 個月，尚無特休", f"滿 6 個月之日：{add_months(seniority_start, 6)}"],
            law_refs=[r.source],
            rule_version=r.version,
            basis={"system": "anniversary", "seniority_months": months},
        )
    return CalcResult(
        value=Decimal(current.days),
        unit="day",
        steps=[
            f"年資起算日 {seniority_start}，至 {on} 年資 {months // 12} 年 {months % 12} 個月",
            f"適用級距：{current.seniority_label} → {current.days} 日",
            f"本特休年度期間：{current.start} 至 {current.end - timedelta(days=1)}",
        ],
        law_refs=[r.source],
        rule_version=r.version,
        basis={
            "system": "anniversary",
            "period_start": current.start.isoformat(),
            "period_end": (current.end - timedelta(days=1)).isoformat(),
            "seniority_months": months,
        },
    )


def calendar_year_entitlement(seniority_start: date, year: int) -> CalcResult:
    r = rule("annual_leave", date(year, 12, 31))
    y_start, y_end = date(year, 1, 1), date(year + 1, 1, 1)
    total = Fraction(0)
    steps: list[str] = []
    for p in service_periods(seniority_start, date(year, 12, 31)):
        if p.seniority_label == "滿6個月":
            if p.start.year == year:
                total += p.days
                steps.append(f"{p.start} {p.seniority_label}：{p.days} 日於當年一次給足")
            continue
        overlap = (min(p.end, y_end) - max(p.start, y_start)).days
        if overlap <= 0:
            continue
        length = (p.end - p.start).days
        portion = Fraction(p.days * overlap, length)
        total += portion
        steps.append(
            f"{p.seniority_label}（{p.start}～{p.end - timedelta(days=1)}，{p.days} 日）"
            f"落在 {year} 年 {overlap}/{length} 日 → {p.days}×{overlap}/{length} = {fmt(portion)} 日"
        )
    hours = ceil_int(total * HOURS_PER_DAY)
    if not steps:
        steps.append(f"年資起算日 {seniority_start}，{year} 年內未滿 6 個月，尚無特休")
    else:
        steps.append(f"合計 {fmt(total)} 日 × 8 = {fmt(total * HOURS_PER_DAY)} 小時，未滿 1 小時以 1 小時計 → {hours} 小時")
    return CalcResult(
        value=Decimal(hours),
        unit="hour",
        steps=steps,
        law_refs=[r.source, "勞動部特別休假曆年制比例計算說明"],
        rule_version=r.version,
        basis={"system": "calendar_year", "year": year, "rounding": "ceil_to_hour"},
    )
