# Skill-GS Demo Script

日期：2026-08-24
Repo：`F:\GitHub_Experiment\LLM-GS-team`
Branch：`Branch_NerdyClaush`

## Demo 核心主張

本 demo 不主張我們做出了一個強力 LLM agent。

本 demo 要展示的是：

```text
LLM agent 產生的 policy 可能不穩定，
但 Adaptive Core 可以把失敗 trace 轉成可分析、可修復、可累積的技能經驗。
```

換句話說，Skill-GS 的核心不是讓 LLM 一次就變聰明，而是建立一個環境適應迴圈：

```text
LLM policy
-> Evaluator 執行與紀錄 trace
-> Failure Attribution 判斷失敗位置
-> Replanner 修復 policy
-> Skill Memory 累積修復經驗
-> 下一次 prompt / repair 使用更可靠的 skills
```

這更接近本專題要展示的 adaptive core：讓不同 LLM agent 可以透過 evaluator feedback 適應遊戲環境。

## Demo 任務：DoorKey

DoorKey 是一個小型 Grid 任務：

```text
1. agent 從初始位置出發
2. 找到 key marker
3. 在 key_position 執行 pickMarker
4. door/lock cell 打開
5. 穿過 door cell
6. 到達 goal_position
7. 在 goal_position 執行 putMarker
```

這個任務適合 demo，因為它很小，但又足以暴露 LLM 的常見問題：

- 看似理解規則，但 action sequence 會走錯。
- 能撿到 key，卻在 post-key navigation 迷路。
- 會在錯誤位置執行 `putMarker`。
- 不一定能穩定 mental simulation grid state。

## 目前完成的模組

| 簡報模組 | 目前實作狀態 | 對應檔案 |
|---|---|---|
| Skill Manager | 已完成 JSON skill store、skill retrieval、ranking、stage-aware skill context | `prog_policies/skill_gs/skill_manager.py`, `skill_ranker.py`, `llm_generated_baseline.py` |
| Critic-Repair | 已完成 trace attribution、structured failure、local repair operators | `trace_attribution.py`, `llm_repair.py`, `repair_llm_generated_batch.py` |
| Planner | 已完成 subgoal template 與 plan 結構；DoorKey repair 使用 deterministic replanning | `planner.py`, `replanner.py`, `adaptive_retry.py` |
| Evaluator | 已完成 action execution、reward、trace logging、success/failure 判定 | `evaluator.py`, `llm_generated_baseline.py` |
| Memory | 已完成 repair observation 寫回 skill database | `skill_memory.py`, `adaptive_memory.py`, `llm_repair.py` |
| LLM Baseline | 已接 OpenAI Luna 與 Gemini provider | `llm_generated_baseline.py`, `run_llm_generated_smoke.py` |

## 實驗結果摘要

### Luna baseline

| 設定 | Seeds | One-shot success | Adaptive repair success |
|---|---:|---:|---:|
| Luna + stage-aware skills | 0~31 | 0/32 | 32/32 |

觀察：

- Luna one-shot 完全不穩，`0~31` 沒有直接解出。
- 但所有失敗都能進入 Evaluator/Replanner。
- Adaptive Core 修復後 `32/32` 成功。

### Gemini baseline

| 設定 | Seeds | One-shot success | Adaptive repair success |
|---|---:|---:|---:|
| Gemini 3.5 Flash + stage-aware skills | 0~31 | 6/32 | 32/32 |

Gemini one-shot 成功 seeds：

```text
3, 11, 13, 16, 17, 27
```

Gemini 失敗型態：

| Failure stage | Count |
|---|---:|
| after_key_before_goal | 23 |
| before_key | 3 |

Gemini repair strategy：

| Repair strategy | Count |
|---|---:|
| splice_post_key_navigation | 23 |
| replan_via_key_then_goal | 3 |

觀察：

- Gemini 比 Luna 更會 one-shot，成功率 `6/32`。
- 但主要問題仍然是 post-key navigation。
- Adaptive Core 對 Gemini 也能修到 `32/32`。

## Demo 故事線

建議用 5 到 7 分鐘展示。

### 1. 開場：我們不是在做強力 LLM agent

講稿：

```text
這個 demo 的目標不是證明 LLM 一次就能解遊戲。
相反地，我們假設 LLM 會犯錯。
我們想做的是 Adaptive Core：當 LLM agent 在遊戲環境中犯錯時，
系統能不能觀察失敗、歸因失敗、修復策略，並把修復經驗累積成技能。
```

### 2. 展示 DoorKey 任務

講稿：

```text
DoorKey 任務很直覺：先拿 key，再穿過 door，最後到 goal 放 marker。
但對 LLM 來說，它需要把文字規則轉成精確 action sequence。
只要中間方向、位置、door 狀態模擬錯一步，就會失敗。
```

可以展示 Gemini seed 0 的初始狀態：

```text
agent_position: [4, 2]
agent_direction: east
key_position: [5, 2]
door_cells: [[2, 4], [3, 4]]
goal_position: [1, 6]
```

### 3. 展示 LLM one-shot policy 失敗

Gemini seed 0 one-shot 的行為：

```text
turnRight
move
pickMarker
turnLeft
move
move
turnLeft
move
move
turnRight
move
move
putMarker
```

結果：

```text
success: false
reward: -0.5
stage_at_end: after_key_before_goal
attribution: blocked_motion
```

講稿：

```text
這裡很有價值的是，Gemini 其實成功撿到了 key。
所以它不是完全不懂任務。
真正失敗的位置在 key 之後：它嘗試往 goal 走，但 grid navigation 崩掉，
最後在錯誤位置 putMarker。
```

