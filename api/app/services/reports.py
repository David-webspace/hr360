"""報表匯出與稽核統計。

模型只決定「哪一張報表、哪段期間、什麼格式」；表格內容一律由這裡的固定查詢產生，權限條件跟一般查詢相同。
不開放模型自由寫 SQL：報表種類是白名單，每一種都先過權限檢查再查資料。
"""

import csv
import io
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime, timedelta

from openpyxl import Workbook
from openpyxl.styles import Font
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.agent import audit
from app.auth import Principal
from app.config import TZ
from app.policy import PolicyDenied, scope_sql
from app.services.hr import leave_name, num

MAX_ROWS = 5000
MAX_DAYS = 366
DAILY_LIMIT = 20
TTL = timedelta(hours=24)
FORMATS = {"xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", "csv": "text/csv; charset=utf-8"}

STATUS = {"draft": "草稿", "pending": "待簽核", "approved": "已核准", "rejected": "已駁回", "cancelled": "已取消"}
DAY_TYPE = {"weekday": "平日", "rest_day": "休息日", "national_holiday": "國定假日", "regular_leave": "例假"}
COMPENSATION = {"pay": "加班費", "comp_time": "補休"}
GROUP_BY = {"user": "使用者", "model": "模型", "intent": "意圖", "deny_reason": "拒絕原因"}


class ReportError(Exception):
    """參數或額度問題，訊息可直接告訴使用者。"""


def is_sysadmin(p: Principal) -> bool:
    return "sysadmin" in p.roles


def period(start: str, end: str) -> tuple[date, date]:
    a, b = date.fromisoformat(start), date.fromisoformat(end)
    if b < a or (b - a).days > MAX_DAYS:
        raise ReportError(f"期間需介於 1 天到 {MAX_DAYS} 天之間")
    return a, b


def _me(p: Principal) -> int:
    if p.emp_id is None:
        raise PolicyDenied("no_employee_record")
    return p.emp_id


def my_leave(db: Session, p: Principal, a: date, b: date) -> tuple[list[str], list[list]]:
    rows = db.execute(text("""
        SELECT leave_type, start_at, end_at, hours, status FROM leave_requests
        WHERE emp_id = :e AND status <> 'draft' AND (start_at AT TIME ZONE 'Asia/Taipei')::date BETWEEN :a AND :b
        ORDER BY start_at"""), {"e": _me(p), "a": a, "b": b}).all()
    fmt = "%Y-%m-%d %H:%M"
    return (["假別", "開始", "結束", "時數", "狀態"],
            [[leave_name(r.leave_type), r.start_at.astimezone(TZ).strftime(fmt), r.end_at.astimezone(TZ).strftime(fmt),
              num(r.hours), STATUS.get(r.status, r.status)] for r in rows])


def my_overtime(db: Session, p: Principal, a: date, b: date) -> tuple[list[str], list[list]]:
    rows = db.execute(text("""
        SELECT work_date, day_type, hours, compensation, status FROM overtime_records
        WHERE emp_id = :e AND work_date BETWEEN :a AND :b ORDER BY work_date"""), {"e": _me(p), "a": a, "b": b}).all()
    return (["日期", "日別", "時數", "補償方式", "狀態"],
            [[r.work_date.isoformat(), DAY_TYPE.get(r.day_type, r.day_type), num(r.hours),
              COMPENSATION.get(r.compensation, r.compensation), STATUS.get(r.status, r.status)] for r in rows])


def team_leave(db: Session, p: Principal, a: date, b: date) -> tuple[list[str], list[list]]:
    if not (p.managed_paths or p.hrbp_paths):
        raise PolicyDenied("not_manager")
    scope, sp = scope_sql(p, "S1")
    rows = db.execute(text(f"""
        SELECT e.emp_no, e.name, o.name AS unit, r.leave_type, SUM(r.hours) AS hours, COUNT(*) AS n
        FROM leave_requests r JOIN employees e ON e.id = r.emp_id JOIN org_units o ON o.id = e.org_unit_id
        WHERE r.status = 'approved' AND e.id <> :me_id AND {scope}
          AND (r.start_at AT TIME ZONE 'Asia/Taipei')::date BETWEEN :a AND :b
        GROUP BY e.emp_no, e.name, o.name, r.leave_type ORDER BY o.name, e.name, r.leave_type
    """), {**sp, "me_id": p.emp_id or -1, "a": a, "b": b}).all()
    return (["員工編號", "姓名", "單位", "假別", "時數", "筆數"],
            [[r.emp_no, r.name, r.unit, leave_name(r.leave_type), num(r.hours), r.n] for r in rows])


def audit_stats(db: Session, p: Principal, a: date, b: date, group_by: str) -> tuple[list[str], list[list]]:
    """稽核統計只給彙總數字，不含使用者的提問原文（原文可能含病假原因等個資，要看原文請到稽核頁）。"""
    if not is_sysadmin(p):
        raise PolicyDenied("not_sysadmin")
    key = {"user": "COALESCE(u.username, '（未登入）')", "model": "COALESCE(a.model, '—')",
           "intent": "COALESCE(a.intent, '—')", "deny_reason": "COALESCE(a.deny_reason, '—')"}.get(group_by)
    if key is None:
        raise ReportError("統計維度只能是 " + "、".join(GROUP_BY))
    extra = "AND a.denied" if group_by == "deny_reason" else ""
    rows = db.execute(text(f"""
        SELECT {key} AS k, COUNT(*) AS n, SUM(CASE WHEN a.denied THEN 1 ELSE 0 END) AS denied,
               SUM(CASE WHEN a.grounding_ok = false THEN 1 ELSE 0 END) AS ungrounded,
               SUM(a.input_tokens + a.cache_read_tokens + a.cache_write_tokens + a.output_tokens) AS tokens,
               COALESCE(SUM(a.cost_usd), 0) AS cost, AVG(a.latency_ms)::int AS latency
        FROM audit_log a LEFT JOIN users u ON u.id = a.user_id
        WHERE a.event IN ('chat', 'mcp_tool') AND (a.ts AT TIME ZONE 'Asia/Taipei')::date BETWEEN :a AND :b {extra}
        GROUP BY 1 ORDER BY n DESC
    """), {"a": a, "b": b}).all()
    return ([GROUP_BY[group_by], "提問數", "拒絕數", "數字未核對", "tokens", "成本 USD", "平均延遲 ms"],
            [[r.k, r.n, r.denied, r.ungrounded, int(r.tokens or 0), round(float(r.cost), 4), r.latency] for r in rows])


