import calendar
from datetime import date


def add_months(d: date, months: int) -> date:
    """到職日 1/31 加 1 個月得 2/28（或 2/29）；到職日 2/29 滿 1 年在平年為 2/28。"""
    y, m = divmod(d.month - 1 + months, 12)
    year, month = d.year + y, m + 1
    return date(year, month, min(d.day, calendar.monthrange(year, month)[1]))


def full_months_between(start: date, end: date) -> int:
    """start 起算到 end 為止滿幾個月（end 當天剛好是週月日時算滿）。"""
    months = (end.year - start.year) * 12 + (end.month - start.month)
    if add_months(start, months) > end:
        months -= 1
    return months


def ymd_between(start: date, end: date) -> tuple[int, int, int]:
    months = full_months_between(start, end)
    days = (end - add_months(start, months)).days
    return months // 12, months % 12, days
