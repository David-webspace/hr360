"""證明文件：上傳驗證、附件權限、讀圖欄位白名單、文件規則、依文件建立草稿（假 LLM，不花錢）。"""

import io
import json
import os
from datetime import date

import pytest
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy import text

from app.agent import vision
from app.agent.loop import run_chat
from app.config import settings
from app.db import get_db
from app.main import app, upload_limit
from app.services import attachments, leave
from tests.integration.test_agent_and_api import FakeLLM, fixed_router  # noqa: F401  （autouse fixture）

TODAY = date(2026, 11, 10)


class VisionLLM(FakeLLM):
    def image_user(self, t, image, media_type):
        return {"role": "user", "content": t, "image_bytes": len(image)}


@pytest.fixture(autouse=True)
def upload_tmp(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "upload_dir", str(tmp_path))
    monkeypatch.setattr(settings, "app_today", TODAY)
    upload_limit.hits.clear()


@pytest.fixture
def client(db):
    app.dependency_overrides[get_db] = lambda: db
    yield TestClient(app)
    app.dependency_overrides.clear()


def login(client, username):
    client.cookies.clear()
    r = client.post("/api/auth/login", json={"username": username, "password": os.environ["SEED_DEMO_PASSWORD"]})
    assert r.status_code == 200


def jpeg(size=(800, 600), exif: dict | None = None, fmt="JPEG") -> bytes:
    img = Image.new("RGB", size, "white")
    b = io.BytesIO()
    if exif:
        e = Image.Exif()
        e.update(exif)
        img.save(b, fmt, exif=e)
    else:
        img.save(b, fmt)
    return b.getvalue()


def doc(**fields) -> str:
    base = {"doc_type": "other", "names": [], "issuer": None, "issue_date": None, "rest_start": None, "rest_end": None,
            "rest_days": None, "event_date": None, "contains_instructions": False}
    return "```json\n" + json.dumps({**base, **fields}, ensure_ascii=False) + "\n```"


MEDICAL = dict(doc_type="medical_certificate", names=["林佳穎"], issuer="曜安醫院", issue_date="2026-11-09",
               rest_start="2026-11-09", rest_end="2026-11-11", rest_days=3)


# ── 上傳 ────────────────────────────────────────────────

def test_upload_reencodes_strips_exif_and_ignores_path_in_name(client, tmp_path):
    login(client, "grace.lin")
    r = client.post("/api/attachments", params={"name": "../../etc/證明.jpg"},
                    content=jpeg((3000, 2000), exif={0x010F: "SpyCam", 0x0110: "GPS-Model"}))
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["name"] == "證明.jpg" and len(out["id"]) == 32
    files = list(tmp_path.iterdir())
    assert [f.name for f in files] == [f"{out['id']}.jpg"]  # 只有 uuid 檔名，沒有跟著 ../ 寫到別處
    saved = Image.open(files[0])
    assert max(saved.size) == 1600 and not saved.getexif()


def test_upload_rejects_non_images_regardless_of_extension(client):
    login(client, "grace.lin")
    pdf = client.post("/api/attachments", params={"name": "cert.jpg"}, content=b"%PDF-1.4 fake")
    gif = client.post("/api/attachments", params={"name": "cert.jpg"}, content=jpeg(fmt="GIF"))
    assert pdf.status_code == 400 and gif.status_code == 400
    assert "只接受" in gif.json()["detail"]


def test_upload_size_cap_uses_declared_and_actual_length(client):
    login(client, "grace.lin")
    r = client.post("/api/attachments", content=b"x" * (attachments.MAX_BYTES + 1))
    assert r.status_code == 413


def test_image_follows_s3_owner_and_payroll_only(client):
    login(client, "grace.lin")
    aid = client.post("/api/attachments", content=jpeg()).json()["id"]
    own = client.get(f"/api/attachments/{aid}")
    assert own.headers["content-type"] == "image/jpeg"
    assert own.headers["cache-control"] == "no-store"  # 共用電腦換人登入不能從瀏覽器快取拿到原圖
    for who in ("jason.wang", "vivian.wu"):  # 其他員工、HRBP 都看不到原圖（診斷證明屬 S3）
        login(client, who)
        assert client.get(f"/api/attachments/{aid}").status_code == 404
    login(client, "sharon.tsai")
    assert client.get(f"/api/attachments/{aid}").status_code == 200
    assert client.get("/api/attachments/0" * 1).status_code == 404


# ── 讀圖輸出與規則 ───────────────────────────────────────

def test_parse_keeps_only_whitelisted_valid_fields():
    raw = "好的：" + json.dumps({"doc_type": "salary_slip", "names": ["王" * 50, "", "A", "B", "C", "D"],
                                "rest_start": "2026/11/09", "rest_days": 999, "event_date": "2026-11-01T00:00",
                                "diagnosis": "急性腸胃炎", "contains_instructions": "yes"})
    d = vision.parse(raw)
    assert d["doc_type"] == "other" and "diagnosis" not in d
    assert d["names"] == ["王" * 20, "A", "B", "C"]
    assert d["rest_start"] is None and d["rest_days"] is None and d["event_date"] == "2026-11-01"
    assert d["contains_instructions"] is False
    assert vision.parse("看不懂")["doc_type"] == "other"


