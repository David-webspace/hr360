"""證明文件：上傳驗證與儲存、權限、以及「模型讀出的欄位」與規定的程式比對。

模型讀出的日期、天數一律只當建議：真正的時數、餘額與規定檢查仍由 leave._validate 重算。
"""

import io
import json
import uuid
from datetime import date, timedelta
from pathlib import Path

from PIL import Image, ImageOps, UnidentifiedImageError
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.auth import Principal
from app.config import settings
from app.engine.leave import marriage_leave_days
from app.policy import PolicyDenied, resolve_employee

MAX_BYTES = 5 * 1024 * 1024
MAX_SIDE = 1600
# 解壓縮炸彈：小檔案宣稱超大尺寸，解碼時吃光記憶體；超過就讓 Pillow 直接拒絕
Image.MAX_IMAGE_PIXELS = 40_000_000
ALLOWED_FORMATS = {"JPEG", "PNG", "WEBP"}

DOC_LABEL = {"medical_certificate": "診斷證明", "death_certificate": "死亡證明／訃聞",
             "marriage_certificate": "結婚證明", "other": "無法辨識的文件"}
DOC_LEAVE = {"medical_certificate": "sick", "death_certificate": "bereavement", "marriage_certificate": "marriage"}
BEREAVEMENT_WINDOW_DAYS = 100


class AttachmentError(ValueError):
    pass


def _path(aid: str) -> Path:
    return Path(settings.upload_dir) / f"{aid}.jpg"


def save(db: Session, p: Principal, data: bytes, name: str) -> dict:
    if len(data) > MAX_BYTES:
        raise AttachmentError("檔案超過 5MB，請壓縮或重新拍攝")
    # 格式看檔案實際內容，不看副檔名或前端宣稱的 content-type
    try:
        img = Image.open(io.BytesIO(data))
        fmt = img.format
        img.load()
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError):
        raise AttachmentError("無法讀取這個檔案，請上傳 JPG、PNG 或 WebP 圖片") from None
    if fmt not in ALLOWED_FORMATS:
        raise AttachmentError("只接受 JPG、PNG 或 WebP 圖片")
    # 重新編碼成 JPEG：去掉 EXIF（含拍攝地點 GPS）與任何夾帶在原檔裡的資料
    img = ImageOps.exif_transpose(img).convert("RGB")
    img.thumbnail((MAX_SIDE, MAX_SIDE))
    out = io.BytesIO()
    img.save(out, "JPEG", quality=85)
    # 儲存檔名用系統產生的 uuid；使用者給的檔名只拿來顯示，不碰檔案路徑
    aid = uuid.uuid4().hex
    _path(aid).parent.mkdir(parents=True, exist_ok=True)
    _path(aid).write_bytes(out.getvalue())
    display = Path(name or "").name[:200] or "文件.jpg"
    db.execute(text("""INSERT INTO leave_attachments (id, user_id, emp_id, original_name, size_bytes)
                       VALUES (:i, :u, :e, :n, :s)"""),
               {"i": aid, "u": p.user_id, "e": p.emp_id, "n": display, "s": out.tell()})
    db.commit()
    return {"id": aid, "name": display}


def image_bytes(aid: str) -> bytes:
    return _path(aid).read_bytes()


def owned(db: Session, p: Principal, ids: list[str]) -> list[dict]:
    """本人上傳、且還沒附到其他假單的附件；別人的 id 直接查不到（條件寫在 SQL）。"""
    if not ids:
        return []
    rows = db.execute(text("""SELECT id, original_name, extracted FROM leave_attachments
                              WHERE id = ANY(:ids) AND user_id = :u AND request_id IS NULL ORDER BY created_at"""),
                      {"ids": ids, "u": p.user_id}).mappings().all()
    return [dict(r) for r in rows]


def viewable(db: Session, p: Principal, aid: str) -> str:
    """原圖依 S3 規則（本人、薪酬人員）；主管與 HRBP 只看文字摘要。查不到與無權限回同一個錯誤。"""
    row = db.execute(text("""SELECT a.id, a.user_id, e.emp_no FROM leave_attachments a
                             LEFT JOIN employees e ON e.id = a.emp_id WHERE a.id = :i"""), {"i": aid}).mappings().one_or_none()
    if row is None:
        raise PolicyDenied("attachment_not_found")
    if row["user_id"] != p.user_id:
        if not row["emp_no"]:
            raise PolicyDenied("attachment_not_owned")
        resolve_employee(db, p, row["emp_no"], "S3")
    return row["id"]


def set_extracted(db: Session, aid: str, extracted: dict) -> None:
    db.execute(text("UPDATE leave_attachments SET extracted = CAST(:x AS jsonb) WHERE id = :i"),
               {"i": aid, "x": json.dumps(extracted, ensure_ascii=False, default=str)})
    db.commit()


def link(db: Session, p: Principal, ids: list[str], rid: int) -> None:
    if ids:
        db.execute(text("""UPDATE leave_attachments SET request_id = :r
                           WHERE id = ANY(:ids) AND user_id = :u AND request_id IS NULL"""),
                   {"r": rid, "ids": ids, "u": p.user_id})


