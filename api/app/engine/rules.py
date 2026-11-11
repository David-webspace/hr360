"""依生效日版本化的法定參數。法規會改，計算結果必須能回答「依哪一版規定」。

出處見 docs/sources.md；每次改這裡都要同步更新出處與測試。
"""

from dataclasses import dataclass
from datetime import date
from fractions import Fraction


@dataclass(frozen=True)
class RuleVersion:
    key: str
    effective_from: date
    params: dict
    source: str

    @property
    def version(self) -> str:
        return f"{self.key}@{self.effective_from.isoformat()}"


F = Fraction

RULES: dict[str, list[RuleVersion]] = {
    "annual_leave": [
        RuleVersion(
            "annual_leave",
            date(2017, 1, 1),
            {
                # (滿幾個月, 天數)；滿 10 年後每年加 1 日至 30 日
                "tiers": [(6, 3), (12, 7), (24, 10), (36, 14), (60, 15), (120, 16)],
                "per_year_after_10": 1,
                "cap": 30,
            },
            "勞動基準法第38條",
        )
    ],
    "overtime": [
        RuleVersion(
            "overtime",
            date(2018, 3, 1),
            {
                # (該段起始小時, 該段結束小時, 加給倍數)，倍數為「另再加給」的部分
                "weekday": [(0, 2, F(4, 3)), (2, 4, F(5, 3))],
                "rest_day": [(0, 2, F(4, 3)), (2, 8, F(5, 3)), (8, 12, F(8, 3))],
                # 休假日（國定假日、特休日）8 小時內加發 1 日工資，超過部分依延長工時計
                "holiday_beyond_8": [(8, 10, F(4, 3)), (10, 12, F(5, 3))],
                "weekday_max_extended": 4,
                "daily_max_total": 12,
                "monthly_limit": 46,
                "monthly_limit_agreed": 54,
                "quarterly_limit_agreed": 138,
            },
            "勞動基準法第24條、第32條、第36條第3項、第39條；臺北市勞動局休息日第9至12小時計算說明",
        )
    ],
    "marriage_leave": [
        RuleVersion("marriage_leave", date(1985, 3, 20), {"days": 8}, "勞工請假規則第2條（舊）"),
        RuleVersion(
            "marriage_leave",
            date(2026, 10, 1),
            {"days": 14, "window_before_days": 10, "window_months": 3},
            "勞工請假規則第2條（115年9月30日修正，115年10月1日施行）",
        ),
    ],
    "minimum_wage": [
        RuleVersion("minimum_wage", date(2025, 1, 1), {"monthly": 28590, "hourly": 190}, "勞動部最低工資公告"),
        RuleVersion("minimum_wage", date(2026, 1, 1), {"monthly": 29500, "hourly": 196}, "勞動部最低工資公告（114年10月21日發布）"),
    ],
    "severance_new": [
        RuleVersion(
            "severance_new",
            date(2005, 7, 1),
            {"months_per_year": F(1, 2), "cap_months": 6},
            "勞工退休金條例第12條",
        )
    ],
    "notice_period": [
        RuleVersion(
            "notice_period",
            date(1984, 7, 30),
            {"tiers": [(3, 10), (12, 20), (36, 30)]},  # (滿幾個月, 預告天數)
            "勞動基準法第16條",
        )
    ],
}


def rule(key: str, on: date) -> RuleVersion:
    candidates = [r for r in RULES[key] if r.effective_from <= on]
    if not candidates:
        raise LookupError(f"{key} 在 {on} 尚無生效規定")
    return max(candidates, key=lambda r: r.effective_from)
