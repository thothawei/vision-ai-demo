# 真實照片評估結果

由 `python scripts/evaluate.py --all` 產生。照片放在 `tests/real_samples/<動作>/`（格式見該目錄 README）。**表現差就照實寫**，不調整標註或門檻去配合數字。

更新日期：2026-10-12

| 模組 | 狀態 | 張數 | 正確 | 準確率 | 平均絕對誤差 | 平均耗時 | 拍攝裝置 |
|---|---|---|---|---|---|---|---|
| count | 真實照片實測 | 12 | 8 | 67% | 2.273 | 0.41 秒 | 網路取得的照片（Wikimedia Commons，授權見 SOURCES.md）；非產線相機 |
| measure | 待補真實照片（沒有 labels.json） | — | — | — | — | — | — |
| seven_segment | 真實照片實測 | 8 | 5 | 62% | — | 0.21 秒 | 網路取得的照片（Wikimedia Commons，授權見 SOURCES.md）；非產線相機 |
| gauge | 真實照片實測 | 6 | 6 | 100% | 1.077 | 0.34 秒 | 網路取得的照片（Wikimedia Commons，授權見 SOURCES.md）；非產線相機 |
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
| two_screws.jpg | 通過 | 計數結果: 預期 2／實際 2 |
| bolts_and_nuts.jpg | 未通過 | 計數結果: 預期 9／實際 3 |
| two_screws_closeup.jpg | 通過 | 計數結果: 預期 2／實際 2 |
| four_screws_4.jpg | 通過 | 計數結果: 預期 4／實際 4 |
| wood_screw_1.jpg | 通過 | 計數結果: 預期 1／實際 1 |
| resistors_6.jpg | 通過 | 計數結果: 預期 6／實際 6 |
| resistors_3.jpg | 未通過 | 計數結果: 預期 3／實際 4 |
| gaskets_5.jpg | 通過 | 計數結果: 預期 5／實際 5 |
| ceramic_balls_5.jpg | 通過 | 計數結果: 預期 5／實際 5 |
| nut_hardware_7.jpg | 未通過 | 計數結果: 預期 7／實際 21 |
| orings_5.jpg | 未通過 | 計數結果: 預期 5／實際 1 |
| bottle_cap_1.jpg | 通過 | 明確拒絕（設計內的行為）：畫面邊緣沒有可參考的背景（零件占滿畫面，或背景雜亂），無法計數；請把零件放在素色背景上、四周留一點空白 |

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
| manometer_104026.jpg | 通過 | 讀值: 預期 0.0／實際 0.05 |
| round_thermometer.jpg | 通過 | 讀值: 預期 23.5／實際 23.37 |
| hygrometer_33.jpg | 通過 | 讀值: 預期 33.5／實際 33.98 |
| boiler_gauge_175.jpg | 通過 | 讀值: 預期 175.0／實際 179.68 |
| india_gauge_21psi.jpg | 通過 | 讀值: 預期 21.0／實際 19.88 |
