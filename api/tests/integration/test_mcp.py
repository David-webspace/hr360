"""MCP server：權杖驗證、唯讀／可執行 scope、與網頁共用的權限邊界。"""

import json
from contextlib import contextmanager

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app import tokens
from app.main import app

HEADERS = {"accept": "application/json, text/event-stream", "content-type": "application/json"}


@pytest.fixture(scope="module")
def app_client():
    # MCP session manager 每個程序只能啟動一次，整個模組共用同一個 lifespan
    with TestClient(app) as c:
        yield c


@pytest.fixture
def mcp_client(app_client, db, monkeypatch):
    @contextmanager
    def same_session():
        yield db

    import app.mcp_server as server
    monkeypatch.setattr(server, "SessionLocal", same_session)
    return app_client


def token_for(db, username: str, scope: str) -> str:
    uid = db.execute(text("SELECT id FROM users WHERE username = :u"), {"u": username}).scalar_one()
    return tokens.create(db, uid, "test", scope, 1)["token"]


def rpc(client, token: str | None, method: str, params: dict | None = None):
    headers = dict(HEADERS)
    if token:
        headers["authorization"] = f"Bearer {token}"
    body = {"jsonrpc": "2.0", "id": 1, "method": method, "params": params or {}}
    return client.post("/mcp", headers=headers, content=json.dumps(body))


def call(client, token, name, args):
    r = rpc(client, token, "tools/call", {"name": name, "arguments": args})
    assert r.status_code == 200, r.text
    result = r.json()["result"]
    return result.get("structuredContent") or json.loads(result["content"][0]["text"])


def test_requires_token(mcp_client):
    assert rpc(mcp_client, None, "tools/list").status_code == 401
    assert rpc(mcp_client, "hr360_fake", "tools/list").status_code == 401


def test_tool_list_and_balance(mcp_client, db):
    t = token_for(db, "grace.lin", "read")
    names = {x["name"] for x in rpc(mcp_client, t, "tools/list").json()["result"]["tools"]}
    assert {"get_leave_balance", "draft_leave_request", "submit_leave_request"} <= names
    assert call(mcp_client, t, "get_leave_balance", {})["annual"]["available_total"] == 13


def test_same_policy_as_web(mcp_client, db):
    t = token_for(db, "grace.lin", "read")
    assert call(mcp_client, t, "get_salary", {"employee": "王志明"}) == {"error": "無權限或查無此人"}
    payroll = token_for(db, "sharon.tsai", "read")
    assert call(mcp_client, payroll, "get_salary", {"employee": "王志明"})["salary"]["base"] == 68000


def test_read_token_cannot_act(mcp_client, db):
    t = token_for(db, "grace.lin", "read")
    out = call(mcp_client, t, "draft_leave_request", {"leave_type": "annual", "start": "2026-11-12", "end": "2026-11-12"})
    assert "唯讀" in out["error"]


def test_action_token_draft_and_submit(mcp_client, db):
    t = token_for(db, "grace.lin", "action")
    card = call(mcp_client, t, "draft_leave_request", {"leave_type": "annual", "start": "2026-11-12", "end": "2026-11-12"})
    assert card["hours"] == 8 and card["status"] == "draft"
    assert call(mcp_client, t, "submit_leave_request", {"draft_id": card["draft_id"]})["status"] == "pending"
    other = token_for(db, "jason.wang", "action")
    assert call(mcp_client, other, "submit_leave_request", {"draft_id": card["draft_id"]}) == {"error": "無權限或查無此人"}


def test_revoked_token_rejected(mcp_client, db):
    uid = db.execute(text("SELECT id FROM users WHERE username = 'grace.lin'")).scalar_one()
    out = tokens.create(db, uid, "x", "read", 1)
    tokens.revoke(db, uid, out["id"])
    assert rpc(mcp_client, out["token"], "tools/list").status_code == 401


def test_mcp_calls_are_audited(mcp_client, db):
    t = token_for(db, "grace.lin", "read")
    call(mcp_client, t, "get_salary", {"employee": "王志明"})
    row = db.execute(text("SELECT channel, event, denied FROM audit_log ORDER BY id DESC LIMIT 1")).one()
    assert tuple(row) == ("mcp", "mcp_tool", True)
