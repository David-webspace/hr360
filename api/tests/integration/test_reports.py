"""報表匯出與稽核統計：權限、檔案內容、下載限制、角色工具組。"""

import csv
import io

import pytest
from openpyxl import load_workbook
from sqlalchemy import text

from app.agent.loop import run_chat
from app.agent.tools import ToolContext, run_tool, tool_names
from app.policy import PolicyDenied
from app.services import reports
from tests.integration.test_agent_and_api import FakeLLM, client, login  # noqa: F401  （client fixture）


def export(db, p, kind, fmt="xlsx", start="2026-01-01", end="2026-12-31"):
    return run_tool(ToolContext(db, p), "export_report", {"kind": kind, "format": fmt, "start": start, "end": end})


def content(db, eid) -> bytes:
    return bytes(db.execute(text("SELECT content FROM report_exports WHERE id = :i"), {"i": eid}).scalar())


def test_my_leave_xlsx_has_only_own_rows(db, as_user):
    out = export(db, as_user("grace.lin"), "my_leave")
    assert not out.error and out.result["rows"] > 0 and out.result["filename"].endswith(".xlsx")
    ws = load_workbook(io.BytesIO(content(db, out.result["export_id"]))).active
    assert [c.value for c in ws[1]] == ["假別", "開始", "結束", "時數", "狀態"]
    own = db.execute(text("""SELECT COUNT(*) FROM leave_requests r JOIN users u ON u.employee_id = r.emp_id
                             WHERE u.username = 'grace.lin' AND r.status <> 'draft'
                               AND r.start_at >= '2026-01-01' AND r.start_at < '2027-01-01'""")).scalar()
    assert ws.max_row - 1 == own == out.result["rows"]


def test_team_report_needs_manager_and_stays_in_scope(db, as_user):
    denied = export(db, as_user("grace.lin"), "team_leave")
    assert denied.denied and denied.deny_reason == "not_manager"
    out = export(db, as_user("kevin.chen"), "team_leave", fmt="csv")
    raw = content(db, out.result["export_id"])
    assert raw.startswith(b"\xef\xbb\xbf")  # BOM：Excel 開中文不亂碼
    rows = list(csv.reader(io.StringIO(raw.decode("utf-8-sig"))))
    team = {r[0] for r in db.execute(text("""
        SELECT e.emp_no FROM employees e WHERE e.manager_id = (SELECT employee_id FROM users WHERE username = 'kevin.chen')""")).all()}
    assert rows[0][0] == "員工編號" and rows[1:] and {r[0] for r in rows[1:]} <= team


def test_formula_injection_is_neutralised():
    raw = reports.to_csv(["名稱"], [["=HYPERLINK(\"http://x\")"], ["+1"], ["一般"], [-3]])
    rows = list(csv.reader(io.StringIO(raw.decode("utf-8-sig"))))
    assert rows[1][0].startswith("'=") and rows[2][0] == "'+1" and rows[3][0] == "一般" and rows[4][0] == "-3"


def test_period_and_empty_and_daily_limit(db, as_user, monkeypatch):
    p = as_user("grace.lin")
    assert "期間" in export(db, p, "my_leave", start="2025-01-01", end="2026-12-31").result["error"]
    assert "沒有" in export(db, p, "my_overtime", start="2020-01-01", end="2020-01-31").result["error"]
    monkeypatch.setattr(reports, "DAILY_LIMIT", 1)
    assert not export(db, p, "my_leave").error
    assert "上限" in export(db, p, "my_leave").result["error"] or "明天" in export(db, p, "my_leave").result["error"]


def test_download_only_by_owner_and_not_after_expiry(client, db, as_user):
    eid = export(db, as_user("grace.lin"), "my_leave").result["export_id"]
    login(client, "grace.lin")
    r = client.get(f"/api/exports/{eid}")
    assert r.status_code == 200 and r.headers["cache-control"] == "no-store"
    assert "filename*=UTF-8''" in r.headers["content-disposition"] and r.content[:2] == b"PK"
    login(client, "sharon.tsai")  # 薪酬人員也不能下載別人的匯出檔
    assert client.get(f"/api/exports/{eid}").status_code == 404
    db.execute(text("UPDATE report_exports SET expires_at = now() - interval '1 minute' WHERE id = :i"), {"i": eid})
    login(client, "grace.lin")
    assert client.get(f"/api/exports/{eid}").status_code == 404


def test_sysadmin_gets_only_audit_tools(db, as_user):
    admin, grace = as_user("sysadmin"), as_user("grace.lin")
    assert tool_names(admin) == ["export_report", "get_audit_stats"]
    assert "get_audit_stats" not in tool_names(grace) and "get_salary" in tool_names(grace)
    assert run_tool(ToolContext(db, grace), "get_audit_stats", {"start": "2026-11-01", "end": "2026-11-30", "group_by": "user"}).error
    assert run_tool(ToolContext(db, admin), "get_leave_balance", {}).error
    with pytest.raises(PolicyDenied):
        reports.audit_stats(db, grace, *reports.period("2026-11-01", "2026-11-30"), "user")


def test_audit_stats_has_no_question_text(db, as_user):
    run_chat(db, FakeLLM([[("get_salary", {"employee": "王志明"})], "無法提供。"]), as_user("grace.lin"), "小王薪水多少？病假原因")
    out = run_tool(ToolContext(db, as_user("sysadmin")), "get_audit_stats",
                   {"start": "2026-01-01", "end": "2026-12-31", "group_by": "user"})
    assert not out.error and any(r[0] == "grace.lin" and r[2] >= 1 for r in out.result["rows"])
    assert "小王" not in out.json and "病假原因" not in out.json


def test_sysadmin_chat_routes_to_audit_and_exports(db, as_user):
    admin = as_user("sysadmin")
    llm = FakeLLM([[("export_report", {"kind": "audit_by_model", "format": "xlsx", "start": "2026-11-01", "end": "2026-11-30"})],
                   "已產生稽核統計（依模型）的 Excel，請從下方下載卡片下載。"])
    r = run_chat(db, llm, admin, "把這個月的稽核統計依模型匯出成 Excel")
    assert r.intent == "report.export" and r.routed_by == "role"
    assert llm.calls[0]["tools"] == ["export_report", "get_audit_stats"]
    assert r.exports and r.exports[0]["filename"].endswith(".xlsx") and r.grounding_ok
    assert r.suggestions and all("特休" not in s for s in r.suggestions)


def test_claimed_export_without_file_is_blocked(db, as_user):
    # 第一次沒呼叫工具會被提醒；仍謊稱已匯出就升級強模型重答，強模型也謊稱時一律擋下
    llm = FakeLLM(["好的"] + ["檔案已在下方準備下載連結，請點擊即可取得。"] * 3)
    r = run_chat(db, llm, as_user("grace.lin"), "把我今年的請假紀錄匯出成 Excel")
    assert not r.exports and not r.grounding_ok
