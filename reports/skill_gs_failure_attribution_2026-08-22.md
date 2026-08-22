# Skill-GS Failure Attribution 報告

日期：2026-08-22
Branch：`Branch_NerdyClaush`
Repo：`F:\GitHub_Experiment\LLM-GS-team`

## 摘要

本報告整理目前 Skill-GS DoorKey MVP / Adaptive Core 實驗中的失敗案例，
目的不是再增加新的 Analyzer Agent，而是先從既有 evaluator、critic、
failure detector、retry loop 與 trace output 中分析：

- 哪些 seed 會失敗
- 為什麼會失敗
- 失敗是否代表 policy 走錯
- 是否有明顯不必要步數、looping、撞牆或子任務順序錯誤
- 這些 failure 應如何回饋到下一階段 Adaptive Core

目前主要結論是：大多數失敗不是 BFS/rule-based baseline 完全失效，
而是人為設置的 step budget 太低，導致 agent 在正確路徑上尚未完成任務
就被截斷。這類 failure 適合被標記為 `step_budget_exhausted`，並可進一步
細分為 key 已取得後的 `after_key_before_goal` budget pressure。

後續已將此分析落成 deterministic trace-level attribution metrics：
Adaptive Core 會在每次 attempt 後產生 `trace_attribution`，並在 retry memory
的 repair outcome 中保存 `failure_attribution` 與 `observed_solve_steps`。

## 資料來源

本次分析使用既有實驗 output，不重新跑大量 seed：

| File | 用途 |
|---|---|
| `output/skill_gs/adaptive_retry_seed0_127_max10_retry100.json` | 寬鬆 retry budget 的成功參考，用來估計目前 baseline 的 observed solve steps |
| `output/skill_gs/adaptive_retry_seed0_63_max6_retry50.json` | 極低 initial budget 的壓力測試 |
| `output/skill_gs/adaptive_retry_seed0_63_max8_retry10.json` | initial/retry budget 都偏低時的失敗案例 |
| `output/skill_gs/adaptive_retry_sweep_seed0_63_max10_retry20_30_summary.json` | retry budget sweep 的摘要統計 |
| `output/skill_gs/adaptive_retry_sweep_seed0_63_max10_retry20_30_full.json` | retry budget sweep 的 per-seed 結果 |

本報告中的「需要幾步」是指目前 BFS/rule-based baseline 在寬鬆 budget 下的
observed solve steps，不代表數學上的全局最短路徑。

## Failure Attribution 定義

目前可從既有資料觀察或推論的 attribution 如下：

| Attribution | 定義 | 目前觀察 |
|---|---|---|
| `step_budget_exhausted` | 執行步數達到 `max_steps`，environment 尚未 terminated | 大量出現，是目前主要 failure |
| `after_key_before_goal` | reward 已達 0.5 或 door/key 狀態已推進，但尚未到 goal | 低 retry budget 下的失敗多屬於此類 |
| `looping_or_no_progress` | trace 顯示反覆做相同狀態或無進展動作 | 目前未觀察到主要案例 |
| `invalid_action_or_crash` | crash 或非法動作 | 目前未觀察到 |
| `state_extraction_error` | state extraction 與 trace 行為不一致 | 目前未觀察到明確證據 |
| `path_inefficiency` | policy 可完成但有明顯多餘繞路或撞牆 | 目前資料不足以嚴格判定 |

## 實驗總覽

| 實驗 | 設定 | First Attempt | Retry 結果 | Final 結果 | Attribution |
|---|---|---:|---:|---:|---|
| Seeds 0..127 | initial 10, retry 100 | 14 成功 / 114 失敗 | 114 retry 成功 | 128/128 成功 | 大多是 initial budget 太低 |
| Seeds 0..63 | initial 6, retry 50 | 0 成功 / 64 失敗 | 64 retry 成功 | 64/64 成功 | initial budget 低於所有 observed solve steps |
| Seeds 0..63 | initial 8, retry 10 | 2 成功 / 62 失敗 | 4 retry 成功 / 58 retry 失敗 | 6/64 成功 | retry budget 仍太低 |
| Seeds 0..63 sweep | initial 10, retry 20 | 6 成功 / 58 失敗 | 54 retry 成功 / 4 retry 失敗 | 60/64 成功 | 4 個 hard seeds 差 1-2 步 |
| Seeds 0..63 sweep | initial 10, retry 21 | 6 成功 / 58 失敗 | 55 retry 成功 / 3 retry 失敗 | 61/64 成功 | 3 個 hard seeds 差 1 步 |
| Seeds 0..63 sweep | initial 10, retry 22 | 6 成功 / 58 失敗 | 58 retry 成功 | 64/64 成功 | budget threshold 達標 |

