# LLM-GS V2 第三環境候選研究

日期：2026-08-12

## 結論

建議把 **TextWorld** 作為 V2 的第一個第三環境試點，**Craftax** 作為偏重大量 episode 與長時程能力的第二順位，**HighwayEnv** 作為偏重連續狀態、反應式安全控制的替代方案。若研究問題明確要測試形式規劃模型或多智能體博弈，再分別選 **pyRDDLGym** 或 **OpenSpiel**；它們不宜在沒有縮小任務語義前直接成為通用第三環境。

第三環境應是**新增，而不是取代** V2 第一階段的 Karel 與 MiniGrid。既有四個任務已經承擔向後可比性、adapter 等價性、seed suite、失敗證據與 paired-budget protocol 的基準角色；現在替換會同時改變環境與評估系統，難以判斷回歸來自哪一層。較穩健的順序是先完成既定 initial slice，再以一個窄任務做 adapter pilot，通過 replay、evidence schema、成本與授權閘門後才納入正式 benchmark。

## 研究範圍與判準

本研究只採用官方 repository、官方文件、套件索引與原始論文。評估的是「適不適合成為 LLM-GS V2 的 programmatic policy synthesis benchmark」，不是一般 RL benchmark 的流行度。判準如下：

1. 能否由 V2 DSL 表示有限且可驗證的 policy，而不是要求模型直接產生任意 Python。
2. seed、初始狀態與 action trace 能否重播；若有 chance node，是否能記錄其結果。
3. 能否輸出結構化 failure evidence，而不只是一個 scalar reward。
4. 能否低成本執行大量 episode，並以 episode wall time、timeout 與 trace 大小實測。
5. 截至研究日期仍有維護，且可在 Python 3.11 使用。
6. 相對 Karel/MiniGrid 是否新增實質能力維度，例如語言 grounding、長時程資源管理、連續動力學或多智能體推理。

「環境有自己的 DSL」不等於「它已經符合 V2 policy DSL」。正式整合仍需 adapter 定義固定 observation predicates、actions、termination、evidence 與 cost accounting；禁止把任意文字或任意 Python 當作繞過 V2 DSL 驗證的捷徑。

## 比較總表

| 候選 | Policy synthesis 適配 | Seed／replay | 結構化 evidence | 大量 episode | Python 3.11／維護 | 相對既有環境的新能力 | 建議 |
|---|---|---|---|---|---|---|---|
| TextWorld | 高：受限文字命令與世界 facts 可映射為 predicates/actions | 高：分離 generation seeds、可序列化 game；凍結 game + command trace | 很高：facts、win/fail facts、last action、won/lost、admissible/policy commands | 中：支援 multiprocessing batch，但有文字遊戲 runtime | 1.7.0，2026-01-30；Python 3.9–3.12 | 語言 grounding、物件／任務推理、文字回饋 | **首選 pilot** |
| Craftax | 中高：symbolic observation + 離散 action，需另定規則 DSL | 很高：reset/step 都顯式傳 JAX PRNG key | 中：67 achievements 很好；死亡與因果證據需 adapter 衍生 | 很高：JAX/vectorization；論文報告最高約 Crafter 250× | 1.6.1，2026-06-20；Python ≥3.9 | 長時程生存、製作、資源與科技樹 | **scale-first 備選** |
| HighwayEnv | 中高：少量 meta-actions 適合條件式 policy | 中：Gymnasium seed + action trace；浮點／平台等價性需實測 | 中低：可由車輛狀態、碰撞、TTC 衍生，原生 taxonomy 較弱 | 高：官方提供 highway-fast-v0 給大規模訓練 | 1.12.0，2026-07-06；Python ≥3.10 | 連續狀態、交通互動、反應式安全 | **安全控制替代** |
| pyRDDLGym | 高但語義較重：RDDL 是正式模型語言，2.7 也有 policy blocks | 高：reset/evaluate 支援 seed；須凍結 domain/instance | 高：preconditions、invariants、termination、fluent dict 與 logs | 中高：有 JAX backend 與 vectorized simulation | 2.7，2026-03-24；Python 3.8–3.14 | 隨機／連續／並行／關聯式規劃 | **形式規劃專案候選** |
| OpenSpiel | 中：離散 legal actions 清楚，但 joint/opponent policy 擴大 DSL 語義 | 高（確定性遊戲）；隨機遊戲須另錄 chance/opponent | 中：history、legal actions、terminal returns 完整，因果解釋需衍生 | 高：C++ core，許多小型遊戲 | 2.0.1，2026-07-17；有 CPython 3.11 wheels | 對抗、合作、不完全資訊 | **僅在明確要測博弈時** |
| NLE | 低中：動作／介面狀態龐大，規則 DSL 容易膨脹 | 中：可 seed、可留 TTYREC；仍須驗證跨平台 replay | 高但龐大：glyphs、stats、messages、inventory、TTYREC | 中低：長 horizon、原生依賴與複雜介面 | 1.3.0，2026-04-25；Python ≥3.10、有 3.11 wheels | 極長時程、程序生成、部分可觀察性 | 暫不採用 |
| LLE | 中：可用 action sets，但需 joint/decentralized policy 語義 | 中高：seeded world generation；action trace 仍須固定 agent ordering | 中：available actions 與 world state 可用，協調失敗需衍生 | 高 | 2.11.0，2026-08-09；Python ≥3.10、有 3.11 wheels | 合作與互賴 | 有趣但仍偏 gridworld |

