from fractions import Fraction

import pytest

from app.policy import PolicyDenied
from app.services import hr, leave


def test_draft_submit_approve_moves_ledger(db, as_user):
    grace, boss = as_user("grace.lin"), None
    card = leave.draft(db, grace, "annual", "2026-11-12", "2026-11-12", "家中有事")
    assert (card["hours"], card["balance_before"], card["balance_after"]) == (8, 13, 5)
    assert hr.leave_balance(db, grace)["annual"]["available_total"] == 13  # 草稿不預扣

    leave.submit(db, grace, card["draft_id"])
    b = hr.leave_balance(db, grace)["annual"]
    assert (b["remaining_total"], b["available_total"]) == (21, 5)

    approver = card["approver"]
    from sqlalchemy import text
    boss_user = db.execute(text("SELECT u.username FROM users u JOIN employees e ON e.id = u.employee_id WHERE e.name = :n"),
                           {"n": approver}).scalar_one()
    boss = as_user(boss_user)
    assert any(x["id"] == card["draft_id"] for x in leave.pending_approvals(db, boss))
    leave.decide(db, boss, card["draft_id"], approve=True)
    b = hr.leave_balance(db, grace)["annual"]
    assert (b["remaining_total"], b["available_total"]) == (13, 5)


def test_reject_releases_hold(db, as_user):
    allen = as_user("allen.huang")
    card = leave.draft(db, allen, "annual", "2026-11-16T09:00", "2026-11-16T13:00")
    leave.submit(db, allen, card["draft_id"])
    before = hr.leave_balance(db, allen)["annual"]["available_total"]
    from sqlalchemy import text
    mgr = db.execute(text("""SELECT u.username FROM employees e JOIN employees m ON m.id = e.manager_id
                             JOIN users u ON u.employee_id = m.id WHERE e.name = '黃俊傑'""")).scalar_one()
    leave.decide(db, as_user(mgr), card["draft_id"], approve=False)
    assert hr.leave_balance(db, allen)["annual"]["available_total"] == before + card["hours"] == before + 3  # 09–13 扣午休


def test_only_direct_manager_can_approve(db, as_user):
    grace = as_user("grace.lin")
    card = leave.draft(db, grace, "annual", "2026-11-13", "2026-11-13")
    leave.submit(db, grace, card["draft_id"])
    for intruder in ("kevin.chen", "grace.lin", "vivian.wu"):
        with pytest.raises(PolicyDenied):
            leave.decide(db, as_user(intruder), card["draft_id"], approve=True)


def test_cannot_submit_someone_elses_draft(db, as_user):
    card = leave.draft(db, as_user("grace.lin"), "annual", "2026-11-13", "2026-11-13")
    with pytest.raises(PolicyDenied):
        leave.submit(db, as_user("jason.wang"), card["draft_id"])


@pytest.mark.parametrize("code, start, end, msg", [
    ("annual", "2026-11-16", "2026-11-18", "可用時數不足"),          # 24h > 13h
    ("annual", "2026-12-25", "2026-12-25", "不用請假"),  # 行憲紀念日
    ("annual", "2026-12-24", "2026-12-24", "重疊"),                  # 已有待簽假單
    ("annual", "2026-11-12T09:00", "2026-11-12T10:30", "1 小時為單位"),
    ("maternity", "2026-11-12", "2026-11-12", "人資"),
])
def test_draft_validation(db, as_user, code, start, end, msg):
    with pytest.raises(leave.LeaveError, match=msg):
        leave.draft(db, as_user("grace.lin"), code, start, end)


def test_sick_leave_cap_f14(db, as_user):
    ken = as_user("ken.hsieh")  # 已請 27 日
    with pytest.raises(leave.LeaveError, match="上限 240"):
        leave.draft(db, ken, "sick", "2026-11-11", "2026-11-16")
    assert leave.draft(db, ken, "sick", "2026-11-11", "2026-11-11")["hours"] == 8


def test_cancel_pending_releases(db, as_user):
    grace = as_user("grace.lin")
    pending = [x for x in leave.my_requests(db, grace) if x["status"] == "pending"][0]
    leave.cancel(db, grace, pending["id"])
    assert hr.leave_balance(db, grace)["annual"]["available_total"] == 21


def test_hours_are_whole_fraction(db, as_user):
    card = leave.draft(db, as_user("ken.hsieh"), "personal", "2026-11-12T08:00", "2026-11-12T12:00")
    assert Fraction(card["hours"]) == 4


def test_holiday_error_names_the_holiday(db, as_user):
    with pytest.raises(leave.LeaveError, match="12/25 行憲紀念日"):
        leave.draft(db, as_user("grace.lin"), "annual", "2026-12-25", "2026-12-25")
