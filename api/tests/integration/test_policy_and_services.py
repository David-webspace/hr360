"""權限邊界與查詢結果。數字對應 seed/fixtures.py 的關鍵員工，皆已人工驗算（見 seed/REPORT.md）。"""

import pytest

from app.policy import PolicyDenied
from app.services import hr

GRACE, KEVIN, JASON, ALLEN = "grace.lin", "kevin.chen", "jason.wang", "allen.huang"


def test_annual_balance_f01(db, as_user):
    # 2025 給 45h，2025 用 36h → 遞延 9h；2026 給 76h；2026 用 64h（先扣遞延 9h）→ 剩 21h；12/24 待簽 8h → 可用 13h
    r = hr.leave_balance(db, as_user(GRACE))["annual"]
    assert r["remaining_total"] == 21
    assert r["available_total"] == 13
    assert {p["period"]: p["remaining"] for p in r["periods"]} == {"2025": 0, "2026": 21}
    assert r["entitlement_this_year"]["hours"] == 76


def test_new_hire_has_no_annual_leave_yet(db, as_user):
    r = hr.leave_balance(db, as_user("tina.chang"))["annual"]
    assert r["available_total"] == 0
    assert "2026-11-11" in r["note"]


def test_overtime_pay_f05_october(db, as_user):
    r = hr.overtime_pay(db, as_user(ALLEN), "2026-10")
    assert r["overtime_pay"] == 22200  # 時薪 300：平日 10,400 + 國定假日 2,400×2 + 休息日 5,400 + 1,600
    assert r["basis"]["comp_time_hours"] == "6"
    assert r["basis"]["counted_extended_hours"] == "44"


@pytest.mark.parametrize("viewer", [GRACE, KEVIN, "vivian.wu"])
def test_salary_of_colleague_denied(db, as_user, viewer):
    # 一般員工、直屬主管、HRBP 都不能看別人薪資（S3）
    with pytest.raises(PolicyDenied):
        hr.salary(db, as_user(viewer), "王志明")


def test_payroll_can_see_salary_and_self_can_see_own(db, as_user):
    assert hr.salary(db, as_user("sharon.tsai"), "王志明")["salary"]["base"] == 68000
    assert hr.salary(db, as_user(JASON))["salary"]["base"] == 68000


def test_denied_and_not_found_are_indistinguishable(db, as_user):
    with pytest.raises(PolicyDenied) as a:
        hr.salary(db, as_user(GRACE), "王志明")
    with pytest.raises(PolicyDenied) as b:
        hr.salary(db, as_user(GRACE), "不存在的人")
    assert str(a.value) == str(b.value) == "out_of_scope_or_not_found"


def test_manager_sees_only_own_team(db, as_user):
    r = hr.team_leave_summary(db, as_user(KEVIN), "2026-07-01", "2026-09-30")
    names = {x["name"] for x in r["ranking"]}
    assert "王志明" in names
    assert "林佳穎" not in names  # 雲端平台課，不是陳冠宇的部屬
    assert r["scope_headcount"] == 8


def test_employee_cannot_query_team(db, as_user):
    with pytest.raises(PolicyDenied):
        hr.team_leave_summary(db, as_user(GRACE), "2026-07-01", "2026-09-30")


def test_manager_can_see_member_balance_but_not_other_team(db, as_user):
    assert hr.leave_balance(db, as_user(KEVIN), "王志明")["employee"] == "王志明"
    with pytest.raises(PolicyDenied):
        hr.leave_balance(db, as_user(KEVIN), "林佳穎")


def test_hrbp_scope(db, as_user):
    vivian = as_user("vivian.wu")  # 研發＋製造
    assert hr.leave_balance(db, vivian, "林佳穎")["employee"] == "林佳穎"
    with pytest.raises(PolicyDenied):
        hr.leave_balance(db, vivian, "楊佩珊")  # 業務中心


def test_sysadmin_sees_no_employee_data(db, as_user):
    with pytest.raises(PolicyDenied):
        hr.leave_balance(db, as_user("sysadmin"), "林佳穎")
    assert hr.find_employee(db, as_user("sysadmin"), "林")["matches"] == []


def test_directory_is_public_but_minimal(db, as_user):
    m = hr.find_employee(db, as_user(GRACE), "王志明")["matches"]
    assert m and set(m[0]) == {"name", "emp_no", "unit", "title", "phone_ext", "email"}


def test_marriage_transition_f10(db, as_user):
    r = hr.leave_balance(db, as_user("peggy.yang"))["marriage"]
    assert r["entitled_days"] == 14
    assert r["remaining_hours"] == 32  # 14 日 − 已核准 10 日（含 12 月預排）= 4 日


def test_insurance_summary_matches_engine(db, as_user):
    r = hr.insurance_summary(db, as_user(GRACE))
    assert r["employee"]["labor"] == 1145  # 月薪 61,000 → 勞保封頂 45,800
    assert r["health_insured_amount"] == 63800


def test_travel_subsidy_f01(db, as_user):
    r = hr.travel_subsidy(db, as_user(GRACE), 2026)
    assert (r["entitlement"], r["claimed"], r["remaining"]) == (8000, 5000, 3000)
