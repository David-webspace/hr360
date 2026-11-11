"""同名員工：權限範圍內同名要請使用者用員工編號指定；範圍外的同名不影響、也不透露。

示範資料沒有同名的人，測試在交易裡臨時複製一位員工，結束時回滾。
"""

import pytest
from sqlalchemy import text

from app.agent.tools import ToolContext, run_tool
from app.policy import AmbiguousEmployee, PolicyDenied, resolve_employee
from tests.integration.test_agent_and_api import client, login  # noqa: F401  （client fixture）

COLS = ["gender", "birth_date", "national_id", "title", "job_grade_id", "employment_type", "schedule_id", "hire_date",
        "seniority_start_date", "status"]


def clone(db, name: str, like_emp_no: str, manager_emp_no: str, emp_no: str) -> str:
    """複製一位員工的基本欄位，改名並掛到指定主管底下（同一單位）。"""
    db.execute(text(f"""
        INSERT INTO employees (emp_no, name, email, org_unit_id, manager_id, {", ".join(COLS)})
        SELECT :no, :name, :email, m.org_unit_id, m.id, {", ".join("s." + c for c in COLS)}
        FROM employees s, employees m WHERE s.emp_no = :like AND m.emp_no = :mgr
    """), {"no": emp_no, "email": f"{emp_no}@example.test", "name": name, "like": like_emp_no, "mgr": manager_emp_no})
    return emp_no


def test_manager_with_same_name_subordinate_must_pick_by_emp_no(db, as_user):
    kevin = as_user("kevin.chen")
    twin = clone(db, "陳冠宇", "YC21020", "YC16001", "YC99001")
    with pytest.raises(AmbiguousEmployee) as e:
        resolve_employee(db, kevin, "陳冠宇", "S2")  # 以前會直接當成查自己
    assert {c["emp_no"] for c in e.value.candidates} == {"YC16001", twin}
    assert resolve_employee(db, kevin, None, "S2")["emp_no"] == "YC16001"
    assert resolve_employee(db, kevin, "我", "S2")["emp_no"] == "YC16001"
    assert resolve_employee(db, kevin, twin, "S2")["emp_no"] == twin


def test_tool_returns_candidates_instead_of_denied(db, as_user):
    clone(db, "王志明", "YC21020", "YC16001", "YC99002")
    out = run_tool(ToolContext(db, as_user("kevin.chen")), "get_leave_balance", {"employee": "王志明"})
    assert out.error and not out.denied
    assert "員工編號" in out.result["error"] and {c["emp_no"] for c in out.result["candidates"]} == {"YC21020", "YC99002"}


def test_same_name_outside_scope_is_invisible(db, as_user):
    clone(db, "林佳穎", "YC24007", "YC16001", "YC99003")  # 同名的人在別的課
    grace = as_user("grace.lin")
    assert resolve_employee(db, grace, "林佳穎", "S2")["emp_no"] == "YC24007"  # 範圍內只有自己
    with pytest.raises(PolicyDenied) as e:
        resolve_employee(db, grace, "YC99003", "S2")
    assert e.value.reason == "out_of_scope_or_not_found"


def test_audit_filter_matches_emp_no(client, db, as_user):
    run_tool(ToolContext(db, as_user("grace.lin")), "get_leave_balance", {})
    from app.agent import audit
    audit.write(db, as_user("grace.lin"), "login")
    login(client, "sysadmin")
    rows = client.get("/api/admin/audit", params={"user": "YC24007"}).json()["events"]
    assert rows and all(r["emp_no"] == "YC24007" for r in rows)