@dataclass
class Report:
    label: str
    build: Callable[[Session, Principal, date, date], tuple[list[str], list[list]]]
    basis: str


REPORTS: dict[str, Report] = {
    "my_leave": Report("我的請假紀錄", my_leave, "本人的假單，不含草稿；依請假開始日歸屬期間"),
    "my_overtime": Report("我的加班紀錄", my_overtime, "本人的加班申請，依加班日歸屬期間"),
    "team_leave": Report("團隊請假統計", team_leave, "權限範圍內的部屬，只計已核准假單、依請假開始日歸屬；不含請假原因"),
    "audit_by_user": Report("稽核統計（依使用者）", lambda db, p, a, b: audit_stats(db, p, a, b, "user"),
                            "問答與 MCP 呼叫的彙總，不含提問原文"),
    "audit_by_model": Report("稽核統計（依模型）", lambda db, p, a, b: audit_stats(db, p, a, b, "model"),
                             "問答與 MCP 呼叫的彙總，不含提問原文"),
}


def _cell(v):
    # Excel 會把 = + - @ 開頭的字串當公式執行（CSV／公式注入），一律加上單引號當純文字
    if isinstance(v, str) and v[:1] in ("=", "+", "-", "@", "\t", "\r"):
        return "'" + v
    return v


def to_csv(columns: list[str], rows: list[list]) -> bytes:
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(columns)
    w.writerows([[_cell(v) for v in r] for r in rows])
    return buf.getvalue().encode("utf-8-sig")  # BOM：Excel 直接開啟中文才不會亂碼


def to_xlsx(title: str, columns: list[str], rows: list[list]) -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = title[:31]
    ws.append(columns)
    for c in ws[1]:
        c.font = Font(bold=True)
    for r in rows:
        ws.append([_cell(v) for v in r])
    ws.freeze_panes = "A2"
    for i, col in enumerate(ws.columns, 1):
        width = max(sum(2 if ord(ch) > 255 else 1 for ch in str(c.value or "")) for c in col)
        ws.column_dimensions[col[0].column_letter].width = min(width + 2, 50)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def available(p: Principal) -> list[str]:
    if is_sysadmin(p) and p.emp_id is None:
        return ["audit_by_user", "audit_by_model"]
    kinds = ["my_leave", "my_overtime"]
    if p.managed_paths or p.hrbp_paths:
        kinds.append("team_leave")
    return kinds


def export(db: Session, p: Principal, kind: str, fmt: str, start: str, end: str) -> dict:
    report = REPORTS.get(kind)
    if report is None:
        raise ReportError("沒有這種報表")
    if fmt not in FORMATS:
        raise ReportError("格式只能是 xlsx 或 csv")
    a, b = period(start, end)
    columns, rows = report.build(db, p, a, b)
    if not rows:
        raise ReportError(f"{a}～{b} 沒有{report.label}的資料，沒有產生檔案")
    used = db.execute(text("SELECT COUNT(*) FROM report_exports WHERE user_id = :u AND created_at > now() - interval '1 day'"),
                      {"u": p.user_id}).scalar()
    if used >= DAILY_LIMIT:
        raise ReportError(f"今天已匯出 {DAILY_LIMIT} 次，請明天再試")
    truncated = len(rows) > MAX_ROWS
    rows = rows[:MAX_ROWS]
    content = to_csv(columns, rows) if fmt == "csv" else to_xlsx(report.label, columns, rows)
    eid = uuid.uuid4().hex
    filename = f"{report.label}_{a}_{b}.{fmt}"
    db.execute(text("""INSERT INTO report_exports (id, user_id, kind, fmt, filename, row_count, content, expires_at)
                       VALUES (:i, :u, :k, :f, :n, :r, :c, :x)"""),
               {"i": eid, "u": p.user_id, "k": kind, "f": fmt, "n": filename, "r": len(rows), "c": content,
                "x": datetime.now(TZ) + TTL})
    audit.write(db, p, "report_export", question=f"{kind} {a}～{b} {fmt}，{len(rows)} 列")
    return {"export_id": eid, "kind": kind, "filename": filename, "report": report.label, "format": fmt, "period": f"{a}～{b}",
            "rows": len(rows), "columns": columns, "truncated": truncated, "basis": report.basis,
            "preview": rows[:5], "note": "檔案在聊天室的下載卡片，24 小時內有效，只有本人能下載"}


def download(db: Session, p: Principal, eid: str) -> tuple[str, str, bytes]:
    # 擁有者條件寫在 SQL：別人的、過期的、不存在的一律查不到（回 404，不透露檔案是否存在）
    row = db.execute(text("""SELECT fmt, filename, content FROM report_exports
                             WHERE id = :i AND user_id = :u AND expires_at > now()"""),
                     {"i": eid, "u": p.user_id}).one_or_none()
    if row is None:
        raise PolicyDenied("export_not_found")
    return row.filename, FORMATS[row.fmt], bytes(row.content)