## 候選詳析

### 1. TextWorld：最適合驗證「從語言到可執行 policy」

TextWorld 的核心優勢不是「它是文字遊戲」，而是它已經暴露出很接近 V2 evidence contract 的結構。官方 `EnvInfos` 可請求 `facts`、`win_facts`、`fail_facts`、`last_action`、`last_command`、`won`、`lost`、`admissible_commands`、`policy_commands`、objective 與 score；quest 也正式區分 win/fail events。[官方 API 原始碼](https://textworld.readthedocs.io/en/stable/_modules/textworld/core.html) [game/quest 文件](https://textworld.readthedocs.io/en/stable/textworld.generator.game.html)

生成器把 map、objects、quest、grammar seeds 分開，且 game 可序列化；因此 replay artifact 應保存產生後的 game、所有 seed、canonical command trace 與套件版本，而不是只存一個整數 seed。官方 Gym wrapper 另提供 asynchronous multiprocessing batch environment 與最大步數控制，但其真實吞吐仍應在 CI 機器實測。[生成與序列化文件](https://textworld.readthedocs.io/en/stable/textworld.generator.game.html) [batch environment 文件](https://textworld.readthedocs.io/en/stable/textworld.gym.envs.html)

政策介面應採「有限 predicate + canonical command」：例如 `at(obj, room)`、`open(container)`、`inventory(obj)` 與一組 adapter 核准的命令模板。不能讓候選程式輸出任意自然語言，否則 parser 容錯、同義詞與模型文風會混入 policy quality。首個任務宜選短 horizon、固定 vocabulary、含明確 win/fail condition 的 quest。

維護面目前良好：PyPI 的 1.7.0 發布於 2026-01-30，要求 Python ≥3.9，列出 3.11 支援。[PyPI](https://pypi.org/project/textworld/) 主要風險是 runtime 較 JAX 環境重、Linux/macOS 支援範圍，以及套件內 Inform7、Jericho、Fast Downward 等元件各有授權；正式散布 benchmark artifact 前必須依[官方 repository 的授權說明](https://github.com/microsoft/TextWorld)做逐項審查。

### 2. Craftax：吞吐與長時程能力最佳

Craftax 的 reset/step API 顯式接收 JAX PRNG key，並提供 symbolic observation 與離散 action space，這使 seed discipline、純函式 state transition 與批次執行很適合 benchmark harness。[官方套件頁與使用例](https://pypi.org/project/craftax/) 其 ICML 2024 原始論文報告相對 Crafter 最高約 250 倍加速，單 GPU 一小時內可做十億次 interaction；同一論文以 67 個 achievements 描述進度，涵蓋探索、戰鬥、製作與 boss 等長期依賴。[原始論文頁](https://openreview.net/forum?id=hg4wXlrQCV) [論文 PDF](https://openreview.net/pdf?id=hg4wXlrQCV)

它新增的是資源、inventory、科技樹與長 horizon，而非另一個 DoorKey。建議保存 initial key、每一步 split key/action、environment state hash 與 achievement vector。主要缺口是「沒拿到 achievement」不等於可操作的 failure explanation；adapter 必須額外產生 death cause、資源瓶頸、不可達 prerequisite、timeout 與最後 N 步因果摘要。觀測欄位應以[官方 symbolic observation 說明](https://github.com/MichaelTMatthews/Craftax/blob/main/obs_description.md)固定版本。

截至研究日期，PyPI 最新版 1.6.1 發布於 2026-06-20，要求 Python ≥3.9。[PyPI](https://pypi.org/project/craftax/) 風險是它仍有強烈二維空間成分；只有當評分涵蓋長期資源依賴與多階段目標，它才真正超越 MiniGrid。

### 3. HighwayEnv：最小動作面積的連續／安全控制選項

HighwayEnv 的 `DiscreteMetaAction` 只有 lane-left、idle、lane-right、faster、slower 等高階動作，也可選離散或連續控制；這很適合編譯成小型條件式 policy。[官方 action 文件](https://highway-env.farama.org/actions/index.html) Kinematics 與 time-to-collision 類 observation 可支援如相對距離、相對速度、lane、TTC 的 predicates。[官方 observation 文件](https://highway-env.farama.org/observations/)

它的新增能力是連續動力學、交通互動與安全 trade-off。官方 repository 明列 `highway-fast-v0` 是為大規模訓練降低 simulation accuracy 的快速版本。[官方 repository](https://github.com/Farama-Foundation/HighwayEnv) 但 failure evidence 不是現成產品：需要 adapter 固定碰撞、出道路、危險 TTC、無效換道、效率不足與 timeout 等 taxonomy。Replay 應保存 Gymnasium seed、完整 action trace、環境 config 與版本；因浮點與物理更新可能受版本／平台影響，必須以跨兩次 process 的 state/evidence hash 測試，而不能僅由 seed API 推定完全等價。[Gymnasium seed semantics](https://github.com/Farama-Foundation/Gymnasium/blob/main/gymnasium/core.py)

PyPI 1.12.0 發布於 2026-07-06，要求 Python ≥3.10，故涵蓋 3.11。[PyPI](https://pypi.org/project/highway-env/) 若希望第三環境最少改動 DSL，這個候選比 Craftax 簡單；若研究主題是語言到程式合成，它則不如 TextWorld 有辨識力。

### 4. pyRDDLGym：形式模型最強，但 benchmark 邊界最難控制

RDDL 可描述 reward、action preconditions、state invariants 與 termination；pyRDDLGym 2.7 更加入 policy block，可宣告參數、policy internal state 與 action CPFs。[官方 RDDL 文件](https://pyrddlgym.readthedocs.io/en/latest/rddl.html) 官方介面支援 seed、constraint checking、結構化 fluent dictionaries、CSV/debug logs，也提供 JAX backend 與 vectorized simulation。[入門與執行文件](https://pyrddlgym.readthedocs.io/en/latest/start.html) [JAX backend](https://pyrddlgym.readthedocs.io/en/latest/jax.html)

這使它在「模型與限制條件可機讀」方面甚至優於 TextWorld。然而 RDDL 主要是環境／決策過程的模型語言，不會自動替 V2 解決候選 policy DSL、錯誤歸因與搜尋成本控制。官方 repository 集合含 IPPC 2011/2014/2018/2023 等大量 domain；若全部納入，benchmark 會從單一第三環境膨脹成一個異質 suite。[RDDL repository 文件](https://pyrddlgym.readthedocs.io/en/latest/rddlrepo.html)

因此它適合獨立的「formal planning」研究線；若試點，應只鎖一個 domain、一個 instance family 與有限 action fluents，並先驗證 JAX 與 reference simulator 的 transition/evidence 等價性。PyPI 2.7 發布於 2026-03-24，支援 Python 3.8 至小於 3.15。[PyPI](https://pypi.org/project/pyrddlgym/)

### 5. OpenSpiel：多智能體需求成立時才值得引入

OpenSpiel 統一支援合作、零和／一般和、輪流／同時動作、完全／不完全資訊等遊戲。[官方 repository](https://github.com/google-deepmind/open_spiel) State API 可取得 legal actions；state serialize/deserialize 預設能以 action history 重建狀態。[legal actions API](https://openspiel.readthedocs.io/en/stable/api_reference/state_legal_actions.html) [serialization API](https://openspiel.readthedocs.io/en/stable/api_reference/state_serialize.html) 2.0.1 於 2026-07-17 發布並提供 CPython 3.11 wheels。[PyPI](https://pypi.org/project/open-spiel/)

它可帶來真正的新維度：對手建模、協調、不完全資訊。但是「policy 失敗」可能來自自身決策、對手策略或 chance outcome；paired comparison 也必須固定 opponent policy 與 chance trace。若採用，只能先選官方 game matrix 中狀態小、規則清楚的單一遊戲，並明確定義 centralized 或 per-player policy。[官方 game matrix](https://github.com/google-deepmind/open_spiel/blob/master/docs/games.md)

### 6. 暫不列入 shortlist：NLE、LLE、PDDLGym 系列

NLE 現在由 NetHack-LE 維護，並非舊 Facebook archived repository 所呈現的停止狀態。PyPI 1.3.0 發布於 2026-04-25，要求 Python ≥3.10 且提供 3.11 wheels；它提供 Gymnasium 介面、TTYREC 與 NetHack 的程序生成長時程世界。[PyPI](https://pypi.org/project/nle/) [現行 repository](https://github.com/NetHack-LE/nle) 原始論文說明 glyphs、stats、messages 與 inventory 等豐富觀測。[NeurIPS 2020 論文](https://proceedings.neurips.cc/paper/2020/file/569ff987c643b4bedf504efda8f786c2-Paper.pdf) 但龐大動作／介面語義、長 episode、原生依賴與 attribution 成本都不適合作為第一個第三 adapter。

Laser Learning Environment（LLE）很活躍：2.11.0 於 2026-08-09 發布，要求 Python ≥3.10 且提供 3.11 wheels。[PyPI](https://pypi.org/project/laser-learning-environment/) 原始論文刻意設計 cooperative interdependence 與 zero-incentive dynamics，並有 available-action sets 可阻擋無效動作。[原始論文](https://openreview.net/forum?id=IPfdjr4rIs) [論文 PDF](https://openreview.net/pdf?id=IPfdjr4rIs) 然而它仍是 gridworld，且引入 joint/decentralized policy 後，V2 DSL 與 failure attribution 的複雜度會大幅上升；若未明確研究協調，不如 OpenSpiel 或先保留 MiniGrid。

PDDLGym/PDDLGymnasium 的 relational literals、preconditions 與 PDDL problem files 在概念上乾淨，[原始 PDDLGym 論文](https://arxiv.org/abs/2002.06432)與[官方 repository](https://github.com/tomsilver/pddlgym)也適合規劃研究；但若今天新選形式規劃後端，pyRDDLGym 的近期 2.7 發布、RDDL policy blocks、JAX backend 與 IPPC repository 提供較完整的成長路徑。Crafter 則應由維護活躍且 JAX 化的 Craftax 取代。Jumanji 雖高速且 JAX-native，但 22 個異質問題不利於形成一套窄而一致的 DSL 與 evidence contract，因此未列入 shortlist。

## 建議 shortlist 與執行順序

1. **TextWorld：預設選擇。** 先做一個 10–30 步、固定詞彙、明確 win/fail facts 的 quest；它最能測 V2 的語言規格、規則編譯與結構化診斷是否真的泛化。
2. **Craftax：吞吐／長時程選擇。** 若核心目標是用低成本增加 episode 數並測資源依賴，選 symbolic Craftax，但只在 adapter 能產生因果 failure taxonomy 時升格。
3. **HighwayEnv：安全／反應式選擇。** 若希望以較小 policy action surface 引入連續狀態與安全控制，選 `highway-fast-v0`，並先通過跨 process replay 驗證。

pyRDDLGym 與 OpenSpiel 是「研究問題驅動」的候選，不應靠綜合分數自動排進前三：前者會把工作重心移向形式規劃模型，後者會把 evaluation unit 改成包含 opponent/chance 的互動系統。

## 升格為正式 benchmark 前的 gate

每個 pilot 都應用同一份最小驗收：

- 在 Python 3.11 的乾淨環境安裝，記錄 wheel/native dependency 與完整授權清單。
- 固定 100 個 seed，每個 seed 以同一 policy 重跑兩個獨立 process；比較 terminal status、逐步 evidence hash、score 與 action count。
- 建立至少 success、invalid action、unsatisfied precondition／unsafe state、timeout、runtime error 五類 evidence；不存在的類型要明確標示 not applicable。
- 分別測單 episode 與 batch 的 p50/p95 wall time、峰值記憶體與 trace bytes；成本數字須來自 V2 CI 目標機，而不是只引用論文吞吐。
- 以一個 handwritten oracle policy、一個已知失敗 policy 與一個語義等價 policy 驗證 adapter、canonicalization 與 paired-budget accounting。
- 第三環境只在以上 gate 全通過後加入 formal evaluation；在此之前不得改寫 Karel/MiniGrid 的 baseline 結果或 initial-phase acceptance criteria。

最終建議是：**V2 第一階段維持 Karel + MiniGrid；完成後新增 TextWorld pilot。** 如果 TextWorld 的 runtime 或授權 gate 不通過，依研究目的改用 Craftax（吞吐與長時程）或 HighwayEnv（連續安全控制），而不是移除既有環境來騰位置。
