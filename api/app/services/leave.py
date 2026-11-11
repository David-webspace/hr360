"""請假流程：draft（Agent 可建）→ pending（只有本人在畫面按確認才會送出）→ approved / rejected。

送出不開放給 LLM：若使用者貼上的文字或規章檢索結果夾帶「順便幫我把下週都請掉」，
LLM 最多只能做出一張草稿，真正送出仍需要本人在 UI 點擊。
"""

from datetime import date, datetime, time, timedelta
from fractions import Fraction
from functools import lru_cache

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.auth import Principal
from app.config import TZ, today
from app.engine.calendar_tw import WorkCalendar, working_hours_between
from app.engine.leave import LEAVE_TYPES, marriage_leave_days
from app.policy import PolicyDenied, resolve_employee
from app.services import ledger
from app.services.hr import leave_name, num

SELF_SERVICE = ("annual", "comp_time", "birthday", "personal", "family_care", "sick", "menstrual", "marriage",
                "bereavement", "prenatal", "paternity")
QUOTA_HOURS = {"sick": 240, "family_care": 56, "paternity": 56, "prenatal": 56}
NOT_FOUND = "查無此假單或無權限操作"


class LeaveError(ValueError):
    pass


@lru_cache(maxsize=1)
def _calendar_cached(key: str) -> WorkCalendar:  # key 只用來讓測試／重新 seed 後失效
    from app.db import SessionLocal

    with SessionLocal() as db:
        rows = db.execute(text("SELECT day, day_type, name FROM calendar_days")).all()
    return WorkCalendar(holidays={d: n or "" for d, t, n in rows if t == "national_holiday"},
                        makeup_workdays=frozenset(d for d, t, _ in rows if t == "makeup_workday"))


def calendar() -> WorkCalendar:
    return _calendar_cached("v1")


def _blocks(db: Session, schedule_id: int) -> tuple[tuple[time, time], ...]:
    wb = db.execute(text("SELECT work_blocks FROM work_schedules WHERE id = :i"), {"i": schedule_id}).scalar_one()
    return tuple((time.fromisoformat(a), time.fromisoformat(b)) for a, b in wb)


def _parse(value: str, blocks, is_end: bool) -> datetime:
    value = value.strip().replace(" ", "T")
    if "T" not in value:
        t = blocks[-1][1] if is_end else blocks[0][0]
        return datetime.combine(date.fromisoformat(value), t, TZ)
    return datetime.fromisoformat(value).replace(tzinfo=TZ)


def _used_hours(db: Session, emp_id: int, codes: tuple[str, ...], a: date, b: date, exclude: int | None) -> Fraction:
    v = db.execute(text("""
        SELECT COALESCE(SUM(hours), 0) FROM leave_requests
        WHERE emp_id = :e AND leave_type = ANY(:c) AND status IN ('pending', 'approved') AND id <> :x
          AND (start_at AT TIME ZONE 'Asia/Taipei')::date BETWEEN :a AND :b
    """), {"e": emp_id, "c": list(codes), "a": a, "b": b, "x": exclude or -1}).scalar()
    return Fraction(str(v))


