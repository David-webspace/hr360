"""曜川科技股份有限公司（虛構）的公司規定參數。

唯一來源：知識庫文件（kb/*.md）、合成資料產生器、計算工具都讀這裡。
tests/test_kb_consistency.py 會檢查文件中的數字與這裡一致，避免「文件寫 8,000、工具算 10,000」。
"""

from datetime import date
from fractions import Fraction

COMPANY = {
    "name": "曜川科技股份有限公司",
    "short": "曜川科技",
    "founded": date(2008, 3, 3),
    "hq": "臺北市內湖區（總部）",
    "rd_site": "新竹縣竹北市（研發中心、製造中心）",
    "email_domain": "yaochuan.example",
    "industry": "工業物聯網閘道器與嵌入式控制器之研發製造",
}

WORK_HOURS = {
    "flex_start_from": "08:00",
    "flex_start_to": "10:00",
    "core_hours": ("10:00", "16:00"),
    "lunch": ("12:00", "13:00"),
    "daily_hours": 8,
    "standard_blocks": (("09:00", "12:00"), ("13:00", "18:00")),
    "late_after": "10:00",
    "rest_day": "星期六",
    "regular_leave": "星期日",
    "leave_min_unit_hours": 1,
}

ANNUAL_LEAVE = {
    "system": "calendar_year",
    "deferral": "年度終結未休日數自動遞延至次一年度，次一年度終結仍未休者，於次年 1 月薪資折發工資",
    "payout_wage_basis": "年度終結時之月薪（本薪＋經常性給與）÷ 30",
}

COMPANY_LEAVE = {
    "birthday": {"days": 1, "window": "生日當月或次月", "paid": True},
    "sick_full_pay_days": 5,  # 未住院普通傷病假每年前 5 日全薪（優於法令半薪）
}

OVERTIME = {
    "pre_approval": True,
    "comp_time_ratio": 1,
    "comp_time_valid_months": 6,
    "comp_time_expiry_payout": "補休期限屆滿未休完之時數，依加班當日之加班費標準於次月薪資發給",
    "monthly_limit": 46,
}

PAYROLL = {
    "pay_day": 5,
    "pay_cycle": "每月 5 日發放上月薪資；遇例假日或國定假日提前至前一工作日",
    "meal_allowance": 3000,
    "attendance_bonus": 2000,
    "position_allowance": {"section_head": 5000, "dept_head": 10000, "center_head": 18000, "gm": 30000},
    "professional_allowance": {"rd": 4000, "it": 3000, "quality": 2000},
    "salary_review_month": 4,
    "year_end_bonus_guaranteed_months": 1,
    "year_end_bonus_performance_months": {"A": 2.5, "B+": 1.5, "B": 1.0, "C": 0.5, "D": 0},
    "year_end_bonus_pay": "農曆春節前 10 日發放；發放日在職者始得領取，年度中到職者按在職月數比例計算",
}

JOB_GRADES = {
    # 職等: (職稱帶, 職級1-3 的薪資帶下限, 上限)
    1: ("助理／技術員", 31000, 40000),
    2: ("專員／工程師", 38000, 56000),
    3: ("資深專員／資深工程師", 52000, 76000),
    4: ("主任／課長／主任工程師", 70000, 98000),
    5: ("經理", 95000, 135000),
    6: ("處長／協理", 130000, 185000),
    7: ("總經理", 220000, 260000),
}

TRAVEL_SUBSIDY = {
    # 年資（截至當年 1 月 1 日）: 年度補助額
    "tiers": [(0, 6000), (1, 8000), (3, 10000), (5, 12000)],
    "new_hire_rule": "當年度到職者，依到職日起至 12 月 31 日之在職月數按比例計算（未滿 1 個月以 1 個月計）",
    "family_per_person": 3000,
    "family_max_persons": 2,
    "claim_deadline": "12 月 15 日",
    "no_cash_out": True,
    "eligible_expenses": "旅行社團費收據、住宿發票、交通票券（機票、高鐵、台鐵）、景點門票",
}

WELFARE = {
    "festival_gifts": {"春節": 3000, "端午節": 2000, "中秋節": 2000},
    "birthday_gift": 1000,
    "wedding_gift": 6000,
    "childbirth_gift": 6000,
    "funeral": {"本人": 30000, "父母、配偶、子女": 8000, "配偶之父母": 5000},
    "hospitalization": {"amount": 3000, "min_days": 3, "max_times_per_year": 2},
    "health_check": {"under_40_every_years": 2, "over_40_every_years": 1, "budget": 5000},
    "club_monthly": 300,
}

TRAINING = {
    "assigned_external": "公司指派之外訓費用全額由公司負擔",
    "certificate_reimburse": "與職務相關之證照，通過後檢據核實補助報名費 100%，每年以 2 張為限",
    "degree_ratio": 0.5,
    "degree_cap_per_year": 30000,
    "bond_threshold": 50000,
    "bond_months": 12,
    "bond_refund": "未滿服務期間離職者，依未服務月數比例返還補助金額",
}

BUSINESS_TRIP = {
    "domestic_per_diem": 600,
    "domestic_hotel_cap": {"臺北市": 3200, "其他縣市": 2800},
    "overseas_per_diem_usd": {"亞洲": 70, "歐美及其他": 90},
    "overseas_hotel_cap_usd": {"亞洲": 180, "歐美及其他": 220},
    "premium_economy": "單程飛行 8 小時以上且職等 5 以上者，得搭乘豪華經濟艙",
    "claim_deadline_workdays": 10,
}

REMOTE_WORK = {
    "max_days_per_week": 2,
    "eligible_units": ["研發中心", "營運中心"],
    "requirement": "試用期滿、最近一次考核 B 以上",
    "request_lead_days": 1,
}

PERFORMANCE = {
    "cycles": ["6 月", "12 月"],
    "distribution": {"A": 15, "B+": 25, "B": 45, "C": 12, "D": 3},
    "promotion_month": 4,
    "pip_days": 90,
}

PROBATION_MONTHS = 3

GROUP_INSURANCE = {
    "term_life": 2_000_000,
    "accident": 3_000_000,
    "accident_medical": 30000,
    "hospital_daily": 1500,
    "cancer_lump_sum": 100000,
    "family_self_pay": "配偶及子女得自費加保，保費由薪資扣繳",
}

HARASSMENT = {
    "mailbox": "hr-care@yaochuan.example",
    "hotline_ext": "1995",
    "investigation_months": 2,
}

# 職業災害保險行業別費率依勞保局核定，此為示範值（非法定數字）
OCCUPATIONAL_RATE_DEMO = Fraction(21, 10000)
