# 03 — 發布有界且可完成的 Proposal Contract v2

**What to build:** 發布 versioned Proposal Contract v2，使模型輸出保持短小、完整且符合 Task-specific DSL。對 incomplete provider response 提供專屬 Correction Feedback，並修正 Karel／MiniGrid prompt contract，降低 schema-valid 但 DSL-invalid 的輸出率，同時維持既有 4096-token limit。

**Blocked by:** 02 — 從重複 Invalid Output 恢復

**Status:** ready-for-agent

- [ ] Structured Output contract 使用 `candidate_program_v2`，要求 non-empty source、禁止額外欄位，並將 source 上限設為 2,000 characters。
- [ ] provider status 為 incomplete 時，在 generic schema extraction 前產生專屬 schema-stage diagnostic，要求完整 JSON、較短 source 與較淺的 control-flow nesting。
- [ ] 初始 Task prompt 與 Correction Feedback 都陳述 2,000-character limit、簡短 delimiter checklist，並提供 parser-valid nested-control example。
- [ ] MiniGrid Task contract 正確區分 object type 與 object color 的值域，且 prompt examples 能通過同一個 local parser。
- [ ] output-token limit 維持 4096、correction 上限維持兩次；新 schema 與 prompt hash 導致的新 Experiment Manifest 和 Experiment ID 被視為新 protocol。
- [ ] request-contract、Task-prompt、repair-prompt 與 incomplete-response behavioral tests 通過。