def _validate(db: Session, e: dict, code: str, start: datetime, end: datetime, exclude: int | None = None) -> dict:
    if code not in SELF_SERVICE:
        raise LeaveError(f"「{leave_name(code) if code in LEAVE_TYPES else code}」需由人資協助辦理，請開立工單")
    if end <= start:
        raise LeaveError("結束時間必須晚於開始時間")
    if start.date() < today() - timedelta(days=3):
        raise LeaveError("僅能補請 3 日內的假，更早的請假請洽人資")
    if e["termination_date"] and end.date() > e["termination_date"]:
        raise LeaveError("請假期間超過離職日")
    blocks = _blocks(db, e["schedule_id"])
    hours = working_hours_between(start, end, calendar(), blocks)
    if hours <= 0:
        cal, d, names = calendar(), start.date(), []
        while d <= end.date():
            if d in cal.holidays:
                names.append(f"{d.month}/{d.day} {cal.holidays[d]}")
            d += timedelta(days=1)
        detail = f"：{'、'.join(names)}是國定假日" if names else "（例假或休息日）"
        raise LeaveError(f"這段時間沒有需要請假的上班時數{detail}，不用請假")
    if hours.denominator != 1:
        raise LeaveError(f"請假以 1 小時為單位，這段時間為 {num(hours)} 小時，請調整到整點")
    overlap = db.execute(text("""
        SELECT id, leave_type FROM leave_requests WHERE emp_id = :e AND status IN ('pending', 'approved') AND id <> :x
          AND start_at < :b AND end_at > :a LIMIT 1
    """), {"e": e["id"], "a": start, "b": end, "x": exclude or -1}).mappings().one_or_none()
    if overlap:
        raise LeaveError(f"與既有假單 #{overlap['id']}（{leave_name(overlap['leave_type'])}）時間重疊")
    y0, y1 = date(start.year, 1, 1), date(start.year, 12, 31)
    info: dict = {"hours": hours, "warnings": []}
    if code in ledger.LEDGER_TYPES:
        ps = ledger.periods(db, e["id"], code, e["birth_date"], start.date())
        avail = sum((p.available for p in ps if p.valid_from <= start.date() <= p.expires), Fraction(0))
        alloc = ledger.allocate(ps, start.date(), hours)
        if alloc is None:
            raise LeaveError(f"{leave_name(code)}可用時數不足：該日可用 {num(avail)} 小時，本次需要 {num(hours)} 小時")
        info.update(alloc=alloc, balance_before=avail, balance_after=avail - hours)
    elif code in ("personal", "family_care"):
        used = _used_hours(db, e["id"], ("personal", "family_care"), y0, y1, exclude)
        if used + hours > 112:
            raise LeaveError(f"事假（含家庭照顧假）本年已用 {num(used)} 小時，上限 112 小時")
        if code == "family_care" and _used_hours(db, e["id"], ("family_care",), y0, y1, exclude) + hours > 56:
            raise LeaveError("家庭照顧假全年以 7 日（56 小時）為限")
        info["warnings"].append("事假不給薪" if code == "personal" else "家庭照顧假不給薪，但不影響全勤獎金")
    elif code in QUOTA_HOURS:
        used = _used_hours(db, e["id"], (code,), y0, y1, exclude)
        if used + hours > QUOTA_HOURS[code]:
            tip = "，超過部分可改以事假或特休抵充" if code == "sick" else ""
            raise LeaveError(f"{leave_name(code)}本年已用 {num(used)} 小時，上限 {QUOTA_HOURS[code]} 小時{tip}")
        if code == "sick":
            info["warnings"].append("每年前 5 日全薪，其後半薪；全勤獎金按日數比例扣發")
            if hours > 24:
                info["warnings"].append("連續 3 日以上需檢附診斷證明")
    elif code == "menstrual":
        m0 = start.date().replace(day=1)
        m1 = (m0 + timedelta(days=32)).replace(day=1) - timedelta(days=1)
        if _used_hours(db, e["id"], ("menstrual",), m0, m1, exclude) + hours > 8:
            raise LeaveError("生理假每月以 1 日為限")
    elif code == "marriage":
        reg = db.execute(text("SELECT event_date FROM benefit_claims WHERE emp_id = :e AND benefit_code = 'wedding' ORDER BY event_date DESC LIMIT 1"),
                         {"e": e["id"]}).scalar()
        if reg is None:
            raise LeaveError("系統沒有你的結婚登記日，請先檢附結婚證明向人資登錄")
        ent = marriage_leave_days(reg, 0, extended_window=True)
        used = _used_hours(db, e["id"], ("marriage",), reg - timedelta(days=10), reg + timedelta(days=400), exclude)
        if used + hours > int(ent.value) * 8:
            raise LeaveError(f"婚假共 {int(ent.value)} 日，已用 {num(used)} 小時")
        info["warnings"].append("請假期間超過登記後 3 個月者，需主管同意延長")
    return info


def draft(db: Session, p: Principal, leave_type: str, start: str, end: str, reason: str | None = None) -> dict:
    e = resolve_employee(db, p, None, "S2")
    blocks = _blocks(db, e["schedule_id"])
    s, t = _parse(start, blocks, False), _parse(end, blocks, True)
    info = _validate(db, e, leave_type, s, t)
    rid = db.execute(text("""
        INSERT INTO leave_requests (emp_id, leave_type, start_at, end_at, hours, reason, status, approver_id, created_via)
        VALUES (:e, :t, :s, :x, :h, :r, 'draft', :a, :via) RETURNING id
    """), {"e": e["id"], "t": leave_type, "s": s, "x": t, "h": float(info["hours"]), "r": reason, "a": e["manager_id"],
           "via": "chat" if p.channel == "web" else p.channel}).scalar_one()
    db.commit()
    approver = db.execute(text("SELECT name FROM employees WHERE id = :i"), {"i": e["manager_id"]}).scalar()
    card = {"draft_id": rid, "leave_type": leave_type, "leave_name": leave_name(leave_type),
            "start": s.isoformat(timespec="minutes"), "end": t.isoformat(timespec="minutes"),
            "hours": num(info["hours"]), "approver": approver, "warnings": info["warnings"],
            "status": "draft", "next_step": "草稿已建立，請本人在畫面上按「確認送出」，送出後才會進入主管簽核"}
    if "balance_before" in info:
        card.update(balance_before=num(info["balance_before"]), balance_after=num(info["balance_after"]))
    return card


def _own(db: Session, p: Principal, rid: int, statuses: tuple[str, ...]) -> dict:
    row = db.execute(text("""
        SELECT r.*, e.birth_date, e.schedule_id, e.termination_date, e.manager_id FROM leave_requests r
        JOIN employees e ON e.id = r.emp_id
        WHERE r.id = :i AND r.emp_id = :me AND r.status = ANY(:st)
    """), {"i": rid, "me": p.emp_id or -1, "st": list(statuses)}).mappings().one_or_none()
    if row is None:
        raise PolicyDenied("leave_not_owned_or_state")
    return dict(row)


