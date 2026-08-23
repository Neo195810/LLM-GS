# Skill-GS Luna seed 0~7 Adaptive Loop 實驗報告

日期：2026-08-23
Branch：`Branch_NerdyClaush`
Repo：`F:\GitHub_Experiment\LLM-GS-team`

## 目的

本次實驗延續前一份 seed 0 小比較，將範圍擴大到 DoorKey seed `0~7`。
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
| `llm_repair.karel.doorkey.navigate_to_goal_after_key.v1` | 撿到 key 後，通過 door 到 goal | 0~7 | 15 | 1.0 |
| `llm_repair.karel.doorkey.navigate_to_key_before_door_open.v1` | door 尚未打開時，先到 key_position 並 pickMarker | 1,2,3,5,7 | 9 | 1.0 |

這裡的 `Evaluations` 是 repair observation 累積次數，`Source seeds` 是目前已觀察過的不同 seed。

## 實驗流程

本次共分成三輪 Luna seed `0~7` 測試。

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

## 目前系統狀態

目前可以誠實描述為：

```text
Skill-GS 已能從 LLM 失敗 trace 中修復 DoorKey seed 0~7，
並把修復經驗累積為 before-key 與 post-key 兩類 macro-skills。
Luna 本身尚未穩定泛化，但 Evaluator/Replanner/Memory 的 Adaptive Loop 已能讓 seed 0~7 全部通過。
```

## 輸出檔案

| 類型 | 路徑 |
|---|---|
| V1 Luna skill-augmented outputs | `output\skill_gs\llm_generated_seed{seed}_openai_luna_skill_augmented_smoke.json` |
| V2 ungated outputs | `output\skill_gs\llm_generated_seed{seed}_openai_luna_skill_augmented_v2_smoke.json` |
| V3 gated outputs | `output\skill_gs\llm_generated_seed{seed}_openai_luna_skill_augmented_v3_gated_smoke.json` |
| V1 repair summary | `output\skill_gs\llm_repair_seed0_7_summary.json` |
| V3 repair summary | `output\skill_gs\llm_repair_seed0_7_v3_gated_summary.json` |
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