### 4. 展示 Evaluator 與 Failure Attribution

Evaluator 會記錄每一步：

```text
step
action
agent_before
agent_after
door_open
instant_reward
total_reward
```

Failure attribution 會把 trace 轉成可用訊號：

```text
stage_at_end: after_key_before_goal
blocked_moves: 3
unique_positions: 5
attribution: blocked_motion
```

講稿：

```text
這一步是 guardrail。
我們不是問 LLM 自己有沒有成功，而是讓 evaluator 真正執行 policy。
然後 trace attribution 把失敗整理成機器可讀的修復訊號。
```

### 5. 展示 Replanner 修復

Gemini seed 0 repair plan：

```text
strategy_id: splice_post_key_navigation
target_subgoal: navigate_to_goal_after_key
rationale:
Preserve the verified key pickup prefix,
then replace the failed post-key navigation segment
with a shortest-path suffix to the goal.
```

修復後結果：

```text
success: true
reward: 1.0
steps: 16
stage_at_end: completed
attribution: completed
```

講稿：

```text
Replanner 沒有把整個 policy 丟掉。
它保留已經被驗證成功的 key pickup prefix，
只替換失敗的 post-key navigation suffix。
這就是 local repair，比重新生成整個 program 更穩。
```

### 6. 展示 Skill Memory

目前核心 skills：

| Skill | 作用 |
|---|---|
| `navigate_to_key_before_door_open` | door 還沒開時，先導航到 key 並 pickMarker |
| `navigate_to_goal_after_key` | key 已取得後，穿過 door 並導航到 goal |

講稿：

```text
每次 repair 成功後，系統會把觀察寫回 skill memory。
這不是直接訓練模型權重，而是把成功的修復經驗變成可檢索、可排名、可重用的技能。
```

### 7. 最後展示總表

```text
Luna one-shot:       0/32
Luna + repair:      32/32

Gemini one-shot:     6/32
Gemini + repair:    32/32
```

講稿：

```text
Luna 和 Gemini 的 one-shot 能力不同。
Gemini 明顯比較強，但仍然不穩。
Skill-GS 的重點是，不論是哪個 LLM provider，
只要它產生可執行 trace，Adaptive Core 就能分析失敗並修復。
```

## Demo 執行方式

建議比賽展示時使用「穩定展示」為主，「live run」為輔。

### 穩定展示

使用已產生的 JSON：

```text
output/skill_gs/gemini_3_5_flash_v1_seed0_7/
output/skill_gs/gemini_3_5_flash_v1_seed8_15/
output/skill_gs/gemini_3_5_flash_v1_seed16_31/
output/skill_gs/llm_repair_seed0_7_gemini_3_5_flash_v1_summary.json
output/skill_gs/llm_repair_seed8_15_gemini_3_5_flash_v1_summary.json
output/skill_gs/llm_repair_seed16_31_gemini_3_5_flash_v1_summary.json
```

優點：

- 不怕網路或 API 額度出問題。
- 不怕現場 response 波動。
- 可以穩定展示同一批結果。

### Live run

只建議 live 跑 seed 0。

```powershell
$env:GEMINI_API_KEY = [Environment]::GetEnvironmentVariable("GEMINI_API_KEY", "Machine")
$python = "C:\Users\haoch\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"

& $python scripts\skill_gs\run_llm_generated_smoke.py `
  --provider Gemini `
  --model gemini-3.5-flash `
  --temperature 0 `
  --prompt-template "C:\Users\haoch\Desktop\doorkey_one_shot_policy_v1.txt" `
  --skill-store "output\skill_gs\llm_repair_skills_prompt_v4.json" `
  --seed 0 `
  --max-output-tokens 512 `
  --output "output\skill_gs\demo_gemini_seed0_smoke.json"
```

接著 repair：

```powershell
& $python scripts\skill_gs\repair_llm_generated_policy.py `
  --input "output\skill_gs\demo_gemini_seed0_smoke.json" `
  --output "output\skill_gs\demo_gemini_seed0_repair.json" `
  --skill-store "output\skill_gs\llm_repair_skills_prompt_v4.json" `
  --source-label "demo_gemini_seed0"
```

## Demo 風險與備案

| 風險 | 備案 |
|---|---|
| API 呼叫失敗 | 使用已產生 JSON 做穩定展示 |
| Gemini 這次 live 剛好成功 | 改展示 seed 0 的已保存失敗案例，或說明 one-shot 有波動 |
| 現場時間不足 | 只講 seed 0 failure -> repair -> success |
| 評審問是否只是 BFS | 說明 BFS/local planner 是 repair operator，核心貢獻是 evaluator-driven failure attribution + local repair + skill memory loop |
| 評審問是不是訓練模型 | 說明目前不是更新模型權重，而是更新可檢索技能記憶，屬於 agent-level adaptation |

## 一句話總結

```text
Skill-GS 不是讓 LLM 一次就會玩遊戲，
而是讓 LLM 在失敗後能被 evaluator 觀察、被 replanner 修復，
並把修復結果累積成下一次可使用的技能。
```

## Demo 後續可補強

- 加一個小型 dashboard，顯示 one-shot / repaired policy trace。
- 將 Gemini vs Luna 結果做成圖表。
- 將 `after_key_before_goal` 的失敗案例做成一張 visual trace。
- 把 Replanner repair 過程做成三段式動畫：

```text
successful prefix
failed suffix
repaired suffix
```

這些都不是 MVP 必須，但很適合提升展示效果。
