from datetime import date

from app.company.policy import TRAVEL_SUBSIDY


def travel_entitlement(seniority_start: date, year: int) -> dict:
    jan1 = date(year, 1, 1)
    tiers = TRAVEL_SUBSIDY["tiers"]
    if seniority_start > jan1:
        months = 12 - seniority_start.month + 1
        amount = int(round(tiers[0][1] * months / 12, -2))
        return {"amount": amount, "basis": f"當年度到職：{tiers[0][1]:,} × {months}/12，四捨五入至百元"}
    years = (jan1 - seniority_start).days // 365
    amount = max(amt for y, amt in tiers if years >= y)
    return {"amount": amount, "basis": f"截至 {jan1} 年資 {years} 年 → {amount:,} 元"}