def _d(v) -> date | None:
    try:
        return date.fromisoformat(v) if v else None
    except (TypeError, ValueError):
        return None


def assess(fields: dict, emp_name: str, on: date) -> dict:
    """模型讀出的欄位 → 建議假別、起訖日、提醒。純函式，不碰資料庫，方便測試。"""
    doc = fields.get("doc_type", "other")
    names = fields.get("names") or []
    out: dict = {"doc_type": doc, "doc_label": DOC_LABEL.get(doc, DOC_LABEL["other"]),
                 "suggested_leave_type": DOC_LEAVE.get(doc), "facts": [], "warnings": [], "name_match": None}
    if doc in ("medical_certificate", "marriage_certificate") and names:
        out["name_match"] = emp_name in names
        if not out["name_match"]:
            out["warnings"].append(f"文件上的姓名（{'、'.join(names)}）與申請人 {emp_name} 不符，主管與人資會看到這個提醒")
    if fields.get("contains_instructions"):
        out["warnings"].append("文件上出現要求系統執行動作的文字，已忽略，只採用文件欄位")

    if doc == "medical_certificate":
        s, e, n = _d(fields.get("rest_start")), _d(fields.get("rest_end")), fields.get("rest_days")
        if s and not e and n:
            e = s + timedelta(days=int(n) - 1)
        if s and e and e >= s:
            out.update(suggested_start=s.isoformat(), suggested_end=e.isoformat())
            out["facts"].append(f"醫囑建議休養 {s.isoformat()} 至 {e.isoformat()}" + (f"（{n} 日）" if n else ""))
            if s < on - timedelta(days=3):
                out["warnings"].append("休養起日早於 3 日前，超過補請期限的部分需洽人資")
        else:
            out["warnings"].append("讀不到醫囑的休養日期，請告訴我要請哪幾天")
    elif doc == "death_certificate":
        dd = _d(fields.get("event_date"))
        if dd:
            deadline = dd + timedelta(days=BEREAVEMENT_WINDOW_DAYS)
            out["facts"].append(f"死亡日期 {dd.isoformat()}，喪假應於 {deadline.isoformat()} 前請畢，可分次申請")
            if on > deadline:
                out["warnings"].append("已超過喪假百日請假期限，請洽人資")
        else:
            out["warnings"].append("讀不到死亡日期")
        out["facts"].append("喪假日數依與往生者的關係而定（父母、配偶 8 日；祖父母、子女、配偶之父母 6 日；曾祖父母、兄弟姊妹、配偶之祖父母 3 日），需先確認關係")
    elif doc == "marriage_certificate":
        reg = _d(fields.get("event_date"))
        if reg:
            r = marriage_leave_days(reg)
            out["registration_date"] = reg.isoformat()
            out["facts"].append(f"結婚登記日 {reg.isoformat()}（依上傳文件，待人資核對）；婚假 {int(r.value)} 日，"
                                f"應於 {r.basis['window_start']} 至 {r.basis['window_end']} 間請畢，可分次申請")
            if on > date.fromisoformat(r.basis["window_end"]):
                out["warnings"].append("已超過登記後 3 個月，需主管同意延長（最長 1 年）")
        else:
            out["warnings"].append("讀不到結婚登記日")
    else:
        out["warnings"].append("無法辨識為診斷證明、死亡證明或結婚證明，請重新拍攝清楚的照片，或直接用文字說明")
    return out


def summary(x: dict | None) -> str:
    """給主管簽核畫面的一行摘要：只用比對後的欄位，不含病名或任何醫療細節。"""
    if not x:
        return "已附文件（尚未判讀）"
    parts = [x.get("doc_label", "文件")]
    if x.get("suggested_start"):
        parts.append(f"建議休養 {x['suggested_start']}～{x['suggested_end']}")
    if x.get("registration_date"):
        parts.append(f"登記日 {x['registration_date']}（待人資核對）")
    if x.get("name_match") is not None:
        parts.append("姓名相符" if x["name_match"] else "姓名不符")
    return "・".join(parts)


def for_requests(db: Session, rids: list[int]) -> dict[int, list[dict]]:
    if not rids:
        return {}
    rows = db.execute(text("""SELECT id, request_id, original_name, extracted FROM leave_attachments
                              WHERE request_id = ANY(:r) ORDER BY created_at"""), {"r": rids}).mappings().all()
    out: dict[int, list[dict]] = {}
    for r in rows:
        out.setdefault(r["request_id"], []).append(
            {"id": r["id"], "name": r["original_name"], "summary": summary(r["extracted"]),
             "warnings": (r["extracted"] or {}).get("warnings", [])})
    return out


def registration_date(db: Session, rid: int | None, ids: list[str]) -> date | None:
    """婚假：系統沒有人資登錄的登記日時，暫用上傳結婚證明讀出的日期（送出時會開工單請人資核對）。"""
    rows = db.execute(text("""SELECT extracted FROM leave_attachments
                              WHERE (request_id = :r OR id = ANY(:ids)) AND extracted->>'doc_type' = 'marriage_certificate'"""),
                      {"r": rid or -1, "ids": ids}).scalars().all()
    return next((d for x in rows if (d := _d((x or {}).get("registration_date")))), None)
