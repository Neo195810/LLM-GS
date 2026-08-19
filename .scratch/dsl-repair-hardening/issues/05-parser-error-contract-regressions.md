# 05 — 修復 DSLParseError 契約遺留的兩處回歸

**What to build:** ticket 01 把 parser 失敗改成統一丟出 `DSLParseError` 後，兩個既有呼叫端沒有跟著更新，導致 search-space 初始化在正常路徑下可能直接 crash，且巢狀 boolean 條件式驗證在 `python -O`（assertions 關閉）下會退化成未分類的裸 `Exception`，違反 ticket 01 「validation 不依賴 assert」的既有驗收標準。

**Blocked by:** 01 — 讓 DSL Validation Error 可直接修正

**Status:** completed

- [x] `prog_policies/search_space/latent_space.py` 的 `initialize_individual()` 與 `get_neighbors()` 對 `_decode()` 的例外處理，改為同時捕捉 `DSLParseError`（連同既有的 `AssertionError`、`IndexError`），使隨機取樣到的 malformed token 序列照原設計靜默重新取樣，而不是讓例外向上傳播。
- [x] `prog_policies/base/dsl.py` 的 `_validate_external_tokens` 對 `not`/`and`/`or` 巢狀條件式，補上「巢狀 `c(...)` 的結束位置需與外層期望的結束位置對齊」的檢查，使多餘的 trailing token（例如 `not c( frontIsClear c) frontIsClear c)`）在這一層就被拒絕，不再依賴 `parse_str_list_to_node` 裡的 `assert prog_str_list[-1] == 'c)'` 兜底。新增 `_validate_boolean_expression` 遞迴驗證每個 `not`/`and`/`or` 子表達式的結束位置與外層期望對齊；同時把 `parse_str_list_to_node` 最後 fallback 的裸 `raise Exception(...)` 改成 `raise ValueError(...)`，作為額外防線納入既有的 `except (..., ValueError)` 範圍。
- [x] 在 `python -O`（assertions 關閉）下重新執行同一組 malformed 巢狀條件式，仍必須得到 `DSLParseError`，不得落入未捕捉的裸 `Exception`。
- [x] 新增回歸測試：(a) `tests/test_latent_space.py` 用不執行 LEAPS 模型載入的 bare `LatentSpace`（monkeypatch `_decode`）驅動 `initialize_individual`/`get_neighbors`，斷言 `DSLParseError` 被重新取樣邏輯吸收而非向上傳播（本機環境無 `torch`，模組以 `pytest.importorskip` 優雅 skip，程式碼路徑已由型別與邏輯覆核）；(b) `tests/test_openai_proposer.py` 新增兩則測試，對本 ticket 描述的巢狀 boolean 表達式分別在一般模式與 `python -O` 子行程下驗證都拋出 `DSLParseError`，比照既有 MiniGrid `-O` 子行程驗證手法。
- [x] 不更動 DSL 語法本身、不擴大既有 correction/token 上限、不改寫歷史 Invalid-output Artifacts。

## Code review 追加修正

初版 `_validate_boolean_expression` 的 leaf 分支假設「非 not/and/or 的 boolean expression 一定只有一個 token」，導致 MiniGrid 的多 token feature（`front_object_type h( <color> h)`、`front_object_color h( <object> h)`）作為條件時（無論在 IF/WHILE 頂層或巢狀於 not/and/or 底下）被誤判為 invalid，回歸破壞既有合法程式。已修正為：leaf 若後接 `h(`，改用既有的 `_matching_close` 找到對應 `h)`，要求該範圍剛好落在期望的結束位置。已補 3 則 `test_minigrid_multitoken_feature_as_condition_remains_accepted` 參數化測試涵蓋頂層、`not` 巢狀、`and` 巢狀三種情境。

## 背景

於 ticket 02 完成後的 code review（medium）中發現，非本次改動範圍但屬於已標記 completed 的 ticket 01 程式碼：

1. `prog_policies/search_space/latent_space.py:104` 與 `:132` — `_decode()` 現在會丟 `DSLParseError`（`ValueError` 子類別），但呼叫端仍只捕捉 `(AssertionError, IndexError)`，隨機取樣時常態性觸發、未捕捉即 crash。
2. `prog_policies/base/dsl.py:447` — `_validate_external_tokens` 對巢狀條件式的結構檢查不完整，正常模式下靠 `parse_str_list_to_node` 的 `assert` 補上，但 `python -O` 關閉 assertions 後會落入 `else: raise Exception(f'Unrecognized token: {token}.')`，不在 `parse_str_to_node` 的 `except (AssertionError, IndexError, KeyError, TypeError, ValueError)` 涵蓋範圍內，違反 ticket 01 「validation 在 assertions 關閉時仍維持相同行為」的既有驗收條件。