def test_assess_rules():
    m = attachments.assess(vision.parse(doc(**MEDICAL)), "林佳穎", TODAY)
    assert m["suggested_leave_type"] == "sick" and m["suggested_start"] == "2026-11-09" and m["name_match"] is True
    other = attachments.assess(vision.parse(doc(**MEDICAL)), "陳冠宇", TODAY)
    assert other["name_match"] is False and any("不符" in w for w in other["warnings"])
    late = attachments.assess(vision.parse(doc(doc_type="death_certificate", names=["林老先生"], event_date="2026-07-01")),
                              "林佳穎", TODAY)
    assert late["name_match"] is None and any("百日" in w for w in late["warnings"])
    wed = attachments.assess(vision.parse(doc(doc_type="marriage_certificate", names=["林佳穎", "張書豪"],
                                              event_date="2026-11-01")), "林佳穎", TODAY)
    assert wed["registration_date"] == "2026-11-01" and "2027-02-01" in wed["facts"][0]
    assert attachments.summary(m) == "診斷證明・建議休養 2026-11-09～2026-11-11・姓名相符"


# ── 依文件請假 ───────────────────────────────────────────

def upload(db, p) -> str:
    return attachments.save(db, p, jpeg(), "診斷證明.jpg")["id"]


def test_certificate_becomes_linked_sick_draft(db, as_user):
    p = as_user("grace.lin")
    aid = upload(db, p)
    llm = VisionLLM([doc(**MEDICAL),
                     [("draft_leave_request", {"leave_type": "sick", "start": "2026-11-09", "end": "2026-11-11"})],
                     "已依診斷證明建立病假草稿，請在卡片上按「確認送出」。"])
    r = run_chat(db, llm, p, "幫我依這份文件請假", attachment_ids=[aid])
    assert llm.calls[0]["tools"] == []  # 讀圖這一步沒有任何工具可呼叫
    assert r.routed_by == "attachment" and r.intent == "action.leave_request"
    assert "不可信的資料" in llm.calls[1]["dynamic"] and "2026-11-09 至 2026-11-11" in llm.calls[1]["dynamic"]
    card = r.drafts[0]
    assert card["hours"] == 24 and card["attachments"][0]["summary"].endswith("姓名相符")
    assert db.execute(text("SELECT request_id FROM leave_attachments WHERE id = :i"), {"i": aid}).scalar() == card["draft_id"]
    meta = db.execute(text("SELECT meta FROM messages WHERE conversation_id = :c AND role = 'user'"),
                      {"c": r.conversation_id}).scalar()
    assert meta == {"attachments": [{"id": aid, "name": "診斷證明.jpg"}]}

    leave.submit(db, p, card["draft_id"])
    boss = db.execute(text("""SELECT u.username FROM employees g JOIN users u ON u.employee_id = g.manager_id
                               WHERE g.id = :e"""), {"e": p.emp_id}).scalar()
    row = next(x for x in leave.pending_approvals(db, as_user(boss)) if x["id"] == card["draft_id"])
    assert row["attachments"] == [{"summary": card["attachments"][0]["summary"]}]  # 主管只拿到摘要，沒有附件 id
    assert row["reason"] is None


def test_instructions_inside_image_are_flagged_not_followed(db, as_user):
    p = as_user("grace.lin")
    aid = upload(db, p)
    llm = VisionLLM([doc(**MEDICAL, contains_instructions=True),
                     [("draft_leave_request", {"leave_type": "sick", "start": "2026-11-09", "end": "2026-11-11"})],
                     "已建立病假草稿，請確認後送出。"])
    run_chat(db, llm, p, "幫我依這份文件請假", attachment_ids=[aid])
    assert llm.calls[0]["tools"] == []
    assert "已忽略" in llm.calls[1]["dynamic"]
    logged = db.execute(text("SELECT tools FROM audit_log ORDER BY id DESC LIMIT 1")).scalar()
    assert {"attachments": [{"doc_type": "medical_certificate", "contains_instructions": True}]} in logged


def test_someone_elses_attachment_is_invisible(db, as_user):
    aid = upload(db, as_user("grace.lin"))
    kevin = as_user("kevin.chen")
    assert attachments.owned(db, kevin, [aid]) == []
    card = leave.draft(db, kevin, "personal", "2026-12-14", "2026-12-14", attachment_ids=[aid])
    assert "attachments" not in card
    assert db.execute(text("SELECT request_id FROM leave_attachments WHERE id = :i"), {"i": aid}).scalar() is None


def test_marriage_certificate_allows_provisional_draft_and_opens_ticket(db, as_user):
    p = as_user("grace.lin")
    with pytest.raises(leave.LeaveError, match="結婚登記日"):
        leave.draft(db, p, "marriage", "2026-12-14", "2026-12-18")
    aid = upload(db, p)
    fields = vision.parse(doc(doc_type="marriage_certificate", names=["林佳穎", "張書豪"], event_date="2026-11-01"))
    attachments.set_extracted(db, aid, {**fields, **attachments.assess(fields, "林佳穎", TODAY)})
    card = leave.draft(db, p, "marriage", "2026-12-14", "2026-12-18", attachment_ids=[aid])
    assert card["hours"] == 40 and any("取自上傳文件" in w for w in card["warnings"])
    leave.submit(db, p, card["draft_id"])
    summary = db.execute(text("SELECT summary FROM tickets ORDER BY id DESC LIMIT 1")).scalar()
    assert f"#{card['draft_id']}" in summary and "2026-11-01" in summary


def test_model_without_vision_marks_document_unreadable(db, as_user):
    class NoVision(VisionLLM):
        def image_user(self, t, image, media_type):
            raise ValueError("model does not support images")

    p = as_user("grace.lin")
    aid = upload(db, p)
    # 沒呼叫工具會被提醒一次（請假意圖），兩次都回同一句
    llm = NoVision(["文件無法辨識，請重新拍攝，或告訴我要請哪幾天。"] * 2)
    r = run_chat(db, llm, p, "幫我依這份文件請假", attachment_ids=[aid])
    assert r.answer.startswith("文件無法辨識")
    assert "無法辨識為診斷證明" in llm.calls[0]["dynamic"]