## 主要失敗原因

### 1. Step Budget Too Low

目前最主要的 failure 是 `step_budget_exhausted`。

在 seeds 0..127、`initial_max_steps=10`、`retry_max_steps=100` 的實驗中：

| Metric | Value |
|---|---:|
| total seeds | 128 |
| first attempt successes | 14 |
| first attempt failures | 114 |
| first attempt failure type | `step_budget_exhausted` |
| retry successes | 114 |
| final successes | 128 |
| final success rate | 1.0 |
| observed solve steps min / avg / max | 7 / 15.08 / 24 |

這表示在寬鬆 retry budget 下，原本失敗的 seed 全部都可以解掉。因此目前
這批 failure 主要不是策略完全錯誤，而是第一次 attempt 的步數限制太低。

### 2. Low Budget Failure 通常發生在拿到 key 之後

在 `initial_max_steps=8`、`retry_max_steps=10` 的 seeds 0..63 實驗中：

| Metric | Value |
|---|---:|
| total seeds | 64 |
| first attempt successes | 2 |
| first attempt success seeds | 6, 16 |
| retry success seeds | 13, 17, 25, 61 |
| final failed seeds | 58 |
| final failed stage | `after_key_before_goal` |

58 個最終失敗 case 都已經取得部分 reward，也就是 reward 為 0.5，
代表 agent 已經完成「取得 key / 開啟 door 相關進展」，但還沒抵達 goal。

因此這些失敗不適合簡單解讀成「agent 不知道鑰匙在哪」或「subgoal 順序錯」。
更合理的歸因是：

```text
agent 已經進入正確流程，但 retry budget 仍不足以完成 key -> goal 的後半段路徑。
```

### 3. Hard Seeds 是 Budget Threshold 附近的 case

以 seeds 0..63 的 sweep 來看：

| retry max_steps | failed seeds | 原因 |
|---:|---|---|
| 20 | 1, 19, 29, 57 | 這些 seed 需要 21-22 步 |
| 21 | 1, 19, 29 | 這些 seed 需要 22 步 |
| 22 | none | 達到 observed threshold |

困難 seed 的 observed solve steps：

| Seed | Observed solve steps | Moves | Turns | Blocked moves | Attribution |
|---:|---:|---:|---:|---:|---|
| 1 | 22 | 15 | 5 | 0 | high budget pressure |
| 19 | 22 | 15 | 5 | 0 | high budget pressure |
| 29 | 22 | 15 | 5 | 0 | high budget pressure |
| 57 | 21 | 14 | 5 | 0 | high budget pressure |
| 56 | 20 | 13 | 5 | 0 | near-threshold case |
| 22 | 19 | 12 | 5 | 0 | near-threshold case |
| 30 | 19 | 12 | 5 | 0 | near-threshold case |
| 46 | 19 | 12 | 5 | 0 | near-threshold case |
| 59 | 19 | 12 | 5 | 0 | near-threshold case |

這些 hard seeds 沒有出現 blocked move，因此目前沒有證據說它們是因為一直撞牆
或做非法移動而失敗。它們比較像是 layout 本身需要較長的路徑。

## Trace-Level 觀察

### 失敗 trace 多半是成功 trace 的前綴

將低 budget 失敗 trace 與寬鬆 budget 下同 seed 的成功 trace 比較：

| Dataset | Checked failed runs | Failed trace 是成功 trace 前綴 |
|---|---:|---:|
| `max8_retry10` | 58 | 58 |
| sweep `retry20` | 4 | 4 |
| sweep `retry21` | 3 | 3 |

這是很重要的 evidence。

如果失敗 trace 是成功 trace 的前綴，表示 agent 在失敗前並沒有明顯偏離
最終可成功的行為序列；它只是還沒走完就被 `max_steps` 截斷。

因此目前更適合寫成：

```text
failure 來自 execution budget cutoff，而不是 observed policy deviation。
```

### 不必要步數目前沒有明確證據

在 seeds 0..127 的寬鬆 budget 成功參考中：

| Metric | Value |
|---|---:|
| total blocked moves | 0 |
| total move actions | 1172 |
| total turnRight actions | 252 |
| total turnLeft actions | 250 |
| total pickMarker actions | 128 |
| total putMarker actions | 128 |

目前 trace 中沒有 observed blocked move，因此不能說 agent 常常撞牆或做
明顯無效移動。

需要注意的是，turn、pickMarker、putMarker 都會造成「位置不變」，但它們不一定
是不必要步數。turn 是方向調整，pickMarker / putMarker 是任務必要動作。
因此不能只用「座標沒有改變」來判斷 waste steps。

## 關於思想鍊錯誤

