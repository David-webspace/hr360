"""知識庫文件中的數字必須和 policy.py、engine 一致；改了任何一邊而忘了另一邊，這裡會失敗。"""

from datetime import date
from fractions import Fraction
from pathlib import Path

import pytest

from app.company import policy as P
from app.engine.annual_leave import calendar_year_entitlement
from app.engine.insurance import monthly_premiums
from app.engine.overtime import OvertimeEntry, monthly_overtime
from app.kb.ingest import KB_DIR, parse

DOCS = {p.stem: p.read_text() for p in KB_DIR.glob("*.md")}


def n(x: int) -> str:
    return f"{x:,}"


EXPECT = [
    ("01-work-rules", [P.WORK_HOURS["flex_start_from"], P.WORK_HOURS["flex_start_to"], "10:00 至 16:00", "三個月"]),
    ("02-leave", [f"前 {P.COMPANY_LEAVE['sick_full_pay_days']} 日", "十四日", "生日當月或次月"]),
    ("04-payroll", [n(P.PAYROLL["meal_allowance"]), n(P.PAYROLL["attendance_bonus"]), f"每月 {P.PAYROLL['pay_day']} 日"]
     + [n(v) for v in P.PAYROLL["position_allowance"].values()]
     + [n(v) for v in P.PAYROLL["professional_allowance"].values()]
     + [f"{n(lo)}–{n(hi)}" for _, lo, hi in P.JOB_GRADES.values()]
     + [f"{k} {v}" for k, v in P.PAYROLL["year_end_bonus_performance_months"].items()]),
    ("05-overtime", [f"{P.OVERTIME['comp_time_valid_months']} 個月", "四十六小時"]),
    ("07-group-insurance", [n(v) for k, v in P.GROUP_INSURANCE.items() if isinstance(v, int)]),
    ("08-welfare", [n(v) for v in P.WELFARE["festival_gifts"].values()] + [n(P.WELFARE["birthday_gift"]),
     n(P.WELFARE["wedding_gift"]), n(P.WELFARE["childbirth_gift"]), n(P.WELFARE["hospitalization"]["amount"]),
     f"{P.WELFARE['hospitalization']['min_days']} 日", f"{P.WELFARE['hospitalization']['max_times_per_year']} 次",
     n(P.WELFARE["health_check"]["budget"]), f"{P.WELFARE['club_monthly']} 元"] + [n(v) for v in P.WELFARE["funeral"].values()]),
    ("09-travel-subsidy", [n(v) for _, v in P.TRAVEL_SUBSIDY["tiers"]] + [n(P.TRAVEL_SUBSIDY["family_per_person"]),
     f"以 {P.TRAVEL_SUBSIDY['family_max_persons']} 人為限", P.TRAVEL_SUBSIDY["claim_deadline"]]),
    ("10-training", [f"{int(P.TRAINING['degree_ratio'] * 100)}%", n(P.TRAINING["degree_cap_per_year"]),
     n(P.TRAINING["bond_threshold"]), f"{P.TRAINING['bond_months']} 個月"]),
    ("11-business-trip", [f"{P.BUSINESS_TRIP['domestic_per_diem']} 元"] + [n(v) for v in P.BUSINESS_TRIP["domestic_hotel_cap"].values()]
     + [f"USD {v}" for v in P.BUSINESS_TRIP["overseas_per_diem_usd"].values()]
     + [f"USD {v}" for v in P.BUSINESS_TRIP["overseas_hotel_cap_usd"].values()] + [f"{P.BUSINESS_TRIP['claim_deadline_workdays']} 個工作日"]),
    ("12-remote-work", [f"每週最多 {P.REMOTE_WORK['max_days_per_week']} 日", f"前 {P.REMOTE_WORK['request_lead_days']} 日"]),
    ("13-performance", [f"{k} {v}%" for k, v in P.PERFORMANCE["distribution"].items()] + [f"{P.PERFORMANCE['pip_days']} 日"]),
    ("14-family-gender", [P.HARASSMENT["mailbox"], f"分機 {P.HARASSMENT['hotline_ext']}", f"{P.HARASSMENT['investigation_months']} 個月", "30 日"]),
    ("06-labor-health-insurance", ["12.5%", "5.17%", "29,500", "45,800", "72,800", "313,000", "150,000", "2.11%", "0.56"]),
]


@pytest.mark.parametrize("slug, needles", EXPECT, ids=[e[0] for e in EXPECT])
def test_policy_numbers_in_docs(slug, needles):
    missing = [x for x in needles if x not in DOCS[slug]]
    assert not missing, f"{slug} 缺少：{missing}"


def test_leave_doc_example_matches_engine():
    assert calendar_year_entitlement(date(2024, 3, 15), 2026).value == 76
    assert "以 76 小時計" in DOCS["02-leave"]


def test_overtime_doc_example_matches_engine():
    r = monthly_overtime(36000, [OvertimeEntry(date(2026, 10, 17), "rest_day", Fraction(10))])
    assert f"= {n(int(r.value))} 元" in DOCS["05-overtime"]


def test_insurance_doc_examples_match_engine():
    b = monthly_premiums(29500, date(2026, 1, 1), 2).basis["employee"]
    assert f"= {b['labor']} 元" in DOCS["06-labor-health-insurance"]
    assert f"為 {n(b['health'])} 元" in DOCS["06-labor-health-insurance"]


def test_every_doc_parses_into_cited_chunks():
    for p in Path(KB_DIR).glob("*.md"):
        d = parse(p)
        assert d.chunks, p.name
        assert all(text.startswith(f"【{d.title}") for _, text in d.chunks)
