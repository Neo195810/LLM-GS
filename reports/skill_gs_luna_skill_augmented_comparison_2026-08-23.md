# Skill-GS Luna Skill-Augmented 小比較

日期：2026-08-23
Branch：`Branch_NerdyClaush`
Repo：`F:\GitHub_Experiment\LLM-GS-team`

## 目的

本次比較的目標是確認：當 Luna 在 DoorKey seed 0 失敗後，Repairer 產生的新
skill 是否能透過 `{{skills_context}}` 注入 prompt，並讓 Luna 在下一次嘗試中
直接產出可成功執行的 action sequence。

這不是泛化實驗，而是 seed 0 的最小證據鏈：

```text
Luna one-shot failure
-> Evaluator trace
-> Repairer repaired policy
-> Learned skill stored in skill database
-> Skill injected into Luna prompt
-> Luna skill-augmented run
```

## 對照設定

| 項目 | Luna prompt v4 裸跑 | Luna + learned skill |
|---|---:|---:|
| Provider | OpenAI | OpenAI |
| Model | `gpt-5.6-luna` | `gpt-5.6-luna` |
| Seed | 0 | 0 |
| Temperature | 0 | 0 |
| Reasoning effort | none | none |
| Skill DB | 無 | `output\skill_gs\llm_repair_skills_prompt_v4.json` |
| Prompt placeholder | `{{environment_state}}` | `{{environment_state}}`, `{{skills_context}}` |

## 注入的 Learned Skill

```text
Skill ID: llm_repair.karel.doorkey.navigate_to_goal_after_key.v1
Name: repair_post_key_navigation_to_goal
Preconditions: door_open, key_picked
Postconditions: goal_topped_off, success
Action Pattern:
turnLeft turnLeft move move turnRight move move move move turnLeft move move putMarker
```

這個 skill 來自 Luna prompt v4 的失敗案例。Repairer 保留 Luna 已經做對的
「找到鑰匙並 pickMarker」前綴，再修正「撿到鑰匙後如何通過門並到達 goal」
的後段 navigation。

## 結果摘要

| 指標 | Luna prompt v4 裸跑 | Luna + learned skill |
|---|---:|---:|
| Success | false | true |
| Reward | -0.5 | 1.0 |
| Steps | 16 | 16 |
| Key pickup | 成功 | 成功 |
| Door opened | 成功 | 成功 |
| Final putMarker | 錯誤位置 `[4, 2]` | 正確位置 `[1, 6]` |
| Failure attribution | blocked_motion | completed |

## 行為差異

兩次 run 的前三步相同，Luna 都能正確到達 key 並使用 `pickMarker`：

```text
turnRight, move, pickMarker
```

差異發生在撿到 key 之後。

裸跑版本在 door 已經打開後，沒有往右穿過 door cell，而是回到左側空間內移動，
最後在 `[4, 2]` 使用 `putMarker`，因此得到負回饋。

Skill-augmented 版本在看到 learned skill 後，產生了可通過 door cell 的後段路徑：

```text
turnLeft, turnLeft, move, move,
turnRight, move, move, move, move,
turnLeft, move, move, putMarker
```

最後 agent 到達 goal position `[1, 6]`，再使用 `putMarker`，Evaluator 判定成功。

## 觀察

本次結果支持一個重要結論：Repairer 學到的 skill 可以不只用於事後修復，也能
透過 runtime prompt injection 影響 Luna 下一次產生 policy。

換句話說，目前系統已經具備 Skill-GS 的最小循環：

```text
失敗 trace -> repair -> skill memory -> skill-augmented prompt -> improved policy
```

這代表 `{{skills_context}}` 不是單純的文字補充，而是能實際改變 Luna action
sequence 的 context engineering 介面。

## 限制

- 本比較只包含 seed 0，不能直接宣稱跨 seed 泛化。
- Learned skill 目前仍偏向 seed 0 的 post-key navigation pattern。
- Luna 可能是在技能提示下複用 action pattern，而不一定真的理解所有 grid topology。
- 下一步需要 seed 0~7 觀察：哪些 seed 能直接受益，哪些 seed 仍需要 Repairer。

## 下一步

建議下一輪執行 seed 0~7 的 skill-augmented Luna smoke test：

```text
for seed in 0..7:
  environment_state + skills_context -> Luna -> Evaluator
  if failed:
    failed trace -> Repairer -> update skill DB
```

這樣可以比較：

- Luna 裸跑成功率
- Luna + learned skill 成功率
- Repairer 後成功率
- 每個失敗案例的 failure attribution
- skill database 是否逐步累積更可泛化的 post-key navigation skill

## 輸出檔案

| 類型 | 路徑 |
|---|---|
| Luna prompt v4 裸跑 | `output\skill_gs\llm_generated_seed0_openai_luna_prompt_v4_smoke.json` |
| Repairer learned skill DB | `output\skill_gs\llm_repair_skills_prompt_v4.json` |
| Luna + learned skill | `output\skill_gs\llm_generated_seed0_openai_luna_skill_augmented_smoke.json` |
