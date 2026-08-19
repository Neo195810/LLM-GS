# 02 — 從重複 Invalid Output 恢復

**What to build:** 當模型在 proposal 或 repair 中重複相同的 invalid output 時，讓下一個 bounded correction request 明確不同，包含 correction ordinal 與 repeated-output warning，要求產生 structurally different 的完整 replacement，避免 Model Budget 花在 byte-identical request 和 response 上。

**Blocked by:** 01 — 讓 DSL Validation Error 可直接修正

**Status:** completed

- [x] 每個 proposal 或 repair request 只在自身範圍內追蹤 normalized invalid-output fingerprint，不跨 Work Unit 或 Execution 共用狀態。
- [x] 每個 correction request 包含 one-based ordinal；重複 fingerprint 時額外包含 repeated-output warning。
- [x] 相同 invalid response 連續出現時，兩次 correction prompt 不相同，且 deterministic fake client 可在看到 warning 後返回有效 Candidate Program。
- [x] Correction Feedback 保持 self-contained、bounded，且不使用 previous response ID 或隱含 API conversation state。
- [x] correction 上限維持兩次；Model Output Failure、Model Budget、initial/repair artifact persistence 的既有分類與計數保持正確。
