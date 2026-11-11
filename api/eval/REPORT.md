# 評測報告（20261111-1338）

評測集：eval/cases.yaml，43 題 × 每題 2 次；judge 模型：claude-sonnet-5-5（校準見 CALIBRATION.md）

## 各模型總表

| 模型 | 題數 | 通過率 | 數字正確率 | 口徑正確率（judge） | 越權洩漏率 | 平均延遲 | 平均成本 USD |
|---|---|---|---|---|---|---|---|
| claude-haiku-5-5 | 86 | 100% | 100% | 100% | 0% | 4.7s | 0.0005 |
| claude-sonnet-5-5 | 86 | 100% | 100% | 100% | 0% | 5.0s | 0.0072 |

## 依意圖

| 意圖 | claude-haiku-5-5 | claude-sonnet-5-5 |
|---|---|---|
| action.leave_request | 100%（22） | 100%（22） |
| analysis.team | 100%（4） | 100%（4） |
| escalate | 100%（4） | 100%（4） |
| lookup.benefits | 100%（2） | 100%（2） |
| lookup.leave_balance | 100%（16） | 100%（16） |
| lookup.overtime_pay | 100%（6） | 100%（6） |
| lookup.payroll | 100%（18） | 100%（18） |
| policy.qa | 100%（14） | 100%（14） |

## 未通過的題目

