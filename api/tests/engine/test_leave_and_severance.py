from datetime import date, datetime, time
from decimal import Decimal
from fractions import Fraction as F

import pytest

from app.engine.calendar_tw import WorkCalendar, round_up_to_unit, working_hours_between
from app.engine.leave import leave_pay_deduction, marriage_leave_days, maternity_leave
from app.engine.result import LaborLawViolation
from app.engine.severance import average_monthly_wage, notice_period_days, severance_pay

CAL = WorkCalendar()


def dt(y, m, d, h=0, mi=0):
    return datetime.combine(date(y, m, d), time(h, mi))


@pytest.mark.parametrize(
    "d, expected",
    [
        (date(2026, 2, 27), "national_holiday"),  # 228 逢週六，提前補假
        (date(2026, 2, 28), "rest_day"),
        (date(2026, 3, 1), "regular_leave"),
        (date(2026, 9, 28), "national_holiday"),  # 教師節 115 年起放假
        (date(2026, 11, 11), "workday"),
    ],
)
def test_day_type(d, expected):
    assert CAL.day_type(d) == expected


@pytest.mark.parametrize(
    "start, end, hours",
    [
        (dt(2026, 11, 11, 9), dt(2026, 11, 11, 18), 8),
        (dt(2026, 11, 11, 9), dt(2026, 11, 12, 12), 11),
        # 12/25 行憲紀念日、12/26-27 週末不計
        (dt(2026, 12, 24, 9), dt(2026, 12, 28, 18), 16),
        # 春節 9 連假（2/14～2/22）夾在中間
        (dt(2026, 2, 13, 9), dt(2026, 2, 23, 18), 16),
        # 10:30～15:00 扣午休 = 1.5 + 2
        (dt(2026, 11, 11, 10, 30), dt(2026, 11, 11, 15), F(7, 2)),
    ],
)
def test_working_hours(start, end, hours):
    assert working_hours_between(start, end, CAL) == F(hours)


def test_round_up_to_hour_unit():
    assert round_up_to_unit(F(7, 2), F(1)) == 4


@pytest.mark.parametrize(
    "code, hours, used, expected",
    [
        ("sick", 8, 0, 600),  # 150×8×0.5
        ("personal", 4, 0, 600),  # 150×4
        ("family_care", 3, 0, 450),
        ("annual", 8, 0, 0),
        ("menstrual", 8, 0, 600),
    ],
)
def test_leave_deduction(code, hours, used, expected):
    assert leave_pay_deduction(36000, code, F(hours), F(used)).value == Decimal(expected)


def test_sick_leave_over_30_days_rejected():
    with pytest.raises(LaborLawViolation, match="抵充"):
        leave_pay_deduction(36000, "sick", F(8), F(236))


@pytest.mark.parametrize(
    "reg, used, extended, days",
    [
        (date(2026, 10, 15), 0, False, 14),
        # 請假期間 2026-02-19～2026-06-01，新制前已結束
        (date(2026, 3, 1), 0, False, 8),
        # 期間至 2026-11-01，新制上路時已請 5 日 → 14
        (date(2026, 8, 1), 5, False, 14),
        # 新制上路前已請畢 8 日 → 不補 6 日
        (date(2026, 8, 1), 8, False, 8),
        # 雇主同意延長至 1 年 → 期間涵蓋 10/1
        (date(2026, 5, 1), 3, True, 14),
    ],
)
def test_marriage_leave_transition(reg, used, extended, days):
    assert marriage_leave_days(reg, used, extended).value == Decimal(days)


def test_maternity_pay_by_seniority():
    assert maternity_leave("birth", date(2025, 1, 1), date(2026, 5, 1)).basis["full_pay"] is True
    short = maternity_leave("birth", date(2026, 1, 1), date(2026, 5, 1))
    assert short.value == Decimal(56)
    assert short.basis["full_pay"] is False


def test_severance_prorated():
    # 6 年 8 個月 9 日 → 3 + 8/12×0.5 + 9/365×0.5 = 3.345662 個月 × 60,000 = 200,739.73 → 200,740
    r = severance_pay(date(2020, 3, 1), date(2026, 11, 10), 60000)
    assert r.value == Decimal(200740)


def test_severance_cap_6_months():
    assert severance_pay(date(2008, 1, 1), date(2026, 11, 10), 60000).value == Decimal(360000)


def test_average_wage():
    assert average_monthly_wage([60000] * 6, 184) == F(360000 * 30, 184)


@pytest.mark.parametrize(
    "start, notice, days",
    [
        (date(2026, 9, 1), date(2026, 11, 10), 0),
        (date(2026, 8, 10), date(2026, 11, 10), 10),
        (date(2026, 1, 10), date(2026, 11, 10), 10),
        (date(2024, 11, 10), date(2026, 11, 10), 20),
        (date(2021, 11, 10), date(2026, 11, 10), 30),
    ],
)
def test_notice_period(start, notice, days):
    assert notice_period_days(start, notice).value == Decimal(days)
