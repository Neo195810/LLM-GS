# Skill-GS Luna seed 0~31 Adaptive Loop 實驗報告

日期：2026-08-23
Branch：`Branch_NerdyClaush`
Repo：`F:\GitHub_Experiment\LLM-GS-team`

## 目的

本次實驗延續前一份 seed 0 小比較，先將範圍擴大到 DoorKey seed `0~7`，
再用 seed `0~15` 與 seed `0~31` 做 sanity check，確認 Adaptive Loop 在較多樣本下是否仍能穩定修復。
主要問題是：

```text
Repairer 學到的 skills 是否能讓 Luna 在多個 seed 中穩定產生可執行 policy？
如果 Luna 仍失敗，Adaptive Core 是否能透過 Evaluator/Replanner 修復並更新 skill memory？
```

這次實驗的重點不是證明 Luna one-shot 已經完全可靠，而是確認 Skill-GS 的完整閉環：

```text
LLM policy -> Evaluator -> Failure Attribution -> Replanner -> Skill Memory
```

## Skill Memory 狀態

目前 skill database 中有兩個 DoorKey repair skills：

| Skill ID | 角色 | Source seeds | Evaluations | Success rate |
|---|---|---:|---:|---:|
| `llm_repair.karel.doorkey.navigate_to_goal_after_key.v1` | 撿到 key 後，通過 door 到 goal | 0~31 | 63 | 1.0 |
| `llm_repair.karel.doorkey.navigate_to_key_before_door_open.v1` | door 尚未打開時，先到 key_position 並 pickMarker | 1,2,3,5,7,9,11,12,13,14,17,18,19,23,28,31 | 32 | 1.0 |

這裡的 `Evaluations` 是 repair observation 累積次數，`Source seeds` 是目前已觀察過的不同 seed。

## 實驗流程

本次先分成三輪 Luna seed `0~7` 測試，再用同樣流程擴展到 seed `0~15` 與 seed `0~31`。

### V1：只注入 post-key skill

第一輪只使用 seed 0 repair 後得到的 post-key skill：

```text
navigate_to_goal_after_key
```

| 指標 | 結果 |
|---|---:|
| Luna-only success | 2/8 |
| 成功 seeds | 0, 4 |
| 失敗 seeds | 1,2,3,5,6,7 |
| Repairer repaired | 6/6 |
| Repair 後總成功 | 8/8 |

觀察：post-key skill 對相似情境有幫助，但大多數失敗發生在 `before_key`，代表 Luna
尚未穩定學會「先找到 key」。

### V2：同時注入 before-key 與 post-key skills，未做 gating

第二輪在 prompt 中同時提供兩個 skills：

```text
navigate_to_key_before_door_open
navigate_to_goal_after_key
```

| 指標 | 結果 |
|---|---:|
| Luna-only success | 0/8 |
| 主要失敗型態 | before_key / blocked_motion |

觀察：新增 skill 後結果反而變差。這表示問題不是沒有 skill，而是 skills 被無條件暴露。
Luna 會把不同階段的 strategy/action pattern 混在一起，導致還沒撿 key 就套用 post-key 行為。

### V3：Stage-aware skill gating

第三輪新增簡單的 stage-aware gating：

```text
if door_open == False:
  only expose navigate_to_key_before_door_open
else:
  expose navigate_to_goal_after_key
```

| 指標 | 結果 |
|---|---:|
| Luna-only success | 0/8 |
| Repairer repaired | 8/8 |
| Repair 後總成功 | 8/8 |

觀察：gating 能避免不相關 skill 互相干擾，但 Luna 仍無法穩定將
`navigate_to key_position then pickMarker` 這種抽象 strategy hint 轉成正確 action sequence。
這說明 gating 是必要條件，但不是充分條件。

### V4：Stage-aware gating seed 0~15 sanity check

第四輪沿用 V3 的 stage-aware skill gating，但將範圍擴大到 seed `0~15`。

| 指標 | 結果 |
|---|---:|
| Luna-only success | 0/16 |
| before_key failures | 9 |
| after_key_before_goal failures | 7 |
| blocked_motion | 14 |
| incomplete_after_key_before_goal | 2 |
| Repairer repaired | 16/16 |
| Repair 後總成功 | 16/16 |

