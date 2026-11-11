"""擬真但不對應真人的個資產生。"""

import random

# 依內政部常見姓氏排序取前 40，權重近似分布
SURNAMES = [
    ("陳", "Chen", 11.1), ("林", "Lin", 8.3), ("黃", "Huang", 6.0), ("張", "Chang", 5.3), ("李", "Lee", 5.1),
    ("王", "Wang", 4.1), ("吳", "Wu", 4.0), ("劉", "Liu", 3.2), ("蔡", "Tsai", 2.9), ("楊", "Yang", 2.7),
    ("許", "Hsu", 2.3), ("鄭", "Cheng", 1.9), ("謝", "Hsieh", 1.8), ("郭", "Kuo", 1.7), ("洪", "Hung", 1.6),
    ("曾", "Tseng", 1.5), ("邱", "Chiu", 1.5), ("廖", "Liao", 1.4), ("賴", "Lai", 1.4), ("周", "Chou", 1.3),
    ("徐", "Hsu", 1.2), ("蘇", "Su", 1.2), ("葉", "Yeh", 1.1), ("莊", "Chuang", 1.1), ("呂", "Lu", 1.0),
    ("江", "Chiang", 1.0), ("何", "Ho", 0.9), ("蕭", "Hsiao", 0.9), ("羅", "Lo", 0.9), ("高", "Kao", 0.8),
    ("潘", "Pan", 0.6), ("簡", "Chien", 0.6), ("朱", "Chu", 0.6), ("鍾", "Chung", 0.6), ("彭", "Peng", 0.6),
    ("游", "Yu", 0.6), ("詹", "Chan", 0.5), ("胡", "Hu", 0.5), ("施", "Shih", 0.5), ("沈", "Shen", 0.5),
]

MALE_GIVEN = [
    "冠宇", "宇翔", "承恩", "柏翰", "家豪", "俊傑", "建宏", "志明", "宗翰", "冠廷", "彥廷", "承翰", "哲瑋", "品睿",
    "子豪", "育霖", "柏宇", "宇軒", "孟哲", "信宏", "嘉偉", "明哲", "偉倫", "俊宏", "政宏", "智凱", "書豪", "國峰",
    "立誠", "昱廷", "宏毅", "建良", "文彬", "啟文", "士傑", "耀中", "柏諺", "裕翔", "振宇", "家銘",
]
FEMALE_GIVEN = [
    "佳穎", "雅婷", "怡君", "欣怡", "淑芬", "佩珊", "婉婷", "怡婷", "雅雯", "詩涵", "郁婷", "宜蓁", "思妤", "筱涵",
    "雅筑", "玉婷", "家瑜", "靜宜", "惠雯", "美玲", "淑惠", "佳蓉", "芳瑜", "曉薇", "語彤", "品妍", "瑋婷", "姿穎",
    "怡萱", "子晴", "佳慧", "雅琪", "秀玲", "麗華", "宛儒", "庭瑄", "以柔", "瑞芬", "心瑜", "若涵",
]
MALE_EN = ["Kevin", "Jason", "Eric", "Allen", "Jack", "Vincent", "Leo", "Ryan", "Ken", "Andy", "Steven", "Sean",
           "Daniel", "Tony", "Brian", "Peter", "Howard", "Frank", "Henry", "Max", "Ian", "Ray", "Alex", "Gary"]
FEMALE_EN = ["Amy", "Cindy", "Grace", "Vivian", "Tina", "Joyce", "Irene", "Wendy", "Iris", "Annie", "Sharon",
             "Emily", "Claire", "Sandy", "Peggy", "Ivy", "Doris", "Fiona", "Helen", "Jenny", "Ruby", "Zoe", "Mia"]

# (身分證字母, 縣市, 區)
REGIONS = [
    ("A", "臺北市", ["內湖區", "松山區", "大安區", "文山區", "南港區", "士林區"]),
    ("F", "新北市", ["板橋區", "新店區", "汐止區", "中和區", "三重區", "林口區"]),
    ("H", "桃園市", ["桃園區", "中壢區", "龜山區"]),
    ("J", "新竹縣", ["竹北市", "竹東鎮", "湖口鄉"]),
    ("O", "新竹市", ["東區", "北區"]),
    ("B", "臺中市", ["西屯區", "北屯區"]),
    ("E", "高雄市", ["左營區", "三民區"]),
]
ROADS = ["晴川路", "雲岫街", "曜光路", "青楓街", "鳴泉路", "朝嵐街", "澄心路", "汀蘭街", "映月路", "松濤街", "望霞路", "竹影街"]

_LETTER_CODE = {c: v for c, v in zip("ABCDEFGHJKLMNPQRSTUVXYWZIO", range(10, 36))}


def _id_checksum(body: str) -> int:
    n = _LETTER_CODE[body[0]]
    digits = [n // 10, n % 10] + [int(c) for c in body[1:]]
    weights = [1, 9, 8, 7, 6, 5, 4, 3, 2, 1]
    return (10 - sum(d * w for d, w in zip(digits, weights)) % 10) % 10


def fake_national_id(rng: random.Random, letter: str, gender: str) -> str:
    """格式正確，但檢查碼刻意錯開 1，任何驗證都不會通過，保證不對應真人。"""
    body = letter + ("1" if gender == "M" else "2") + "".join(str(rng.randint(0, 9)) for _ in range(7))
    return body + str((_id_checksum(body) + 1) % 10)


def is_valid_national_id(nid: str) -> bool:
    return _id_checksum(nid[:9]) == int(nid[9])


def pick_name(rng: random.Random, gender: str, used: set[str]) -> tuple[str, str, str]:
    while True:
        s, s_en, _ = rng.choices(SURNAMES, weights=[w for *_, w in SURNAMES])[0]
        given = rng.choice(MALE_GIVEN if gender == "M" else FEMALE_GIVEN)
        if s + given not in used:
            used.add(s + given)
            en = rng.choice(MALE_EN if gender == "M" else FEMALE_EN)
            return s + given, en, s_en


def address(rng: random.Random) -> tuple[str, str]:
    letter, city, districts = rng.choices(REGIONS, weights=[22, 25, 10, 18, 12, 7, 6])[0]
    return letter, f"{city}{rng.choice(districts)}{rng.choice(ROADS)}{rng.randint(1, 3)}段{rng.randint(2, 288)}號{rng.randint(2, 15)}樓"


def mobile(rng: random.Random) -> str:
    # 0900 字頭未核配給一般門號，避免產生到真實手機號碼
    return f"0900-{rng.randint(100, 999)}-{rng.randint(100, 999)}"