目前資料不適合直接分析「思想鍊錯誤」。

原因有三個：

1. 目前 agent 是 BFS/rule-based baseline，不是會輸出自然語言 reasoning 的 LLM planner。
2. 目前 JSON 保存的是 evaluator/critic/diagnosis/repair plan，不是完整 chain-of-thought。
3. 從 trace evidence 看，多數失敗是成功路徑的前綴，不像是內部推理方向錯誤。

因此比較安全、也比較工程化的說法是：

```text
目前不分析 chain-of-thought error，而是分析 structured decision trace error。
```

未來如果要讓 agent 從錯誤中學習，建議保存的是：

| Field | 說明 |
|---|---|
| `observed_state` | 當下抽取到的環境狀態 |
| `chosen_subgoal` | planner 選擇的子目標 |
| `selected_skill` | skill ranker / replanner 選出的技能 |
| `expected_progress` | 預期這個 skill 會造成什麼進展 |
| `actual_progress` | 實際 trace 是否達成該進展 |
| `failure_attribution` | 失敗歸因，例如 budget、looping、wrong_subgoal_order |

這樣可以避免保存不可控或不可驗證的內部思考，同時仍然能讓系統從錯誤中學。

## 目前尚未觀察到的錯誤

| Error Type | 目前狀態 | 說明 |
|---|---|---|
| 撞牆 / blocked move | 未觀察到 | 0..127 成功參考中 blocked move 數量為 0 |
| crash / invalid action | 未觀察到 | failure detector 沒有主要分類到此類 |
| 明顯 looping | 未觀察到 | 目前主要 failure 都是 budget cutoff |
| 拿不到 key | 未作為主要問題出現 | 低 budget 最終失敗多半已經 reward 0.5 |
| subgoal 順序錯 | 未觀察到明確證據 | 目前看起來 key -> goal 流程順序是合理的 |
| state extraction 失準 | 未觀察到明確證據 | trace 與 reward/stage 大致一致 |

## 對 Adaptive Core 的意義

目前 Failure Attribution 可以回饋到 Adaptive Core 的方式如下：

| Attribution | 對 Replanner 的意義 | 對 Skill Ranking 的意義 | 對 Memory 的意義 |
|---|---|---|---|
| `step_budget_exhausted` | 提高 retry budget 或延長當前 plan | 不一定需要換 skill | 記錄 seed 的 observed required steps |
| `after_key_before_goal` | 針對 goal navigation 階段調整 plan | 提高 navigation-to-goal skill 權重 | 記錄 key 後半段路徑壓力 |
| `looping_or_no_progress` | 插入 progress guard | 降低造成 loop 的 skill | 記錄 no-progress signature |
| `invalid_action_or_crash` | replace subtree | 降低 unsafe skill | 記錄 crash context |
| `path_inefficiency` | 嘗試 alternative route / subtree | 降低高成本 skill | 記錄 inefficiency metrics |

目前已經能支持前兩種，也就是：

```text
step_budget_exhausted
after_key_before_goal budget pressure
```

後三種仍需要更細的 trace metrics 或 Agent Analyzer 才適合做。

## 建議下一步

短期建議：

1. 暫時不新增 Analyzer Agent。
2. 已先補上 trace-level attribution metrics，例如 blocked moves、turn ratio、stage at failure。
3. 已在 retry memory 中保存 `failure_attribution` 與 `observed_solve_steps`。
4. 下一步讓 Replanner 更明確區分「需要更多步數」與「需要換 skill」。

更完整的下一階段可以是：

```text
Evaluator
-> Failure Detector
-> Failure Attribution
-> Skill Ranking
-> Replanner
-> Retry
-> Memory
```

其中 Failure Attribution 不需要一開始就是 Agent。它可以先是一個 deterministic
trace analyzer，負責產出可測試、可重現、可統計的 structured failure labels。

## 結論

目前 Skill-GS 的失敗案例大多可以被歸因為 step budget 壓力，而不是 policy
或 subgoal order 明顯錯誤。特別是在低 retry budget 實驗中，失敗 seed 多半已經
完成 key 相關進展，只是尚未抵達 goal。

這代表目前 Adaptive Core 的方向是合理的：failure detector 可以找出 budget
cutoff，replanner 可以提高 retry budget，memory 可以記錄哪些 seed 需要更多步數。

下一步真正值得做的不是立刻加入更複雜的 Agent，而是先把 Failure Attribution
變成穩定、可測試的資料欄位。如此一來，之後不管是接上 Agent Analyzer、
LLM-generated DSL program，或更複雜的 MiniGrid-style 任務，系統都能清楚回答：

```text
這次失敗，是因為不會，還是因為還沒走完？
```