觀察：Luna-only 在 `0~15` 仍全部失敗，但失敗型態集中在兩個可修復階段：

```text
before_key
after_key_before_goal
```

這代表目前的 LLM one-shot policy generation 還不能獨立完成 DoorKey，但 failure
attribution 足夠穩定，Replanner 能根據階段選擇對應 repair strategy。

### V5：Stage-aware gating seed 0~31 sanity check

第五輪沿用同一份 prompt、同一份 skill memory，以及 stage-aware skill gating，
將實驗範圍擴大到 seed `0~31`，也就是 32 個 DoorKey 初始狀態。

| 指標 | 結果 |
|---|---:|
| Luna-only success | 0/32 |
| Luna-only steps mean | 17.31 |
| Luna-only steps range | 8~25 |
| source reward = -0.5 | 18 |
| source reward = -1.0 | 14 |
| after_key_before_goal failures | 18 |
| before_key failures | 14 |
| blocked_motion | 30 |
| incomplete_after_key_before_goal | 2 |
| `splice_post_key_navigation` repairs | 18 |
| `replan_via_key_then_goal` repairs | 14 |
| Repairer repaired | 32/32 |
| Repair 後總成功 | 32/32 |
| Repair steps mean | 15.66 |
| Repair steps range | 7~23 |

觀察：V5 的結果比 V4 更清楚。Luna-only 仍然完全無法獨立完成 DoorKey，
但失敗不是隨機散掉，而是集中在兩個階段：

```text
after_key_before_goal
before_key
```

這代表目前 Adaptive Core 的 failure attribution 與 Replanner decision rules
已經能穩定將 LLM policy failure 分流成兩種修復策略。

## V3 每個 Seed 的 Repair 結果

| Seed | Luna stage at failure | Repair strategy | Repair success | Repair steps |
|---:|---|---|---:|---:|
| 0 | after_key_before_goal | `splice_post_key_navigation` | true | 16 |
| 1 | before_key | `replan_via_key_then_goal` | true | 22 |
| 2 | before_key | `replan_via_key_then_goal` | true | 16 |
| 3 | after_key_before_goal | `splice_post_key_navigation` | true | 13 |
| 4 | after_key_before_goal | `splice_post_key_navigation` | true | 15 |
| 5 | before_key | `replan_via_key_then_goal` | true | 17 |
| 6 | after_key_before_goal | `splice_post_key_navigation` | true | 8 |
| 7 | before_key | `replan_via_key_then_goal` | true | 18 |

## 重要結論

第一，Luna one-shot policy generation 仍不可靠。即使提供 structured prompt、
environment state、learned skill context 和 stage-aware gating，Luna 仍會出現座標偏移、
撞牆、錯誤 `pickMarker` 或錯誤 `putMarker`。

第二，skills 目前更接近 macro-policy / strategy hint，而不是可直接執行的低階動作。
例如：

```text
navigate_to key_position then pickMarker
```

這句對人類很清楚，但對 one-shot LLM 來說，仍需要轉換成正確的 action sequence。
這個轉換過程若沒有 simulator feedback，就容易失準。

第三，Adaptive Core 是目前最可靠的部分。Evaluator 能發現 trace failure；
Replanner 能根據 failure stage 做 deterministic repair；Memory 則能保存修復後的技能與觀察。
在 V3 中，Luna-only 是 `0/8`，但進入 Adaptive Loop 後達到 `8/8`。
在 V4 sanity check 中，Luna-only 是 `0/16`，但進入 Adaptive Loop 後達到 `16/16`。
在 V5 sanity check 中，Luna-only 是 `0/32`，但進入 Adaptive Loop 後達到 `32/32`。

## 目前系統狀態

目前可以誠實描述為：

```text
Skill-GS 已能從 LLM 失敗 trace 中修復 DoorKey seed 0~31，
並把修復經驗累積為 before-key 與 post-key 兩類 macro-skills。
Luna 本身尚未穩定泛化，但 Evaluator/Replanner/Memory 的 Adaptive Loop 已能讓 seed 0~31 全部通過。
```

## 輸出檔案

