# 04 — 保存可操作的私人證據並驗證完整 Protocol

**What to build:** 讓 Invalid-output Artifact 保留安全且可操作的 DSL validation evidence，同時維持 secret privacy、content-addressed persistence 與 public report 邊界；最後以匿名 production-pattern replay 和完整測試驗證新的 correction protocol。

**Blocked by:** 01 — 讓 DSL Validation Error 可直接修正；02 — 從重複 Invalid Output 恢復；03 — 發布有界且可完成的 Proposal Contract v2

**Status:** ready-for-agent

- [ ] 安全 DSL symbols（例如 typed closers 與 `ELSE`）保留在 validation evidence 中，不再因 credential-oriented `token:` pattern 被一律遮罩。
- [ ] API keys、environment secrets、bearer credentials、passwords 與其他 recognized secret patterns 在 response、diagnostic 和 correction prompt 中仍於 bounding 與 hashing 前被遮罩。
- [ ] Invalid-output Artifact、Attempt Store、Matrix Report、CLI 與 export schema 保持相容；public reports 仍只暴露安全 metadata。
- [ ] 使用 minimized anonymous fixtures replay 已觀察到的 delimiter、wrapper、`ELSE`、unexpected symbol、repeated output 與 incomplete JSON patterns；parser rejection 不再產生裸 `Invalid program`。
- [ ] focused proposer、parser、Task contract、persistence、report tests 與完整 pytest suite 全部通過。
- [ ] 不改寫歷史 artifacts、不執行付費 live matrix；後續 pilot 與可能的 6144-token protocol 留在本 ticket 範圍外。
