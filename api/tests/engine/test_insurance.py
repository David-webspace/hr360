from datetime import date
from decimal import Decimal
from fractions import Fraction as F

import pytest

from app.engine.calendar_tw import WorkCalendar
from app.engine.insurance import attendance_bonus_after_leave, bonus_supplementary_premium, monthly_premiums

D26 = date(2026, 6, 1)


@pytest.mark.parametrize(
    "wage, deps, labor, health",
    [
        # 健保署負擔金額表：29,500 級本人 458；勞保局：29,500 × 12.5% × 20% = 737.5 → 738
        (29500, 0, 738, 458),
        # 45,800 級：勞保 1,145、健保 710（健保署表）
        (45800, 0, 1145, 710),
        # 60,000 → 勞保封頂 45,800；健保 60,800 × 5.17% × 30% = 943.0 → 943，含 2 眷 ×3
        (60000, 2, 1145, 2829),
        # 眷屬 4 人只算 3 人
        (60000, 4, 1145, 3772),
        # 2025 年第 1 級 28,590：勞保 714.75 → 715
        (28000, 0, 715, 443),
    ],
)
def test_employee_premiums(wage, deps, labor, health):
    on = date(2025, 6, 1) if wage == 28000 else D26
    r = monthly_premiums(wage, on, deps)
    assert r.basis["employee"]["labor"] == labor
    assert r.basis["employee"]["health"] == health


def test_pension_and_employer_share():
    r = monthly_premiums(52000, D26, 0, F(6, 100))
    # 52,000 → 勞退級距 53,000：雇主 6% = 3,180、自提 6% = 3,180
    assert r.basis["pension_contribution_wage"] == 53000
    assert r.basis["employer"]["pension"] == 3180
    assert r.basis["employee"]["pension_voluntary"] == 3180
    # 健保雇主 = 53,000 × 5.17% × 60% × 1.56 = 2,564.73 → 2,565
    assert r.basis["employer"]["health"] == 2565


def test_pension_cap():
    assert monthly_premiums(200000, D26).basis["pension_contribution_wage"] == 150000


@pytest.mark.parametrize(
    "insured, before, now, expected",
    [
        (60800, 0, 100000, 0),  # 4 倍 = 243,200 未超過
        (60800, 0, 300000, 1198),  # (300,000 − 243,200) × 2.11% = 1,198.48 → 1,198
        (60800, 250000, 50000, 1055),  # 已超過，本次全額 × 2.11%
        (60800, 200000, 100000, 1198),  # 累計 300,000，本次計費 56,800
    ],
)
def test_bonus_supplementary(insured, before, now, expected):
    assert bonus_supplementary_premium(insured, before, now, D26).value == Decimal(expected)


def test_attendance_bonus_mol_example():
    # 勞動部 Q&A：全勤 3,000，病假 1 日扣 100
    assert attendance_bonus_after_leave(3000, F(1)).value == Decimal(2900)
    assert attendance_bonus_after_leave(2000, F(1, 2)).value == Decimal(1967)  # 33.33 → 33


def test_2025_calendar():
    cal = WorkCalendar()
    assert cal.day_type(date(2025, 2, 8)) == "workday"
    assert cal.day_type(date(2025, 1, 27)) == "national_holiday"
    assert cal.day_type(date(2025, 9, 29)) == "national_holiday"
