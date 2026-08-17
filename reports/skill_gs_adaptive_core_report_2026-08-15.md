# Skill-GS Adaptive Core 進度與實驗報告

日期：2026-08-15
Branch：`Branch_NerdyClaush`
Repo：`F:\GitHub_Experiment\LLM-GS-team`

## 摘要

今天的主要進度，是把原本穩定可跑的 DoorKey MVP，從 BFS/rule-based
baseline 往前推進成一個小型但完整的 Adaptive Core loop。

目前系統已經可以做到：

- 在 repo 原生的 Karel DoorKey 任務上跑固定 seed 範圍
- 從 evaluator 與 critic output 中偵測 failure
- 使用固定 random seed 選擇 repair perturbation
- 根據 failure diagnosis 產生下一次 attempt 的 replan
- 對失敗 seed 進行 retry
- 儲存 attempt-level adaptive memory
- 統計 success rate、retry count、replan count 與 failure type

這仍然不是完整論文級別的 Skill-GS 演算法。目前版本使用
BFS/rule-based DoorKey policy 作為穩定 baseline，並透過控制 step budget
來測試 Adaptive Core 的行為。

## 已完成元件

Skill-GS layer 目前包含以下 Adaptive Core 模組：

| Component | File | Role |
|---|---|---|
| Failure Detector | `prog_policies/skill_gs/failure_detector.py` | 將 evaluator 與 critic output 轉換成穩定的 failure diagnosis |
| Stochastic Perturbation | `prog_policies/skill_gs/stochastic_perturbation.py` | 使用可重現的 random seed 選擇 repair strategy |
| Skill Ranker | `prog_policies/skill_gs/skill_ranker.py` | 根據 failure diagnosis 重新排序候選 skill |
| Replanner | `prog_policies/skill_gs/replanner.py` | 將 diagnosis 與 perturbation 轉換成下一次 attempt config |
| Adaptive Memory | `prog_policies/skill_gs/adaptive_memory.py` | 儲存 attempts、diagnoses、repair plans 與 repair outcomes |
| Retry Wrapper | `prog_policies/skill_gs/adaptive_retry.py` | 串接 detector、perturbation、replanning、retry 與 memory |
| Agent Workflow | `prog_policies/skill_gs/agent_workflow.py` | 將 DoorKey loop 暴露成 role-based agent data flow |

目前 Adaptive Core 的資料流如下：

```text
Evaluator output
-> Failure Detector
-> Seeded Perturbation
-> Adaptive Skill Ranking
-> Replanner
-> Retry Wrapper
-> Adaptive Memory
```

Agent 層級的資料流如下：

```text
PlannerAgent
-> SkillManagerAgent
-> EvaluatorAgent
-> CriticRepairAgent
-> SkillMemoryAgent
```

## 實驗設定

所有實驗皆使用：

- task：Karel DoorKey
- policy：目前的 BFS/rule-based fixed policy
- adaptive mode：enabled
- max attempts：2
- perturbation seed：123
- output directory：`output/skill_gs/`

本次 failure 是透過 step-budget limit 人為誘發。也就是說，這些實驗不是
在證明 BFS 很差，而是在測試 Adaptive Core 能不能偵測第一次 attempt
因步數不足而失敗，接著產生 repair plan、retry，並記錄結果。

範例指令：

```powershell
python scripts\skill_gs\run_agent_loop.py --seeds 0 --adaptive-retry --initial-max-steps 10 --retry-max-steps 22 --max-attempts 2 --perturbation-seed 123
```

## 實驗 1：Seeds 0..127，寬鬆 Retry Budget

設定：

```text
seeds = 0..127
initial max_steps = 10
retry max_steps = 100
max_attempts = 2
```

結果：

| Metric | Value |
|---|---:|
| total seeds | 128 |
| total attempts | 242 |
| first-attempt successes | 14 |
| retried seeds | 114 |
| replan count | 114 |
| retry successes | 114 |
| retry failures | 0 |
| final successes | 128 |
| final success rate | 1.0 |
| average successful steps | 15.078125 |

解讀：

在 `initial max_steps=10` 時，大多數 seed 無法在第一次 attempt 中完成。
然而，當 retry budget 放寬到 100 時，所有失敗 seed 都能在 retry 後成功。
這驗證了 Adaptive Core pipeline 在寬鬆 repair budget 下可以完整運作。

結果檔案：

```text
output/skill_gs/adaptive_retry_seed0_127_max10_retry100.json
```

## 實驗 2：Seeds 0..63，短步數 Budget 測試

| Initial max_steps | Retry max_steps | First success | Retried | Replans | Retry success | Final success | Success rate |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 6 | 50 | 0/64 | 64 | 64 | 64 | 64/64 | 1.0 |
| 8 | 10 | 2/64 | 62 | 62 | 4 | 6/64 | 0.09375 |

解讀：

`max_steps=6` 對 seeds 0..63 來說太低，沒有任何 seed 能在第一次 attempt
完成。當 retry budget 提高到 50 時，全部 case 都能被 repair 成功。

`max_steps=8` 開始能解出少數短路徑 case。第一次 attempt 成功的 seed
只有 `6` 與 `16`。當 `retry_max_steps=10` 時，只額外救回四個 seed：
`13`、`17`、`25`、`61`。這代表 retry budget 10 對大多數 DoorKey layout
仍然太緊。

