# Skill-GS Skill Feedback Loop 進度紀錄

日期：2026-08-22
Branch：`Branch_NerdyClaush`
Repo：`F:\GitHub_Experiment\LLM-GS-team`

## 目的

本次進度是讓 Adaptive Core 不只記錄 repair outcome，而是能把 outcome 回饋到
下一次 skill ranking。這是從「重跑同一條 decision tree」往「根據經驗調整
skill selection」前進的一步。

## 新資料流

```text
Evaluator
-> Trace Attribution
-> Replanner
-> Repair Outcome
-> Adaptive Memory
-> Skill Feedback
-> Skill Ranking
```

也就是說，過去 retry 成功或失敗的 selected skill，會在下一次 ranking 時形成
分數調整。

## Feedback 規則

目前規則刻意保持簡單、可測試：

| Repair Outcome | Ranking Feedback |
|---|---|
| selected skill repair 成功 | 加分 |
| selected skill repair 失敗 | 扣分 |
| failure attribution 不同 | 不套用該 feedback |

Memory 會依照 `failure_attribution` 過濾 repair outcome，避免把不相關任務狀態的
經驗混在一起。例如 `budget_cutoff_before_key` 的經驗不會直接套到
`blocked_motion`。

## 實作狀態

| Component | 狀態 |
|---|---|
| Adaptive Memory | 已能產生 per-skill feedback summary |
| Skill Ranker | 已能讀取 feedback 並調整 `score_after` |
| Retry Loop | 已會把 memory feedback 傳進 skill ranking |
| Tests | 已補成功 feedback、失敗 feedback、retry loop integration 測試 |

## Smoke Run 觀察

使用一筆既有成功 repair outcome：

```text
selected_skill_id = karel.doorkey.navigate_forward_until_blocked.v1
failure_attribution = budget_cutoff_before_key
success = true
```

下一次 seed=0 ranking 時，top skill 會取得：

```text
repair_success_feedback_bonus=0.75
```

這代表 feedback 已經被 Skill Ranker 讀到，並實際影響 ranking score。

## 目前限制

- Feedback 目前只影響 skill ranking 分數，還沒有真的替換 DSL subtree。
- 如果候選 skill 本來差距很大，feedback 不一定會改變 top-1 skill。
- 目前 DoorKey default skill set 偏小，因此 feedback loop 的可觀察變化主要在
  score/reason，而不是大規模改變 plan structure。

## 下一步

下一步可以讓 Replanner 產生更明確的 `skill_preference` 或 `plan_patch`：

```text
blocked_motion -> prefer alternative navigation skill
looping_or_no_progress -> prefer progress guard skill
budget_cutoff_after_key -> keep skill, increase budget
```

這樣 feedback loop 就能進一步從「調整 ranking score」推進到「改變 selected skill
或 plan structure」。
