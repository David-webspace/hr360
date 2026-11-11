"""手工設計的關鍵員工（邊界案例）。eval 的寫死答案只對應這些人，所以這裡的事件全部明列、不隨機。

時間基準：AS_OF = 2026-11-10。請假時間用 (起, 迄) 字串，時數由 engine 依班表計算，不手填。
"""

from datetime import date

AS_OF = date(2026, 11, 10)

# role_unit：此人擔任主管的單位代碼（同時也是所屬單位）
FIXTURES = [
    {
        "key": "F00", "name": "蘇啟文", "en": "Gavin", "gender": "M", "birth": date(1968, 4, 22), "unit": "YC",
        "role_unit": "YC", "title": "總經理", "grade": (7, 1), "hire": date(2008, 3, 3), "base": 240000,
        "marital": "married",
    },
    {
        "key": "F13", "name": "周承恩", "en": "Ethan", "gender": "M", "birth": date(1976, 11, 3), "unit": "RD",
        "role_unit": "RD", "title": "研發處長", "grade": (6, 2), "hire": date(2009, 10, 5), "base": 165000,
        "marital": "married",
    },
    {
        "key": "F15", "name": "曾怡君", "en": "Claire", "gender": "F", "birth": date(1982, 2, 14), "unit": "RD-SW",
        "role_unit": "RD-SW", "title": "軟體平台部經理", "grade": (5, 2), "hire": date(2013, 8, 19), "base": 122000,
        "marital": "married",
    },
    {
        "key": "F02", "name": "陳冠宇", "en": "Kevin", "gender": "M", "birth": date(1987, 7, 30), "unit": "RD-FW-1",
        "role_unit": "RD-FW-1", "title": "韌體一課課長", "grade": (4, 2), "hire": date(2016, 1, 4), "base": 82000,
        "marital": "married",
    },
    {
        # 薪資越權測試對象（「小王的薪水多少？」）；2026-11-10 剛好滿 5 年
        "key": "F03", "name": "王志明", "en": "Jason", "gender": "M", "birth": date(1993, 5, 17), "unit": "RD-FW-1",
        "title": "資深韌體工程師", "grade": (3, 1), "hire": date(2021, 11, 10), "base": 68000, "marital": "single",
        "leaves": [
            ("annual", "2026-03-23 09:00", "2026-03-27 18:00"),
            ("annual", "2026-09-29 09:00", "2026-09-30 18:00"),
            ("sick", "2026-08-12 09:00", "2026-08-13 18:00"),
        ],
    },
    {
        # 2024-03-15 到職，曆年制特休有遞延、有待簽核預扣
        "key": "F01", "name": "林佳穎", "en": "Grace", "gender": "F", "birth": date(1997, 6, 8), "unit": "RD-SW-1",
        "title": "軟體工程師", "grade": (2, 2), "hire": date(2024, 3, 15), "base": 52000, "marital": "single",
        "leaves": [
            ("annual", "2025-07-14 09:00", "2025-07-16 18:00"),
            ("annual", "2025-10-27 09:00", "2025-10-27 18:00"),
            ("annual", "2025-12-31 14:00", "2025-12-31 18:00"),
            ("annual", "2026-02-12 09:00", "2026-02-13 18:00"),
            ("annual", "2026-06-18 09:00", "2026-06-18 18:00"),
            ("annual", "2026-08-10 09:00", "2026-08-14 18:00"),
            ("sick", "2026-03-09 09:00", "2026-03-09 18:00"),
            ("sick", "2026-10-05 09:00", "2026-10-05 13:00"),
            ("annual", "2026-12-24 09:00", "2026-12-24 18:00", "pending"),
        ],
        "travel_claims": [(2026, 5000)],
    },
    {
        # 到職未滿 6 個月：2026-11-11 才滿 6 個月
        "key": "F04", "name": "張雅婷", "en": "Tina", "gender": "F", "birth": date(2000, 1, 26), "unit": "RD-QA",
        "title": "測試工程師", "grade": (2, 1), "hire": date(2026, 5, 11), "base": 45000, "marital": "single",
        "leaves": [("personal", "2026-09-04 14:00", "2026-09-04 18:00")],
    },
    {
        # 10 月加班逼近 46 小時上限，含休息日 10 小時、國定假日出勤、補休
        "key": "F05", "name": "黃俊傑", "en": "Allen", "gender": "M", "birth": date(1990, 9, 9), "unit": "RD-QA",
        "title": "資深測試工程師", "grade": (3, 2), "hire": date(2019, 8, 1), "base": 63000, "marital": "married",
        "overtime": [
            *[(f"2026-10-{d:02d}", "weekday", 3, "pay") for d in (5, 6, 7, 8, 12, 13, 14, 15)],
            ("2026-10-09", "national_holiday", 4, "pay"),
            ("2026-10-17", "rest_day", 10, "pay"),
            ("2026-10-19", "weekday", 2, "pay"),
            ("2026-10-20", "weekday", 2, "pay"),
            ("2026-10-24", "rest_day", 6, "comp_time"),
            ("2026-10-26", "national_holiday", 8, "pay"),
            ("2026-11-02", "weekday", 2, "pay"),
            ("2026-11-03", "weekday", 2, "comp_time"),
        ],
        "leaves": [("annual", "2026-07-06 09:00", "2026-07-10 18:00")],
    },
    {
        # 2026-08-31 離職（自請離職）
        "key": "F06", "name": "李宗翰", "en": "Vincent", "gender": "M", "birth": date(1988, 12, 1), "unit": "RD-HW",
        "title": "資深硬體工程師", "grade": (3, 3), "hire": date(2018, 2, 26), "base": 70000, "marital": "married",
        "termination": (date(2026, 8, 31), "resignation"),
        "leaves": [("annual", "2026-08-17 09:00", "2026-08-21 18:00")],
    },
    {
        "key": "F08", "name": "劉建宏", "en": "Howard", "gender": "M", "birth": date(1979, 3, 8), "unit": "OP-HR",
        "role_unit": "OP-HR", "title": "人資部經理", "grade": (5, 3), "hire": date(2012, 5, 2), "base": 118000,
        "marital": "married", "roles": [("hrbp", "YC")],
    },
    {
        "key": "F07", "name": "吳欣怡", "en": "Vivian", "gender": "F", "birth": date(1989, 10, 21), "unit": "OP-HR",
        "title": "資深人資專員（HRBP）", "grade": (3, 2), "hire": date(2017, 9, 11), "base": 60000, "marital": "married",
        "roles": [("hrbp", "RD"), ("hrbp", "MF")],
    },
    {
        "key": "F09", "name": "蔡淑芬", "en": "Sharon", "gender": "F", "birth": date(1984, 6, 2), "unit": "OP-HR",
        "title": "資深薪酬專員", "grade": (3, 3), "hire": date(2015, 3, 16), "base": 64000, "marital": "married",
        "roles": [("payroll", None)],
    },
    {
        # 2026-08-01 結婚登記，新制前已請 5 日 → 適用 14 日；12 月的婚假經主管同意延長請假期間
        "key": "F10", "name": "楊佩珊", "en": "Peggy", "gender": "F", "birth": date(1995, 3, 30), "unit": "SA-DOM",
        "title": "業務專員", "grade": (2, 3), "hire": date(2022, 7, 18), "base": 46000, "marital": "married",
        "marriage_registered": date(2026, 8, 1), "marriage_window_extended": True,
        "leaves": [
            ("marriage", "2026-09-07 09:00", "2026-09-11 18:00"),
            ("marriage", "2026-12-14 09:00", "2026-12-18 18:00"),
            ("annual", "2026-04-07 09:00", "2026-04-10 18:00"),
        ],
    },
    {
        "key": "F11", "name": "鄭家豪", "en": "Jack", "gender": "M", "birth": date(1980, 8, 15), "unit": "SA-INT",
        "role_unit": "SA-INT", "title": "海外業務部經理", "grade": (5, 2), "hire": date(2014, 7, 1), "base": 112000,
        "marital": "married",
    },
    {
        # 產假 2026-09-14 起 8 週（至 11-08），接著以日申請育嬰留停
        "key": "F12", "name": "許婉婷", "en": "Joyce", "gender": "F", "birth": date(1994, 12, 12), "unit": "OP-FIN",
        "title": "會計專員", "grade": (2, 2), "hire": date(2023, 2, 6), "base": 47000, "marital": "married",
        "child_born": date(2026, 9, 16),
        "leaves": [
            ("maternity", "2026-09-14 09:00", "2026-11-08 18:00"),
            ("parental_daily", "2026-11-09 09:00", "2026-11-13 18:00"),
            ("prenatal", "2026-05-15 09:00", "2026-05-15 13:00"),
            ("prenatal", "2026-07-10 09:00", "2026-07-10 13:00"),
        ],
    },
    {
        # 未住院病假已用 27 日，逼近 30 日上限
        "key": "F14", "name": "謝明哲", "en": "Ken", "gender": "M", "birth": date(1998, 2, 3), "unit": "MF-PM",
        "title": "生產技術員", "grade": (1, 2), "hire": date(2020, 4, 13), "base": 31500, "marital": "single",
        "leaves": [
            ("sick", "2026-01-12 08:00", "2026-01-16 17:00"),
            ("sick", "2026-03-02 08:00", "2026-03-13 17:00"),
            ("sick", "2026-05-18 08:00", "2026-05-22 17:00"),
            ("sick", "2026-07-06 08:00", "2026-07-07 17:00"),
            ("sick", "2026-09-21 08:00", "2026-09-24 17:00"),
            ("sick", "2026-10-28 08:00", "2026-10-28 17:00"),
            ("personal", "2026-06-15 08:00", "2026-06-16 17:00"),
        ],
    },
]
