"""組織架構與各單位人員組成。"""

from dataclasses import dataclass


@dataclass(frozen=True)
class UnitSpec:
    code: str
    name: str
    level: str  # company / center / department / section
    parent: str | None
    site: str
    staff: int = 0  # 不含主管的一般人員數
    family: str = ""  # 職務族群，決定職稱、專業加給、性別比例
    head_title: str = ""


UNITS = [
    UnitSpec("YC", "曜川科技股份有限公司", "company", None, "taipei", head_title="總經理"),
    UnitSpec("GMO", "總經理室", "department", "YC", "taipei", 1, "gmo"),
    UnitSpec("RD", "研發中心", "center", "YC", "hsinchu", head_title="研發處長"),
    UnitSpec("RD-FW", "韌體部", "department", "RD", "hsinchu", 0, "fw", "韌體部經理"),
    UnitSpec("RD-FW-1", "韌體一課", "section", "RD-FW", "hsinchu", 8, "fw", "韌體一課課長"),
    UnitSpec("RD-FW-2", "韌體二課", "section", "RD-FW", "hsinchu", 7, "fw", "韌體二課課長"),
    UnitSpec("RD-SW", "軟體平台部", "department", "RD", "hsinchu", 0, "sw", "軟體平台部經理"),
    UnitSpec("RD-SW-1", "雲端平台課", "section", "RD-SW", "hsinchu", 8, "sw", "雲端平台課課長"),
    UnitSpec("RD-SW-2", "應用開發課", "section", "RD-SW", "hsinchu", 8, "sw", "應用開發課課長"),
    UnitSpec("RD-HW", "硬體設計部", "department", "RD", "hsinchu", 12, "hw", "硬體設計部經理"),
    UnitSpec("RD-QA", "測試驗證部", "department", "RD", "hsinchu", 11, "qa", "測試驗證部經理"),
    UnitSpec("SA", "業務中心", "center", "YC", "taipei", head_title="業務處長"),
    UnitSpec("SA-DOM", "國內業務部", "department", "SA", "taipei", 11, "sales", "國內業務部經理"),
    UnitSpec("SA-INT", "海外業務部", "department", "SA", "taipei", 10, "sales_int", "海外業務部經理"),
    UnitSpec("SA-FAE", "技術支援部", "department", "SA", "taipei", 9, "fae", "技術支援部經理"),
    UnitSpec("OP", "營運中心", "center", "YC", "taipei", head_title="營運處長"),
    UnitSpec("OP-FIN", "財務部", "department", "OP", "taipei", 7, "fin", "財務部經理"),
    UnitSpec("OP-HR", "人資部", "department", "OP", "taipei", 5, "hr", "人資部經理"),
    UnitSpec("OP-ADM", "行政總務部", "department", "OP", "taipei", 4, "adm", "行政總務部經理"),
    UnitSpec("OP-IT", "資訊部", "department", "OP", "taipei", 6, "it", "資訊部經理"),
    UnitSpec("OP-PUR", "採購部", "department", "OP", "taipei", 5, "pur", "採購部經理"),
    UnitSpec("MF", "製造中心", "center", "YC", "hsinchu", head_title="製造處長"),
    UnitSpec("MF-PM", "生產管理部", "department", "MF", "hsinchu", 30, "mfg", "生產管理部經理"),
    UnitSpec("MF-QC", "品保部", "department", "MF", "hsinchu", 10, "qc", "品保部經理"),
]

UNIT_BY_CODE = {u.code: u for u in UNITS}

# 職務族群：(職稱基底, 男性比例, 職等分布 {等: 權重}, 專業加給鍵, 可遠距)
FAMILIES = {
    "gmo": ("特別助理", 0.4, {3: 1}, None, False),
    "fw": ("韌體工程師", 0.82, {1: 5, 2: 45, 3: 38, 4: 12}, "rd", True),
    "sw": ("軟體工程師", 0.72, {1: 5, 2: 48, 3: 35, 4: 12}, "rd", True),
    "hw": ("硬體工程師", 0.8, {1: 5, 2: 42, 3: 40, 4: 13}, "rd", True),
    "qa": ("測試工程師", 0.62, {1: 12, 2: 50, 3: 30, 4: 8}, "rd", True),
    "sales": ("業務專員", 0.55, {2: 60, 3: 32, 4: 8}, None, False),
    "sales_int": ("海外業務專員", 0.5, {2: 55, 3: 35, 4: 10}, None, False),
    "fae": ("應用工程師", 0.75, {2: 55, 3: 35, 4: 10}, "rd", False),
    "fin": ("會計專員", 0.2, {1: 10, 2: 55, 3: 30, 4: 5}, None, True),
    "hr": ("人資專員", 0.2, {2: 50, 3: 50}, None, True),
    "adm": ("行政專員", 0.3, {1: 40, 2: 50, 3: 10}, None, True),
    "it": ("系統工程師", 0.75, {2: 50, 3: 40, 4: 10}, "it", True),
    "pur": ("採購專員", 0.4, {1: 10, 2: 60, 3: 30}, None, True),
    "mfg": ("生產技術員", 0.5, {1: 65, 2: 28, 3: 7}, None, False),
    "qc": ("品保工程師", 0.55, {1: 10, 2: 55, 3: 30, 4: 5}, "quality", False),
}

GRADE_PREFIX = {1: "助理", 2: "", 3: "資深", 4: "主任"}


def staff_title(family: str, grade: int) -> str:
    base = FAMILIES[family][0]
    if family == "mfg":
        return {1: "生產技術員", 2: "生管專員", 3: "資深生管專員"}[grade]
    return GRADE_PREFIX[grade] + base
