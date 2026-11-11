"""相對日期由程式換算後放進提示，模型不必自己推星期幾。"""

from datetime import date

from app.agent.prompts import date_table


def test_date_table_resolves_relative_days():
    t = date_table(date(2026, 11, 11))
    assert "今天 2026-11-11（週三）" in t and "明天 2026-11-12（週四）" in t
    assert "下週：週一 2026-11-16" in t


def test_date_table_on_sunday_counts_next_monday_as_tomorrow():
    assert "下週：週一 2026-11-16" in date_table(date(2026, 11, 15))