| 類型 | 路徑 |
|---|---|
| V1 Luna skill-augmented outputs | `output\skill_gs\llm_generated_seed{seed}_openai_luna_skill_augmented_smoke.json` |
| V2 ungated outputs | `output\skill_gs\llm_generated_seed{seed}_openai_luna_skill_augmented_v2_smoke.json` |
| V3 gated outputs | `output\skill_gs\llm_generated_seed{seed}_openai_luna_skill_augmented_v3_gated_smoke.json` |
| V4 gated seed 0~15 outputs | `output\skill_gs\llm_generated_seed{seed}_openai_luna_skill_augmented_v4_gated_smoke.json` |
| V5 gated seed 0~31 outputs | `output\skill_gs\llm_generated_seed{seed}_openai_luna_skill_augmented_v5_gated_smoke.json` |
| V1 repair summary | `output\skill_gs\llm_repair_seed0_7_summary.json` |
| V3 repair summary | `output\skill_gs\llm_repair_seed0_7_v3_gated_summary.json` |
| V4 repair summary | `output\skill_gs\llm_repair_seed0_15_v4_gated_summary.json` |
| V5 repair summary | `output\skill_gs\llm_repair_seed0_31_v5_gated_summary.json` |
| Skill database | `output\skill_gs\llm_repair_skills_prompt_v4.json` |

## 驗證

本次變更後已跑 Skill-GS 測試：

```text
Ran 54 tests in 2.442s
OK
```

## 下一步

下一步不建議繼續盲目增加 prompt 說明，而是將 Replanner 的能力更明確地納入 demo：

```text
Luna generates an imperfect policy
-> Evaluator detects failure stage
-> Replanner repairs the policy
-> repaired policy succeeds
-> skill memory accumulates before-key/post-key macro-skills
```

若要進一步提升 Luna-only 成功率，可以考慮：

- 將 `navigate_to key_position` 展開成更具體的 local planner guidance。
- 讓 Luna 逐步產生 subgoal，而不是一次產出完整 action sequence。
- 將 Replanner 產生的 repair action sequence 壓縮成更清楚的 few-shot examples。

## Seed 0~31 實驗紀錄

本輪已執行 seed `0~31`，共 32 次 OpenAI API call。輸出採用獨立的 `v5_gated`
名稱，避免覆蓋 seed `0~15` 的 V4 sanity check。

本輪輸出命名：

```text
output\skill_gs\llm_generated_seed{seed}_openai_luna_skill_augmented_v5_gated_smoke.json
output\skill_gs\llm_repair_seed0_31_v5_gated_summary.json
```

Luna smoke run 使用設定：

```powershell
$env:OPENAI_API_KEY = [Environment]::GetEnvironmentVariable("OPENAI_API_KEY", "Machine")
$python = "C:\Users\haoch\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
$prompt = "C:\Users\haoch\Desktop\doorkey_one_shot_policy_v1.txt"
$skillStore = "output\skill_gs\llm_repair_skills_prompt_v4.json"

foreach ($seed in 0..31) {
  & $python scripts\skill_gs\run_llm_generated_smoke.py `
    --provider OpenAI `
    --model gpt-5.6-luna `
    --temperature 0 `
    --prompt-template $prompt `
    --skill-store $skillStore `
    --seed $seed `
    --reasoning-effort none `
    --max-output-tokens 512 `
    --output "output\skill_gs\llm_generated_seed${seed}_openai_luna_skill_augmented_v5_gated_smoke.json"
}
```

Luna 跑完後，執行 batch repair：

```powershell
& $python scripts\skill_gs\repair_llm_generated_batch.py `
  --input-glob "output\skill_gs\llm_generated_seed*_openai_luna_skill_augmented_v5_gated_smoke.json" `
  --output-dir "output\skill_gs\llm_repair_seed0_31_v5_gated" `
  --skill-store $skillStore `
  --summary-output "output\skill_gs\llm_repair_seed0_31_v5_gated_summary.json" `
  --source-label "skill_augmented_v5_gated_seed0_31"
```

本輪結果：

```text
Luna-only success: 0/32
Adaptive repair success: 32/32
failed repairs: 0
```

本輪 sanity check 顯示 repairer 對 seed `0~31` 為 `32/32`。這支持目前主張：
Luna one-shot 不是可靠 solver，但 Skill-GS 的 Evaluator/Replanner/Memory 可以將失敗 trace
轉成穩定可修復的 adaptive loop。
