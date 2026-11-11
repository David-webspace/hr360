from datetime import date
from decimal import Decimal

import pytest

from app.engine.annual_leave import anniversary_entitlement, calendar_year_entitlement


@pytest.mark.parametrize(
    "start, on, days, period_start",
    [
        # 未滿 6 個月：2026-03-15 + 6 個月 = 2026-09-15
        (date(2026, 3, 15), date(2026, 9, 14), 0, None),
        (date(2026, 3, 15), date(2026, 9, 15), 3, "2026-09-15"),
        # 年資 2 年 7 個月 → 10 日，特休年度 2026-03-15 起
        (date(2024, 3, 15), date(2026, 11, 10), 10, "2026-03-15"),
        # 差 1 天滿 2 年 → 仍是 7 日
        (date(2024, 11, 11), date(2026, 11, 10), 7, "2025-11-11"),
        (date(2021, 11, 10), date(2026, 11, 10), 15, "2026-11-10"),
        # 滿 10 年 → 15 + 1 = 16
        (date(2016, 1, 1), date(2026, 11, 10), 16, "2026-01-01"),
        # 滿 24 年 → 16 + 14 = 30；36 年仍封頂 30
        (date(2002, 6, 1), date(2026, 6, 1), 30, "2026-06-01"),
        (date(1990, 1, 1), date(2026, 11, 10), 30, "2026-01-01"),
        # 2/29 到職：平年週年日以 2/28 計
        (date(2024, 2, 29), date(2025, 2, 28), 7, "2025-02-28"),
    ],
)
def test_anniversary(start, on, days, period_start):
    r = anniversary_entitlement(start, on)
    assert r.value == Decimal(days)
    assert r.basis.get("period_start") == period_start
    assert r.basis["system"] == "anniversary"


@pytest.mark.parametrize(
    "start, year, hours",
    [
        # 勞動部範例：2017-07-01 到職，2018 年 = 3 + 7×184/365 = 6.5288 日 = 52.23h → 53h
        (date(2017, 7, 1), 2018, 53),
        # 2019 年 = 7×181/365 + 10×184/366（2020 為閏年）= 8.4985 日 = 67.99h → 68h
        (date(2017, 7, 1), 2019, 68),
        (date(2017, 7, 1), 2017, 0),
        # 2026-03-01 到職：滿 6 個月 2026-09-01 給 3 日 = 24h
        (date(2026, 3, 1), 2026, 24),
        # 2027 年：滿 1 年期間 2027-03-01～2028-02-29 共 366 日，落在 2027 有 306 日 → 7×306/366×8 = 46.82 → 47h
        (date(2026, 3, 1), 2027, 47),
    ],
)
def test_calendar_year(start, year, hours):
    r = calendar_year_entitlement(start, year)
    assert r.value == Decimal(hours)
    assert r.unit == "hour"
    assert r.basis["system"] == "calendar_year"


def test_result_carries_law_and_version():
    r = anniversary_entitlement(date(2024, 3, 15), date(2026, 11, 10))
    assert "勞動基準法第38條" in r.law_refs
    assert r.rule_version == "annual_leave@2017-01-01"
    assert any("10 日" in s for s in r.steps)