def submit(db: Session, p: Principal, rid: int) -> dict:
    r = _own(db, p, rid, ("draft",))
    e = {"id": r["emp_id"], "birth_date": r["birth_date"], "schedule_id": r["schedule_id"],
         "termination_date": r["termination_date"]}
    info = _validate(db, e, r["leave_type"], r["start_at"].astimezone(TZ), r["end_at"].astimezone(TZ), exclude=rid)
    db.execute(text("UPDATE leave_requests SET status = 'pending', created_at = now() WHERE id = :i"), {"i": rid})
    if "alloc" in info:
        ledger.write(db, r["emp_id"], r["leave_type"], info["alloc"], "hold", rid, -1, p.user_id, "送出預扣")
    db.commit()
    return {"id": rid, "status": "pending"}


def cancel(db: Session, p: Principal, rid: int) -> dict:
    r = _own(db, p, rid, ("draft", "pending", "approved"))
    if r["status"] == "approved" and r["start_at"] <= datetime.now(TZ):
        raise LeaveError("已開始或已結束的假單無法自行取消，請洽人資")
    if r["leave_type"] in ledger.LEDGER_TYPES:
        if r["status"] == "pending":
            ledger.write(db, r["emp_id"], r["leave_type"], ledger.holds_of(db, rid), "release", rid, 1, p.user_id, "取消釋放")
        elif r["status"] == "approved":
            used = db.execute(text("SELECT period_key, -SUM(delta_hours) FROM leave_ledger WHERE ref_request_id = :r AND kind = 'use' GROUP BY period_key"),
                              {"r": rid}).all()
            ledger.write(db, r["emp_id"], r["leave_type"], [(k, Fraction(str(h))) for k, h in used], "use", rid, 1, p.user_id, "取消退回")
    db.execute(text("UPDATE leave_requests SET status = 'cancelled' WHERE id = :i"), {"i": rid})
    db.commit()
    return {"id": rid, "status": "cancelled"}


def decide(db: Session, p: Principal, rid: int, approve: bool, note: str | None = None) -> dict:
    # 簽核者條件寫在 SQL：只有申請人的直屬主管查得到這張待簽假單
    r = db.execute(text("""
        SELECT r.id, r.emp_id, r.leave_type FROM leave_requests r JOIN employees e ON e.id = r.emp_id
        WHERE r.id = :i AND r.status = 'pending' AND e.manager_id = :me AND r.emp_id <> :me
    """), {"i": rid, "me": p.emp_id or -1}).mappings().one_or_none()
    if r is None:
        raise PolicyDenied("not_approver_or_state")
    if r["leave_type"] in ledger.LEDGER_TYPES:
        holds = ledger.holds_of(db, rid)
        ledger.write(db, r["emp_id"], r["leave_type"], holds, "release", rid, 1, p.user_id)
        if approve:
            ledger.write(db, r["emp_id"], r["leave_type"], holds, "use", rid, -1, p.user_id, "主管核准")
    db.execute(text("""
        UPDATE leave_requests SET status = :s, decided_at = now(), approver_id = :me, decision_note = :n WHERE id = :i
    """), {"s": "approved" if approve else "rejected", "me": p.emp_id, "n": note, "i": rid})
    db.commit()
    return {"id": rid, "status": "approved" if approve else "rejected"}


def _rows(db: Session, where: str, params: dict) -> list[dict]:
    rows = db.execute(text(f"""
        SELECT r.id, e.name AS employee, r.leave_type, r.start_at, r.end_at, r.hours, r.status, r.reason, r.created_at
        FROM leave_requests r JOIN employees e ON e.id = r.emp_id WHERE {where} ORDER BY r.start_at DESC LIMIT 50
    """), params).mappings().all()
    return [{**dict(x), "leave_name": leave_name(x["leave_type"]), "hours": num(x["hours"]),
             "start_at": x["start_at"].astimezone(TZ).isoformat(timespec="minutes"),
             "end_at": x["end_at"].astimezone(TZ).isoformat(timespec="minutes"),
             "created_at": x["created_at"].astimezone(TZ).isoformat(timespec="minutes")} for x in rows]


def my_requests(db: Session, p: Principal) -> list[dict]:
    return _rows(db, "r.emp_id = :me", {"me": p.emp_id or -1})


def pending_approvals(db: Session, p: Principal) -> list[dict]:
    # 病假原因屬 S3，主管簽核畫面不顯示
    rows = _rows(db, "r.status = 'pending' AND e.manager_id = :me AND r.emp_id <> :me", {"me": p.emp_id or -1})
    for x in rows:
        if x["leave_type"] in ("sick", "menstrual", "prenatal"):
            x["reason"] = None
    return rows