結果檔案：

```text
output/skill_gs/adaptive_retry_seed0_63_max6_retry50.json
output/skill_gs/adaptive_retry_seed0_63_max8_retry10.json
```

## 實驗 3：Retry Budget Sweep，Seeds 0..63

設定：

```text
seeds = 0..63
initial max_steps = 10
retry max_steps = 20..30
max_attempts = 2
```

結果：

| retry max_steps | first success | retried | replans | retry success | final success | failed seeds |
|---:|---:|---:|---:|---:|---:|---|
| 20 | 6/64 | 58 | 58 | 54 | 60/64 | 1, 19, 29, 57 |
| 21 | 6/64 | 58 | 58 | 55 | 61/64 | 1, 19, 29 |
| 22 | 6/64 | 58 | 58 | 58 | 64/64 | none |
| 23 | 6/64 | 58 | 58 | 58 | 64/64 | none |
| 24 | 6/64 | 58 | 58 | 58 | 64/64 | none |
| 25 | 6/64 | 58 | 58 | 58 | 64/64 | none |
| 26 | 6/64 | 58 | 58 | 58 | 64/64 | none |
| 27 | 6/64 | 58 | 58 | 58 | 64/64 | none |
| 28 | 6/64 | 58 | 58 | 58 | 64/64 | none |
| 29 | 6/64 | 58 | 58 | 58 | 64/64 | none |
| 30 | 6/64 | 58 | 58 | 58 | 64/64 | none |

解讀：

對 seeds 0..63 而言，當第一次 attempt 限制在 `max_steps=10` 時，只有
6 個 seed 會立即成功。剩下 58 個 seed 都會觸發 failure detection 與
replanning。

觀察到的完整成功 retry threshold 是：

```text
retry_max_steps = 22
```

當 retry budget 為 20 時，仍有四個 seed 失敗：`1`、`19`、`29`、`57`。
當 retry budget 為 21 時，仍有三個 seed 失敗：`1`、`19`、`29`。
當 retry budget 到 22 或以上時，seeds 0..63 全部成功。

結果檔案：

```text
output/skill_gs/adaptive_retry_sweep_seed0_63_max10_retry20_30_summary.json
output/skill_gs/adaptive_retry_sweep_seed0_63_max10_retry20_30_full.json
```

## Failure Detector 觀察

Raw critic 與 formal failure detector 不一定會產生相同標籤。這是預期內的，
而且對 Adaptive Core 很有用。

Retry sweep 中的一個例子：

```text
raw critic:
  insert_missing_subgoal or retrieve_alternative_skill

formal failure detector:
  step_budget_exhausted
```

Critic 主要從任務進度與 repair hint 的角度判斷。Failure Detector 則額外
加入 runtime context，特別是 `steps == max_steps` 且 environment 尚未
terminated 的情況。因此在 loop engineering 實驗中，`step_budget_exhausted`
是更適合交給 replanner 的正式 diagnosis。

## 主要發現

1. BFS/rule-based DoorKey baseline 在 step budget 足夠時是穩定的。
2. 小 step budget 可以在不修改 task 與 policy 的情況下製造 controlled failure。
3. Adaptive Core 可以把這些 failure 轉換成 retry/replan event。
4. 對 seeds 0..63 而言，`max_steps=6` 低於觀察到的 first-attempt success threshold。
5. 對 seeds 0..63 且 `initial max_steps=10` 的設定來說，完整成功所需的 retry budget 是 22。
6. 本次實驗中 retry count 與 replan count 相同，因為每個失敗 seed 都只在第二次 attempt 前 replan 一次。
7. Adaptive Skill Ranking 已經能根據 failure diagnosis 產生候選 skill 的 reranking artifact，讓下一階段 replanning 可以使用 skill-level 訊號。

## 目前限制

- 目前 policy 仍是 BFS/rule-based baseline，還不是 learned policy 或 LLM-generated policy。
- Stochastic perturbation 目前已能選擇 repair strategy，並透過 Skill Ranker 產生候選 skill reranking；但尚未 mutate AST structure。
- Replanning 目前主要改變 attempt configuration，也就是 step budget，尚未合成新的 DSL program。
- Adaptive memory 目前會記錄 attempts 與 repair outcomes，但尚未回饋到未來的 skill retrieval。

## 建議下一步

1. 加入小型 report generator，將 `output/skill_gs/*.json` 自動轉成 Markdown tables。
2. 做 skill-ranking experiment，測試 reranked skills 是否應該依照 seed coverage、success rate 或 failure signature 排序。
3. 將 replanning 擴展到 step budget 以外，例如讓 Replanner 根據 `skill_ranking` 選擇 alternative navigation skill。
4. 後續再將 Adaptive Core 接到原始 LLM-GS candidate programs，讓 failure detection 與 repair 不只用在 BFS baseline，也能用在 generated programs。

## 驗證

Adaptive Core 實作後使用的 fresh verification command：

```powershell
python -m unittest tests.test_skill_gs_doorkey_mvp tests.test_skill_gs_agent_workflow tests.test_skill_gs_adaptive_core -v
```

觀察結果：

```text
Ran 16 tests
OK
```

實驗 output files 位於 `output/skill_gs/`，且 `output/` 已經被 `.gitignore`
忽略，不會進入版控。
