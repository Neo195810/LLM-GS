# Skill-GS Retry Budget Schedule 實驗報告

日期：2026-08-22
Branch：`Branch_NerdyClaush`
Repo：`F:\GitHub_Experiment\LLM-GS-team`

## 目的

前一輪實驗中，單純把 `max_attempts` 提高到 3 並沒有救回更多 seed。
原因是 retry attempt 仍使用同一個固定 `retry_max_steps`，例如：

```text
10 -> 20 -> 20
```

這代表第三次 attempt 只是用同樣 budget 重跑一次，無法解決真正需要 21、22
或 24 steps 的 cases。

本次加入 `retry_budget_schedule`，讓 retry budget 可以逐步放寬：

```text
10 -> 20 -> 22 -> 24
```

## 實作狀態

Adaptive retry loop 已新增：

```python
retry_budget_schedule=[20, 22, 24]
```

CLI 也支援：

```powershell
--retry-budget-schedule 20 22 24
```

若沒有提供 schedule，系統會保留原本固定 `retry_max_steps` 行為。

## 實驗設定

| Setting | Value |
|---|---:|
| seeds | 0..127 |
| initial_max_steps | 10 |
| replanner_policy | attribution_aware |
| perturbation_seed | 123 |

本次比較三組：

| Group | max_attempts | Retry Budget |
|---|---:|---|
| fixed_retry20 | 3 | 10 -> 20 -> 20 |
| fixed_retry22 | 3 | 10 -> 22 -> 22 |
| schedule_20_22_24 | 4 | 10 -> 20 -> 22 -> 24 |

實驗輸出：

```text
output/skill_gs/adaptive_schedule_compare_seed0_127_max10_summary.json
output/skill_gs/adaptive_schedule_compare_seed0_127_max10_fixed_retry20_full.json
output/skill_gs/adaptive_schedule_compare_seed0_127_max10_fixed_retry22_full.json
output/skill_gs/adaptive_schedule_compare_seed0_127_max10_schedule_20_22_24_full.json
```

## 實驗結果

| Group | Successes | Success Rate | Failed Seeds |
|---|---:|---:|---|
| fixed_retry20 | 121/128 | 0.9453125 | 1, 19, 29, 57, 65, 78, 93 |
| fixed_retry22 | 127/128 | 0.9921875 | 65 |
| schedule_20_22_24 | 128/128 | 1.0 | none |

## Attempt 分布

### fixed_retry20

| Attempt | max_steps | Attempts | Successes | Failures |
|---:|---:|---:|---:|---:|
| 1 | 10 | 128 | 14 | 114 |
| 2 | 20 | 114 | 107 | 7 |
| 3 | 20 | 7 | 0 | 7 |

### fixed_retry22

| Attempt | max_steps | Attempts | Successes | Failures |
|---:|---:|---:|---:|---:|
| 1 | 10 | 128 | 14 | 114 |
| 2 | 22 | 114 | 113 | 1 |
| 3 | 22 | 1 | 0 | 1 |

### schedule_20_22_24

| Attempt | max_steps | Attempts | Successes | Failures |
|---:|---:|---:|---:|---:|
| 1 | 10 | 128 | 14 | 114 |
| 2 | 20 | 114 | 107 | 7 |
| 3 | 22 | 7 | 6 | 1 |
| 4 | 24 | 1 | 1 | 0 |

## 解讀

這次結果確認：

1. 單純增加 `max_attempts` 不夠；如果 retry budget 不變，後續 attempt 只是重跑同樣限制。
2. Retry budget schedule 能讓多次 retry 真的有意義。
3. `20 -> 22 -> 24` 可以把 seeds 0..127 從 121/128 提升到 128/128。
4. 目前所有 first-attempt failures 仍歸因為 `budget_cutoff_after_key`。
5. attribution-aware Replanner 在 114 個 first-attempt failures 中全部選擇 `increase_step_budget`，策略語意保持一致。

## Failure Attribution 結論

在目前 seeds 0..127、DoorKey MVP、既有 skill set 與 attribution-aware Replanner
設定下，觀察到的失敗原因集中在 `insufficient budget`，也就是 execution step
limit 不足。這些 cases 不是因為找不到 key、沒有朝正確 subgoal 推進，或選到明顯錯誤
的 skill，而是 plan 在接近完成任務前被 `max_steps` 截斷。

因此，目前證據支持以下判斷：

```text
主要失敗原因：insufficient budget
目前未觀察到的主因：not best skill
```

這代表現階段 Adaptive Core 的主要修正方向應優先放在 budget-aware retry /
replanning，而不是急著替換 skill 或修改 decision tree。若未來切換到更複雜的
MiniGrid task，才需要重新檢查是否出現 `not best skill`、subgoal selection error
或 planner decision error。

## 對 Adaptive Core 的意義

目前 Adaptive Core 已能做到：

```text
Failure Attribution
-> Attribution-aware Replanner
-> Retry Budget Schedule
-> Skill Feedback Memory
-> Skill Ranking Feedback
```

這表示系統已不只是「失敗後重跑」，而是可以根據失敗歸因逐步調整 retry execution
budget，並將 repair outcome 回饋給後續 skill ranking。

## 下一步

下一步若要讓 decision tree 真的改變，可以從 budget schedule 進一步推進到：

```text
Replanner plan_patch
-> replace selected skill
-> insert progress guard
-> modify subgoal-level plan
```

目前 schedule 已經解決「多 retry 但 budget 不變」的問題。後續應把重點轉到
skill/plan patch，而不是只增加 retry 次數。
