# 01 — 讓 DSL Validation Error 可直接修正

**What to build:** 當 Karel 或 MiniGrid Candidate Program 無法通過 DSL validation 時，讓 parser 產生可操作的結構化診斷，並讓 OpenAIProposer 將該診斷放入 bounded、self-contained 的 Correction Feedback。診斷必須指出失敗 construct、局部 symbol 位置、expected、actual 或 end-of-input，以及短 context，讓下一次 correction 能先修正第一個結構錯誤。

**Blocked by:** None — can start immediately

**Status:** ready-for-agent

- [ ] Karel 與 MiniGrid 對 malformed program wrapper、錯誤 opener、缺少 closer、錯誤 `ELSE`、invalid repeat count、MiniGrid feature delimiter 與 unexpected symbol 產生可操作診斷，不再只回傳裸 `Invalid program`。
- [ ] 外部 DSL 輸入的 validation 不依賴 Python `assert`，在 assertions 關閉時仍維持相同行為。
- [ ] OpenAIProposer 的 Correction Feedback 包含 bounded parser diagnostic，且 parser-valid Candidate Program 的既有行為不變。
- [ ] TextWorldPilot 保持既有 fixed-vocabulary parser 與 task-specific 錯誤契約。
- [ ] 直接 parser 測試與最高層 proposer retry 測試覆蓋上述行為並通過。
