from datetime import date
from decimal import Decimal
from fractions import Fraction as F

import pytest

from app.engine.overtime import OvertimeEntry, monthly_overtime
from app.engine.result import LaborLawViolation

D = date(2026, 10, 14)


def one(day_type, hours, wage=36000):
    return monthly_overtime(wage, [OvertimeEntry(D, day_type, F(hours))])


@pytest.mark.parametrize(
    "day_type, hours, wage, expected",
    [
        # 臺北市勞動局範例：月薪 36,000、時薪 150
        ("rest_day", 1, 36000, 200),  # 150×4/3
        ("rest_day", 6, 36000, 1400),  # 150×4/3×2 + 150×5/3×4
        ("rest_day", 10, 36000, 2700),  # + 150×8/3×2
        ("weekday", 3, 36000, 650),  # 150×4/3×2 + 150×5/3×1
        ("weekday", 2, 45000, 500),  # 187.5×4/3×2
        ("national_holiday", 5, 36000, 1200),  # 8 小時內加發 1 日工資
        ("national_holiday", 10, 36000, 1600),  # 1200 + 150×4/3×2
        ("national_holiday", 12, 36000, 2100),  # 1200 + 400 + 150×5/3×2 (500)
        ("weekday", 1, 50000, 278),  # 208.33×4/3 = 277.78 → 無條件進位 278
    ],
)
def test_single_entry(day_type, hours, wage, expected):
    assert one(day_type, hours, wage).value == Decimal(expected)


@pytest.mark.parametrize("day_type, hours", [("weekday", 5), ("rest_day", 13), ("national_holiday", 12.5), ("weekday", 0)])
def test_violations_rejected(day_type, hours):
    with pytest.raises(LaborLawViolation):
        one(day_type, hours)


def test_regular_leave_warns_comp_day():
    r = one("regular_leave", 8)
    assert r.value == Decimal(1200)
    assert any("補假" in w for w in r.warnings)


def test_monthly_limit_and_total():
    entries = [OvertimeEntry(date(2026, 10, d), "weekday", F(2)) for d in range(5, 15)]
    entries += [OvertimeEntry(date(2026, 10, d), "rest_day", F(10)) for d in (3, 17, 24)]
    r = monthly_overtime(36000, entries)
    # 平日 400×10 + 休息日 2700×3
    assert r.value == Decimal(12100)
    assert r.basis["counted_extended_hours"] == "50"
    assert any("46" in w for w in r.warnings)


def test_holiday_within_8_not_counted_to_limit():
    r = monthly_overtime(36000, [OvertimeEntry(D, "national_holiday", F(8))])
    assert r.basis["counted_extended_hours"] == "0"
    assert r.warnings == []


def test_comp_time_excluded_from_pay():
    r = monthly_overtime(
        36000,
        [OvertimeEntry(D, "weekday", F(2)), OvertimeEntry(date(2026, 10, 17), "rest_day", F(4), "comp_time")],
    )
    assert r.value == Decimal(400)
    assert r.basis["comp_time_hours"] == "4"
