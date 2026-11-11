"""勞保（含就保）、職災保險、健保、勞退提繳、二代健保補充保費（獎金）。

投保級距：取「大於等於月薪資」的最低一級，超過最高級以最高級計。保費各方分擔額四捨五入到元
（與勞保局、健保署負擔金額表一致：29,500 級勞保自付 738、健保自付 458）。
"""

from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from fractions import Fraction

from app.engine.result import CalcResult, fmt
from app.engine.rules import RULES, RuleVersion, rule

_COMMON = [30300, 31800, 33300, 34800, 36300, 38200, 40100, 42000, 43900, 45800]
_ABOVE_LABOR = [48200, 50600, 53000, 55400, 57800, 60800, 63800, 66800, 69800, 72800]
_PENSION_HIGH = [76500, 80200, 83900, 87600, 92100, 96600, 101100, 105600, 110100, 115500, 120900, 126300,
                 131700, 137100, 142500, 147900, 150000]
_HEALTH_HIGH = _PENSION_HIGH + [156400, 162800, 169200, 175600, 182000, 189500, 197000, 204500, 212000, 219500,
                                228200, 236900, 245600, 254300, 263000, 273000, 283000, 293000, 303000, 313000]


def _tables(first: list[int]) -> dict:
    return {
        "labor_levels": first + _COMMON,
        "occupational_levels": first + _COMMON + _ABOVE_LABOR,
        "health_levels": first + _COMMON + _ABOVE_LABOR + _HEALTH_HIGH,
        "pension_levels": first + _COMMON + _ABOVE_LABOR + _PENSION_HIGH,
    }


_BASE = {
    "labor_rate": Fraction(125, 1000),  # 普通事故 11.5% + 就業保險 1%
    "labor_shares": {"employee": Fraction(2, 10), "employer": Fraction(7, 10)},
    "health_rate": Fraction(517, 10000),
    "health_shares": {"employee": Fraction(3, 10), "employer": Fraction(6, 10)},
    "health_avg_dependents": Fraction(56, 100),
    "health_max_charged_dependents": 3,
    "pension_employer_rate": Fraction(6, 100),
    "pension_voluntary_max": Fraction(6, 100),
    "supplementary_rate": Fraction(211, 10000),
    "bonus_free_multiple": 4,
}

RULES["insurance"] = [
    RuleVersion("insurance", date(2025, 1, 1), {**_BASE, **_tables([28590, 28800])},
                "勞保局 114 年投保薪資分級表；健保署 114 年投保金額分級表；勞工退休金月提繳分級表"),
    RuleVersion("insurance", date(2026, 1, 1), {**_BASE, **_tables([29500])},
                "勞保局 115 年投保薪資分級表（第1級 29,500、最高 45,800，費率 12.5% 含就保 1%）；"
                "健保署 115.1.1 生效負擔金額表（費率 5.17%、平均眷口數 0.56、最高 313,000）；"
                "勞工退休金月提繳分級表 115.1.1 生效；健保署二代健保補充保險費 Q&A（2.11%、獎金逾投保金額 4 倍部分）"),
]


def _round(x: Fraction) -> int:
    return int((Decimal(x.numerator) / Decimal(x.denominator)).quantize(Decimal(1), rounding=ROUND_HALF_UP))


def bracket(levels: list[int], wage: int) -> int:
    return next((lv for lv in levels if lv >= wage), levels[-1])


