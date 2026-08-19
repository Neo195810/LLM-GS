# 05 — 修復 DSLParseError 契約遺留的兩處回歸

**What to build:** ticket 01 把 parser 失敗改成統一丟出 `DSLParseError` 後，兩個既有呼叫端沒有跟著更新，導致 search-space 初始化在正常路徑下可能直接 crash，且巢狀 boolean 條件式驗證在 `python -O`（assertions 關閉）下會退化成未分類的裸 `Exception`，違反 ticket 01 「validation 不依賴 assert」的既有驗收標準。

**Blocked by:** 01 — 讓 DSL Validation Error 可直接修正

**Status:** ready-for-agent

- [ ] `prog_policies/search_space/latent_space.py` 的 `initialize_individual()` 與 `get_neighbors()` 對 `_decode()` 的例外處理，改為同時捕捉 `DSLParseError`（連同既有的 `AssertionError`、`IndexError`），使隨機取樣到的 malformed token 序列照原設計靜默重新取樣，而不是讓例外向上傳播。
- [ ] `prog_policies/base/dsl.py` 的 `_validate_external_tokens` 對 `not`/`and`/`or` 巢狀條件式，補上「巢狀 `c(...)` 的結束位置需與外層期望的結束位置對齊」的檢查，使多餘的 trailing token（例如 `not c( frontIsClear c) frontIsClear c)`）在這一層就被拒絕，不再依賴 `parse_str_list_to_node` 裡的 `assert prog_str_list[-1] == 'c)'` 兜底。
- [ ] 在 `python -O`（assertions 關閉）下重新執行同一組 malformed 巢狀條件式，仍必須得到 `DSLParseError`，不得落入未捕捉的裸 `Exception`。
- [ ] 新增回歸測試：(a) 對 `LatentSpaceSearchSpace`（或對應 search-space 類別）以會 decode 出 malformed token 序列的種子/latent 向量驅動 `initialize_individual`/`get_neighbors`，斷言不拋出未捕捉例外而是重新取樣；(b) 對本 ticket 描述的巢狀 boolean 表達式，分別在一般模式與 `python -O` 子行程下驗證兩者都拋出 `DSLParseError`（可比照 `tests/test_openai_proposer.py` 既有的 `-O` 子行程驗證手法）。
- [ ] 不更動 DSL 語法本身、不擴大既有 correction/token 上限、不改寫歷史 Invalid-output Artifacts。

## 背景

於 ticket 02 完成後的 code review（medium）中發現，非本次改動範圍但屬於已標記 completed 的 ticket 01 程式碼：

1. `prog_policies/search_space/latent_space.py:104` 與 `:132` — `_decode()` 現在會丟 `DSLParseError`（`ValueError` 子類別），但呼叫端仍只捕捉 `(AssertionError, IndexError)`，隨機取樣時常態性觸發、未捕捉即 crash。
2. `prog_policies/base/dsl.py:447` — `_validate_external_tokens` 對巢狀條件式的結構檢查不完整，正常模式下靠 `parse_str_list_to_node` 的 `assert` 補上，但 `python -O` 關閉 assertions 後會落入 `else: raise Exception(f'Unrecognized token: {token}.')`，不在 `parse_str_to_node` 的 `except (AssertionError, IndexError, KeyError, TypeError, ValueError)` 涵蓋範圍內，違反 ticket 01 「validation 在 assertions 關閉時仍維持相同行為」的既有驗收條件。
