# Skill-GS Replanner Policy 對照實驗

日期：2026-08-22
Branch：`Branch_NerdyClaush`
Repo：`F:\GitHub_Experiment\LLM-GS-team`

## 目的

本次實驗比較原本的 `legacy` Replanner 與新的 `attribution_aware`
Replanner。重點不是追求更高成功率，而是確認 repair strategy 是否能更明確地
反映 failure attribution。

在目前 DoorKey MVP 中，大多數 failure 已被 trace-level metrics 歸因為
`budget_cutoff_after_key`。這代表 agent 已經完成 key 相關進展，但因 execution
step budget 不足，尚未抵達 goal。

因此合理的 repair strategy 應該優先是：

```text
increase_step_budget
```

而不是：

```text
retrieve_alternative_skill
```

## 實驗設定

| Setting | Value |
|---|---:|
| seeds | 0..63 |
| initial_max_steps | 10 |
| retry_max_steps | 20 |
| max_attempts | 2 |
| perturbation_seed | 123 |
| compared policies | `legacy`, `attribution_aware` |

結果摘要另存於：

```text
output/skill_gs/replanner_policy_compare_seed0_63_max10_retry20.json
```

## Replanner Policy 定義

### Legacy

`legacy` policy 保留原本行為：

```text
Failure Detector
-> Stochastic Perturbation
-> Replanner 採用 perturbation strategy
```

因此即使 trace attribution 顯示是 budget cutoff，strategy 仍可能因 stochastic
draw 被標成 `retrieve_alternative_skill`。

### Attribution-Aware

`attribution_aware` policy 會讀取 `trace_attribution`：

| Attribution | Strategy |
|---|---|
| `budget_cutoff_before_key` | `increase_step_budget` |
| `budget_cutoff_after_key` | `increase_step_budget` |
| `budget_cutoff` | `increase_step_budget` |
| `blocked_motion` | `retrieve_alternative_skill` |
| `looping_or_no_progress` | `insert_progress_guard` |

也就是說，只有當 trace 顯示真的卡住、撞牆或 loop 時，才優先考慮換 skill。
如果 trace 顯示只是正確流程被 step limit 截斷，就優先加 budget。

## 實驗結果

| Policy | Success Rate | Final Successes | Failed Seeds | First Failures | Retry Successes | Retry Failures |
|---|---:|---:|---|---:|---:|---:|
| `legacy` | 0.9375 | 60/64 | 1, 19, 29, 57 | 58 | 54 | 4 |
| `attribution_aware` | 0.9375 | 60/64 | 1, 19, 29, 57 | 58 | 54 | 4 |

成功率沒有改變，這是預期內的。因為目前兩種策略在 execution behavior 上都會把
retry budget 提高到 20，所以是否成功主要仍取決於 `retry_max_steps=20`
是否足夠。

真正有差異的是 repair strategy 的可解釋性。

## Repair Strategy 對照

| Policy | `increase_step_budget` | `retrieve_alternative_skill` | Override Count |
|---|---:|---:|---:|
| `legacy` | 51 | 7 | 0 |
| `attribution_aware` | 58 | 0 | 7 |

在 `legacy` policy 中，58 個 first-attempt failures 全部都被 trace metrics
歸因為：

```text
budget_cutoff_after_key
```

但 stochastic perturbation 仍將其中 7 個標成：

```text
retrieve_alternative_skill
```

這會造成語意上的混淆：明明 evidence 指向 budget cutoff，repair label 卻看起來
像是 skill 選錯。

`attribution_aware` policy 則把這 7 個 case 覆寫為：

```text
increase_step_budget
```

因此 attribution 到 strategy 的對應變成：

| Attribution | Legacy Strategy Counts | Attribution-Aware Strategy Counts |
|---|---|---|
| `budget_cutoff_after_key` | `increase_step_budget`: 51, `retrieve_alternative_skill`: 7 | `increase_step_budget`: 58 |

## 解讀

這次實驗說明：

1. 目前 seeds 0..63 的 first-attempt failures 全部是 `budget_cutoff_after_key`。
2. 原本 `legacy` policy 會讓 stochastic perturbation 混入 7 個 `retrieve_alternative_skill`。
3. 新的 `attribution_aware` policy 會把這些 case 修正成 `increase_step_budget`。
4. 成功率沒有改變，因為本次改的是 repair strategy selection 的語意，不是改 policy 或路徑規劃。
5. 這讓 Adaptive Core 更能回答「這次失敗是需要更多 budget，還是需要換 skill」。

換句話說，本次強化的價值是：

```text
讓 repair strategy 更忠實反映 failure evidence。
```

## 後續建議

下一步不需要立刻追求更高成功率，而是可以做兩件事：

1. 將 `decision_basis` 納入後續報告與 memory 分析。
2. 針對 `blocked_motion` 或 `looping_or_no_progress` 製造 controlled failure，
   觀察 `attribution_aware` 是否會改選 `retrieve_alternative_skill` 或
   `insert_progress_guard`。

目前 DoorKey seeds 0..63 的主要結論仍然是：

```text
failure 主要來自 execution step budget cutoff，而不是 skill selection error。
```
