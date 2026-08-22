# Skill-GS Baseline Comparison 實驗報告

日期：2026-08-22
Branch：`Branch_NerdyClaush`
Repo：`F:\GitHub_Experiment\LLM-GS-team`

## 目的

本次目標是補上 Baselines comparison 的公平對照組，讓目前的 Adaptive Skill-GS
不只和自己的不同 retry 設定比較，也能和兩種更接近 baseline 的方法放在同一個
evaluation table 中。

本次比較三組：

| Group | 說明 |
|---|---|
| `llm_generated` | LLM-generated one-shot proxy。代表一次產生固定 program/policy，不做 search、不做 repair。 |
| `llm_gs_style_search` | LLM-GS-style candidate search proxy。代表生成多個 candidate 後用 evaluator 選最佳，但不做 adaptive memory/replanning。 |
| `ours_adaptive_skill_gs` | 我們的 Adaptive Skill-GS。使用 failure attribution、attribution-aware replanner 與 retry budget schedule。 |

注意：目前這兩個 LLM-named baseline 是 local reproducible proxy，沒有呼叫外部 LLM
API。這樣做是為了讓 seeds、environment、evaluator、budget 設定可以先被固定下來，
建立可重跑、可比較的 baseline harness。

## 公平性設定

| Setting | Value |
|---|---|
| task | DoorKey |
| seeds | 0..127 |
| shared environment | `prog_policies.karel_tasks.DoorKey` |
| shared evaluator | `prog_policies.skill_gs.evaluator.run_doorkey_mvp` |
| external LLM calls | false |
| max allowed execution budget | 24 |

## Baseline 設定

### LLM-generated one-shot proxy

```text
max_steps = 10
repair = disabled
memory = disabled
search = disabled
```

這組代表「一次產生一個固定 policy/program 後直接跑」，沒有後續修正能力。

### LLM-GS-style search proxy

Candidate search space：

```text
max_steps candidates = 10, 20, 22, 24
```

系統會對每個 candidate 跑同一批 seeds，並依照 success rate、failed seeds、average
steps 等指標選出最佳 candidate。這組代表「搜尋多份 candidate program/budget 後選
最佳」，但不具備 per-seed adaptive retry、failure memory 或 replanning。

### Ours: Adaptive Skill-GS

```text
initial_max_steps = 10
retry_budget_schedule = 20 -> 22 -> 24
max_attempts = 4
replanner_policy = attribution_aware
perturbation_seed = 123
```

這組代表「先用低 budget 嘗試，失敗後根據 failure attribution 逐步放寬 budget」。

## 實驗指令

```powershell
python scripts\skill_gs\run_baseline_comparison.py `
  --seed-start 0 `
  --seed-end 127 `
  --initial-max-steps 10 `
  --search-candidate-max-steps 10 20 22 24 `
  --ours-retry-budget-schedule 20 22 24 `
  --ours-max-attempts 4 `
  --perturbation-seed 123 `
  --output output\skill_gs\baseline_comparison_seed0_127.json
```

## 實驗結果

| Group | Successes | Success Rate | Evaluation Count | Max Budget | Repair | Memory |
|---|---:|---:|---:|---:|---|---|
| `llm_generated` | 14/128 | 0.109375 | 128 | 10 | no | no |
| `llm_gs_style_search` | 128/128 | 1.0 | 512 | 24 | no | no |
| `ours_adaptive_skill_gs` | 128/128 | 1.0 | 250 | 24 | yes | yes |

## Candidate Search 細節

| Candidate | max_steps | Successes | Success Rate | Failed Seeds |
|---|---:|---:|---:|---|
| `candidate_01` | 10 | 14/128 | 0.109375 | 114 failed |
| `candidate_02` | 20 | 121/128 | 0.9453125 | 1, 19, 29, 57, 65, 78, 93 |
| `candidate_03` | 22 | 127/128 | 0.9921875 | 65 |
| `candidate_04` | 24 | 128/128 | 1.0 | none |

最後 search proxy 選到 `candidate_04`，也就是 `max_steps = 24`。

## 解讀

本次結果顯示：

1. `llm_generated` one-shot proxy 在 `max_steps = 10` 下只成功 14/128，主要問題仍是
   execution budget 不足。
2. `llm_gs_style_search` 可以透過完整 candidate search 找到 `max_steps = 24`，因此
   達到 128/128。
3. `ours_adaptive_skill_gs` 同樣達到 128/128，但 evaluation count 是 250，少於
   search proxy 的 512。
4. 這代表目前 Adaptive Core 的優勢不是「找到比 search 更短的 final path」，而是用
   failure attribution 在需要時才追加 budget，因此 evaluation/sample cost 較低。
5. 在目前 DoorKey MVP 中，失敗原因仍支持先前結論：主要是 insufficient budget，而
   不是 not best skill。

## 對專題的意義

這份結果讓 Baselines comparison 有了第一版可重跑骨架：

```text
LLM-generated one-shot proxy
vs
LLM-GS-style candidate search proxy
vs
Ours Adaptive Skill-GS
```

目前我們不能宣稱已經打敗真正接 LLM API 的 LLM-GS，因為本次 baseline 還是 local
proxy。但我們已經能公平展示：

```text
同一批 seeds
同一個 DoorKey environment
同一個 evaluator
同一個最高 execution budget
不同 search / repair / memory 機制
```

在這個設定下，Adaptive Skill-GS 能用較少 evaluation 次數達到和 candidate search
相同的 100% success rate。

## 下一步

後續若要更接近 paper baseline，可以把 `llm_generated` 與 `llm_gs_style_search`
從 local proxy 替換成真正的 LLM program generator：

```text
LLM prompt -> candidate DSL program -> evaluator -> candidate selection
```

但這一步會引入 API 成本、prompt variance、temperature、LLM model version 等變因。
在 Hackathon/MVP 階段，先保留 local proxy baseline 比較穩定，也比較容易展示。