def monthly_premiums(
    monthly_wage: int, on: date, nhi_dependents: int = 0, voluntary_pension_rate: Fraction = Fraction(0),
    occupational_rate: Fraction = Fraction(0),
) -> CalcResult:
    r = rule("insurance", on)
    p = r.params
    labor_salary = bracket(p["labor_levels"], monthly_wage)
    occ_salary = bracket(p["occupational_levels"], monthly_wage)
    health_amount = bracket(p["health_levels"], monthly_wage)
    pension_wage = bracket(p["pension_levels"], monthly_wage)
    if voluntary_pension_rate > p["pension_voluntary_max"]:
        raise ValueError("勞退自提率不得超過 6%")

    labor_emp = _round(labor_salary * p["labor_rate"] * p["labor_shares"]["employee"])
    labor_er = _round(labor_salary * p["labor_rate"] * p["labor_shares"]["employer"])
    health_per_person = _round(health_amount * p["health_rate"] * p["health_shares"]["employee"])
    charged = min(nhi_dependents, p["health_max_charged_dependents"])
    health_emp = health_per_person * (1 + charged)
    health_er = _round(health_amount * p["health_rate"] * p["health_shares"]["employer"] * (1 + p["health_avg_dependents"]))
    occ_er = _round(occ_salary * occupational_rate)
    pension_er = _round(pension_wage * p["pension_employer_rate"])
    pension_vol = _round(pension_wage * voluntary_pension_rate)

    steps = [
        f"月薪資 {monthly_wage:,} → 勞保投保薪資 {labor_salary:,}、健保投保金額 {health_amount:,}、勞退提繳工資 {pension_wage:,}",
        f"勞保（含就保）自付 = {labor_salary:,} × 12.5% × 20% = {labor_emp:,} 元",
        f"健保自付 = {health_amount:,} × 5.17% × 30% = {health_per_person:,} 元 × (本人 + 眷屬 {charged} 人) = {health_emp:,} 元"
        + ("（眷屬超過 3 人以 3 人計）" if nhi_dependents > charged else ""),
        f"勞退自提 = {pension_wage:,} × {fmt(voluntary_pension_rate * 100)}% = {pension_vol:,} 元（可自所得總額扣除）",
        f"公司負擔：勞保 {labor_er:,}、職災 {occ_er:,}、健保 {health_er:,}、勞退 6% {pension_er:,} 元",
    ]
    return CalcResult(
        value=Decimal(labor_emp + health_emp + pension_vol),
        unit="TWD",
        steps=steps,
        law_refs=["勞工保險條例第15條", "全民健康保險法第27條", "勞工退休金條例第14條"],
        rule_version=r.version,
        basis={
            "labor_insured_salary": labor_salary,
            "health_insured_amount": health_amount,
            "pension_contribution_wage": pension_wage,
            "employee": {"labor": labor_emp, "health": health_emp, "pension_voluntary": pension_vol},
            "employer": {"labor": labor_er, "occupational": occ_er, "health": health_er, "pension": pension_er},
            "nhi_dependents_charged": charged,
        },
    )


def bonus_supplementary_premium(health_insured_amount: int, bonus_ytd_before: int, bonus_now: int, on: date) -> CalcResult:
    """二代健保補充保費：當年累計獎金超過「給付當月投保金額 4 倍」的部分 × 2.11%。"""
    p = rule("insurance", on).params
    free = health_insured_amount * p["bonus_free_multiple"]
    taxable = max(0, bonus_ytd_before + bonus_now - max(free, bonus_ytd_before))
    taxable = min(taxable, bonus_now)
    premium = _round(taxable * p["supplementary_rate"])
    return CalcResult(
        value=Decimal(premium),
        unit="TWD",
        steps=[
            f"免扣額度 = 投保金額 {health_insured_amount:,} × 4 = {free:,} 元",
            f"本年累計獎金 {bonus_ytd_before:,} + 本次 {bonus_now:,} = {bonus_ytd_before + bonus_now:,} 元，本次應計費 {taxable:,} 元",
            f"補充保費 = {taxable:,} × 2.11% = {premium:,} 元",
        ],
        law_refs=["全民健康保險法第31條"],
        rule_version=rule("insurance", on).version,
        basis={"free_quota": free, "taxable": taxable},
    )


def attendance_bonus_after_leave(bonus: int, prorated_days: Fraction) -> CalcResult:
    """全勤獎金按請假日數比例扣發：扣 bonus ÷ 30 × 日數（勞工請假規則第9條第2項；勞動部 Q&A 範例）。"""
    deduct = Fraction(bonus, 30) * prorated_days
    deduct_int = int(deduct)  # 扣款無條件捨去
    return CalcResult(
        value=Decimal(bonus - deduct_int),
        unit="TWD",
        steps=[f"全勤獎金 {bonus:,} ÷ 30 × {fmt(prorated_days)} 日 = 扣 {fmt(deduct)} → {deduct_int:,} 元，實發 {bonus - deduct_int:,} 元"],
        law_refs=["勞工請假規則第9條"],
        rule_version="attendance_bonus@2026-01-01",
        basis={"deducted": deduct_int},
    )
