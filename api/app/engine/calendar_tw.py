"""工作日判斷與請假時數切分。

民間企業依勞基法第37條放假；國定假日逢例假／休息日的補休日由勞資協商，
本公司採行政院人事行政總處辦公日曆表的補假日（2/27、4/3、4/6、10/9、10/26 等）。
"""

from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from fractions import Fraction
from math import ceil

# 115年政府行政機關辦公日曆表（人事行政總處 114.06.13 公告），全年放假 120 日、無補行上班日
HOLIDAYS_2026: dict[date, str] = {
    date(2026, 1, 1): "開國紀念日",
    date(2026, 2, 16): "除夕",
    date(2026, 2, 17): "春節",
    date(2026, 2, 18): "春節",
    date(2026, 2, 19): "春節",
    date(2026, 2, 20): "小年夜（2/15 逢星期日）補假",
    date(2026, 2, 27): "和平紀念日（2/28 逢星期六）補假",
    date(2026, 4, 3): "兒童節（4/4 逢星期六）補假",
    date(2026, 4, 6): "清明節（4/5 逢星期日）補假",
    date(2026, 5, 1): "勞動節",
    date(2026, 6, 19): "端午節",
    date(2026, 9, 25): "中秋節",
    date(2026, 9, 28): "孔子誕辰紀念日／教師節",
    date(2026, 10, 9): "國慶日（10/10 逢星期六）補假",
    date(2026, 10, 26): "臺灣光復暨金門古寧頭大捷紀念日（10/25 逢星期日）補假",
    date(2026, 12, 25): "行憲紀念日",
}

# 114年政府行政機關辦公日曆表（含 114.06.13 修正新增教師節、光復節、行憲紀念日），2/8（六）補行上班
HOLIDAYS_2025: dict[date, str] = {
    date(2025, 1, 1): "開國紀念日",
    date(2025, 1, 27): "除夕前一日（調整放假，2/8 補行上班）",
    date(2025, 1, 28): "除夕",
    date(2025, 1, 29): "春節",
    date(2025, 1, 30): "春節",
    date(2025, 1, 31): "春節",
    date(2025, 2, 28): "和平紀念日",
    date(2025, 4, 3): "兒童節（與清明節同日，於前一日放假）",
    date(2025, 4, 4): "民族掃墓節（清明節）",
    date(2025, 5, 1): "勞動節",
    date(2025, 5, 30): "端午節（5/31 逢星期六）補假",
    date(2025, 9, 29): "孔子誕辰紀念日／教師節（9/28 逢星期日）補假",
    date(2025, 10, 6): "中秋節",
    date(2025, 10, 10): "國慶日",
    date(2025, 10, 24): "臺灣光復暨金門古寧頭大捷紀念日（10/25 逢星期六）補假",
    date(2025, 12, 25): "行憲紀念日",
}
MAKEUP_WORKDAYS = frozenset({date(2025, 2, 8)})

DEFAULT_BLOCKS = ((time(9), time(12)), (time(13), time(18)))


@dataclass(frozen=True)
class WorkCalendar:
    holidays: dict[date, str] = field(default_factory=lambda: {**HOLIDAYS_2025, **HOLIDAYS_2026})
    makeup_workdays: frozenset[date] = MAKEUP_WORKDAYS
    rest_day_weekday: int = 5  # 星期六
    regular_leave_weekday: int = 6  # 星期日

    def day_type(self, d: date) -> str:
        if d in self.makeup_workdays:
            return "workday"
        if d in self.holidays:
            return "national_holiday"
        if d.weekday() == self.regular_leave_weekday:
            return "regular_leave"
        if d.weekday() == self.rest_day_weekday:
            return "rest_day"
        return "workday"

    def is_workday(self, d: date) -> bool:
        return self.day_type(d) == "workday"


def working_hours_between(
    start: datetime, end: datetime, cal: WorkCalendar, blocks: tuple[tuple[time, time], ...] = DEFAULT_BLOCKS
) -> Fraction:
    """start～end 與工作時段重疊的時數，只算工作日（例假、休息日、國定假日不計）。"""
    total = Fraction(0)
    d = start.date()
    while d <= end.date():
        if cal.is_workday(d):
            for b_start, b_end in blocks:
                s = max(start, datetime.combine(d, b_start, start.tzinfo))
                e = min(end, datetime.combine(d, b_end, start.tzinfo))
                if e > s:
                    total += Fraction(int((e - s).total_seconds()), 3600)
        d += timedelta(days=1)
    return total


def round_up_to_unit(hours: Fraction, unit: Fraction) -> Fraction:
    return Fraction(ceil(hours / unit)) * unit


def calendar_days_between(start: date, end: date) -> int:
    return (end - start).days + 1
