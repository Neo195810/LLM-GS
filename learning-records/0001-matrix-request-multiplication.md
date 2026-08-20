# Learning Record 0001: matrix request multiplication

## Learned

`matrix run` 的延遲主要來自多層有限迴圈相乘，而不是單一無限迴圈：48 個 arms 依序執行；每個 arm 依 search strategy 產生 1 或 4 個候選；失敗時可再 repair 一輪；每次候選因 JSON／DSL 校正最多發出 3 次 request。

## Evidence

- `src/llm_gs/matrix.py:20-28`
- `src/llm_gs/cli.py:229-238`
- `src/llm_gs/execution.py:357-450`
- `src/llm_gs/proposer.py:228-287`

## Next question

如何在不破壞實驗公平性的前提下，加入 request tracing、跨 arm cache 或平行化？
