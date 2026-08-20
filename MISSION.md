# Mission

## Why

理解並改善 `matrix run` 的執行時間，先能從程式碼與實際計數看出 LLM request 是在哪些層次被重複放大的。

## Current target

能用「arms × candidates × repair × correction」解釋一次 matrix run 的 request 上限，並定位到對應程式碼。
