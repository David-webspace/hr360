from dataclasses import dataclass, field
from decimal import ROUND_CEILING, ROUND_HALF_UP, Decimal
from fractions import Fraction


@dataclass(frozen=True)
class CalcResult:
    """Engine 唯一的輸出格式。Agent 只能轉述這裡的 value / steps / basis，不能自行換算。"""

    value: Decimal
    unit: str
    steps: list[str]
    law_refs: list[str]
    rule_version: str
    basis: dict = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)


class LaborLawViolation(ValueError):
    """輸入本身違反強制規定（例如平日加班超過 4 小時），不計算、直接拒絕。"""


def to_money(x: Fraction) -> Decimal:
    return (Decimal(x.numerator) / Decimal(x.denominator)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def ceil_int(x: Fraction) -> int:
    # 法定給付是「最低標準」，四捨五入可能少給 0.x 元，一律無條件進位
    return int((Decimal(x.numerator) / Decimal(x.denominator)).to_integral_value(rounding=ROUND_CEILING))


def fmt(x: Fraction | int) -> str:
    x = Fraction(x)
    if x.denominator == 1:
        return f"{x.numerator:,}"
    return f"{to_money(x):,}"
