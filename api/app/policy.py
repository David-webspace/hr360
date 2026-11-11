"""權限邊界：誰可以看誰的哪一級資料。

規則寫成 SQL 條件（目標員工必須落在「可見集合」內），不是先查到資料再用 if 判斷；
少寫一個條件會直接查不到，而不是悄悄洩漏。

  S0 公開：姓名、單位、職稱、分機 ——所有登入者（不含系統管理員）
  S1 內部：請假／加班時數彙總 ——本人、主管（部屬）、HRBP（負責範圍）
  S2 個人：假單明細、打卡、特休餘額 ——同 S1
  S3 機密：薪資、加班費金額、保費、病假原因 ——本人、薪酬人員
"""

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.auth import Principal

DENIED = "無權限或查無此人"


class PolicyDenied(Exception):
    """對外一律回 DENIED；內部原因只進稽核。「查無此人」與「無權限」不區分，避免枚舉。"""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


class AmbiguousEmployee(PolicyDenied):
    """權限範圍內有多位同名員工。候選人只取自可見範圍，告訴使用者不會洩漏範圍外的人。"""

    def __init__(self, candidates: list[dict]) -> None:
        super().__init__("ambiguous")
        self.candidates = candidates


LEVEL_RANK = {"S0": 0, "S1": 1, "S2": 2, "S3": 3}


def visible_paths(p: Principal, level: str) -> tuple[str, ...] | None:
    """回傳可見的單位路徑前綴；None 表示全公司。本人永遠可見，另外處理。"""
    rank = LEVEL_RANK[level]
    if "sysadmin" in p.roles and p.emp_id is None:
        return ()
    if rank == 0:
        return None
    if rank == 3:
        return None if p.is_payroll else ()
    return tuple(p.managed_paths) + tuple(p.hrbp_paths)


def scope_sql(p: Principal, level: str, alias: str = "e") -> tuple[str, dict]:
    paths = visible_paths(p, level)
    me = p.emp_id or -1
    if paths is None:
        return "TRUE", {}
    if not paths:
        return f"{alias}.id = :me_id", {"me_id": me}
    conds = " OR ".join(f"o_scope.path LIKE :sp{i}" for i in range(len(paths)))
    cond = (f"({alias}.id = :me_id OR EXISTS (SELECT 1 FROM org_units o_scope "
            f"WHERE o_scope.id = {alias}.org_unit_id AND ({conds})))")
    return cond, {"me_id": me, **{f"sp{i}": f"{path}%" for i, path in enumerate(paths)}}


def resolve_employee(db: Session, p: Principal, who: str | None, level: str) -> dict:
    """把「誰」（姓名、員工編號，或省略＝本人）解析成員工，同時套用權限範圍。"""
    # 不把「自己的名字」當成查本人：主管和部屬同名時，會查錯人
    if not who or who.strip() in ("me", "self", "本人", "我"):
        if p.emp_id is None:
            raise PolicyDenied("no_employee_record")
        who_cond, params = "e.id = :target", {"target": p.emp_id}
    else:
        who_cond, params = "(e.name = :target OR e.emp_no = :target)", {"target": who.strip()}
    scope, sp = scope_sql(p, level)
    rows = db.execute(text(f"""
        SELECT e.id, e.emp_no, e.name, e.hire_date, e.seniority_start_date, e.birth_date, e.status, e.termination_date,
               e.manager_id, e.schedule_id, e.org_unit_id, o.name AS unit_name, e.title
        FROM employees e JOIN org_units o ON o.id = e.org_unit_id
        WHERE {who_cond} AND {scope}
    """), {**params, **sp}).mappings().all()
    if not rows:
        raise PolicyDenied("out_of_scope_or_not_found")
    if len(rows) > 1:
        raise AmbiguousEmployee([{"emp_no": r["emp_no"], "name": r["name"], "unit": r["unit_name"], "title": r["title"]}
                                 for r in rows])
    return dict(rows[0])
