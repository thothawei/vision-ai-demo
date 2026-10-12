# 真實照片評估結果

由 `python scripts/evaluate.py --all` 產生。照片放在 `tests/real_samples/<動作>/`（格式見該目錄 README）。**表現差就照實寫**，不調整標註或門檻去配合數字。

更新日期：2026-10-12

| 模組 | 狀態 | 張數 | 正確 | 準確率 | 平均絕對誤差 | 平均耗時 | 拍攝裝置 |
|---|---|---|---|---|---|---|---|
| count | 真實照片實測 | 3 | 0 | 0% | 26.333 | 0.11 秒 | 網路取得的照片（Wikimedia Commons，授權見 SOURCES.md）；非產線相機 |
| measure | 待補真實照片（沒有 labels.json） | — | — | — | — | — | — |
| seven_segment | 真實照片實測 | 8 | 5 | 62% | — | 0.21 秒 | 網路取得的照片（Wikimedia Commons，授權見 SOURCES.md）；非產線相機 |
| gauge | 真實照片實測 | 3 | 1 | 33% | 13.037 | 0.43 秒 | 網路取得的照片（Wikimedia Commons，授權見 SOURCES.md）；非產線相機 |
| assembly | 待補真實照片（沒有 labels.json） | — | — | — | — | — | — |
| colordiff | 待補真實照片（沒有 labels.json） | — | — | — | — | — | — |
| shipping | 待補真實照片（沒有 labels.json） | — | — | — | — | — | — |

## 演算法改動紀錄

| 日期 | 模組 | 改動前 | 改動後 | 說明 |
|---|---|---|---|---|
| 2026-10-12 | seven_segment | 0/8 | 5/8 | 重寫判讀流程：兩種極性都試、分組（線段不相連）、覆蓋率判斷、較嚴格的門檻對付光暈。仍失敗的 3 張：計數器近拍（3 個暗淡數字標成 ?，整體判 NG 交人工，沒有讀錯）、兩張完整場景照（顯示器只占畫面一小塊，須近拍）。 |

## count

| 照片 | 結果 | 明細 |
|---|---|---|
| two_screws.jpg | 未通過 | 計數結果: 預期 2／實際 15 |
| bolts_and_nuts.jpg | 未通過 | 計數結果: 預期 10／實際 63 |
| two_screws_closeup.jpg | 未通過 | 計數結果: 預期 2／實際 15 |

## seven_segment

| 照片 | 結果 | 明細 |
|---|---|---|
| scale_lcd_112.jpg | 未通過 | 讀值: 預期 112／實際 5 |
| calculator_led.jpg | 未通過 | 讀值: 預期 31415927／實際 8 |
| beckman_77.jpg | 通過 | 讀值: 預期 77／實際 77 |
| led_clock_238.jpg | 通過 | 讀值: 預期 238／實際 238 |
| scale_lcd_112_closeup.jpg | 通過 | 讀值: 預期 112／實際 112 |
| calculator_led_closeup.jpg | 未通過 | 讀值: 預期 31415927／實際 ?1415?2? |
| beckman_77_closeup.jpg | 通過 | 讀值: 預期 77／實際 77 |
| led_clock_238_closeup.jpg | 通過 | 讀值: 預期 238／實際 238 |

## gauge

| 照片 | 結果 | 明細 |
|---|---|---|
| pool_gauge_0bar.jpg | 通過 | 讀值: 預期 0.0／實際 0.0 |
| manometer_104026.jpg | 未通過 | 讀值: 預期 9.8／實際 0.73 |
| round_thermometer.jpg | 未通過 | 讀值: 預期 23.5／實際 -6.54 |
