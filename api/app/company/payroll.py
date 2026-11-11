"""月薪資單：法定計算（engine）＋曜川科技規定（policy）。合成資料與日後的薪資工具共用。"""

from dataclasses import dataclass, field
from datetime import date
from fractions import Fraction

from app.company.policy import COMPANY_LEAVE, OCCUPATIONAL_RATE_DEMO
from app.engine.insurance import attendance_bonus_after_leave, bonus_supplementary_premium, monthly_premiums
from app.engine.overtime import OvertimeEntry, hourly_wage, monthly_overtime

LABELS = {
    "base": "本薪", "meal": "伙食津貼", "position": "職務加給", "professional": "專業加給",
    "attendance_bonus": "全勤獎金", "overtime": "加班費", "comp_time_payout": "補休到期折發",
    "annual_leave_payout": "未休特休折發", "year_end_bonus": "年終獎金",
    "leave_deduction": "請假扣薪", "labor_insurance": "勞保費（含就保）", "health_insurance": "健保費",
    "pension_voluntary": "勞退自提", "nhi_supplementary": "二代健保補充保費",
}


@dataclass
class PayInputs:
    pay_month: str
    base: int
    allowances: dict[str, int]
    attendance_bonus: int
    leave_hours: dict[str, Fraction] = field(default_factory=dict)  # 本月已核准請假時數，依假別
    sick_hours_before_month: Fraction = Fraction(0)  # 本年度先前已請未住院病假時數
    overtime: list[OvertimeEntry] = field(default_factory=list)  # 本月核准、選擇加班費者
    comp_time_payout: list[OvertimeEntry] = field(default_factory=list)
    annual_leave_payout_hours: Fraction = Fraction(0)
    year_end_bonus: int = 0
    bonus_ytd_before: int = 0
    nhi_dependents: int = 0
    voluntary_pension_rate: Fraction = Fraction(0)
    unpaid_days: int = 0  # 育嬰留停等不支薪日數


@dataclass
class PayItem:
    category: str
    code: str
    amount: int
    note: dict | None = None

    @property
    def label(self) -> str:
        return LABELS[self.code]


def compute_payslip(i: PayInputs) -> tuple[list[PayItem], dict]:
    year, month = map(int, i.pay_month.split("-"))
    month_end = date(year, month, 28)
    monthly_wage = i.base + sum(i.allowances.values()) + i.attendance_bonus
    hw = hourly_wage(monthly_wage)
    items: list[PayItem] = [PayItem("earning", "base", i.base)]
    for code, amt in i.allowances.items():
        if amt:
            items.append(PayItem("earning", code, amt))

    leave_days_for_bonus = (i.leave_hours.get("sick", Fraction(0)) + i.leave_hours.get("personal", Fraction(0))) / 8
    if i.attendance_bonus:
        r = attendance_bonus_after_leave(i.attendance_bonus, leave_days_for_bonus)
        sick_h, personal_h = i.leave_hours.get("sick", Fraction(0)), i.leave_hours.get("personal", Fraction(0))
        why = [f"本月病假 {float(sick_h):g} 小時、事假 {float(personal_h):g} 小時，合計 {float(leave_days_for_bonus):.3g} 日（每日 8 小時）"] \
            if leave_days_for_bonus else ["本月無病假、事假，全勤獎金全額發給"]
        items.append(PayItem("earning", "attendance_bonus", int(r.value), {"steps": why + r.steps}))

    if i.overtime:
        r = monthly_overtime(monthly_wage, i.overtime)
        items.append(PayItem("earning", "overtime", int(r.value), {"steps": r.steps}))
    if i.comp_time_payout:
        r = monthly_overtime(monthly_wage, i.comp_time_payout)
        items.append(PayItem("earning", "comp_time_payout", int(r.value), {"steps": r.steps}))
    if i.annual_leave_payout_hours:
        amt = int(hw * i.annual_leave_payout_hours + Fraction(1, 2))
        items.append(PayItem("earning", "annual_leave_payout", amt, {"hours": str(i.annual_leave_payout_hours)}))
    if i.year_end_bonus:
        items.append(PayItem("earning", "year_end_bonus", i.year_end_bonus))

    # 請假扣薪：事假／家庭照顧假全扣；病假本年前 5 日全薪，其後半薪；生理假半薪；不支薪日依日薪扣
    full_paid_sick = Fraction(COMPANY_LEAVE["sick_full_pay_days"] * 8)
    sick = i.leave_hours.get("sick", Fraction(0))
    sick_half = max(Fraction(0), i.sick_hours_before_month + sick - max(full_paid_sick, i.sick_hours_before_month))
    deduction = (
        hw * (i.leave_hours.get("personal", 0) + i.leave_hours.get("family_care", 0))
        + hw * sick_half / 2
        + hw * i.leave_hours.get("menstrual", 0) / 2
        + Fraction(monthly_wage, 30) * i.unpaid_days
    )
    if deduction:
        items.append(PayItem("deduction", "leave_deduction", int(deduction), {"sick_half_paid_hours": str(sick_half)}))

    prem = monthly_premiums(monthly_wage, month_end, i.nhi_dependents, i.voluntary_pension_rate, OCCUPATIONAL_RATE_DEMO)
    emp = prem.basis["employee"]
    items.append(PayItem("deduction", "labor_insurance", emp["labor"]))
    items.append(PayItem("deduction", "health_insurance", emp["health"]))
    if emp["pension_voluntary"]:
        items.append(PayItem("deduction", "pension_voluntary", emp["pension_voluntary"]))
    if i.year_end_bonus:
        sup = bonus_supplementary_premium(prem.basis["health_insured_amount"], i.bonus_ytd_before, i.year_end_bonus, month_end)
        if sup.value:
            items.append(PayItem("deduction", "nhi_supplementary", int(sup.value), {"steps": sup.steps}))

    gross = sum(x.amount for x in items if x.category == "earning")
    ded = sum(x.amount for x in items if x.category == "deduction")
    return items, {"gross": gross, "deductions": ded, "net": gross - ded, "monthly_wage": monthly_wage, "insurance": prem.basis}
