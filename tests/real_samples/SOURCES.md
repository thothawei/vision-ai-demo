# 真實照片來源與授權

這些照片都來自 Wikimedia Commons，下載的是 Commons 產生的縮圖（寬 1280 px 以內，未做其他處理）；`*_closeup.jpg` 是從同一張縮圖裁出顯示器或零件區域，只裁切、不調色。
各照片依來源授權使用，**散佈或再利用時須依授權標示作者與授權**；CC BY-SA 與 GFDL 的照片具相同方式分享條款，與本專案原始碼的授權（AGPL-3.0-or-later）是分開的。查證日：2026-10-12。

| 本專案檔案 | 來源頁面 | 作者 | 授權 |
|---|---|---|---|
| `gauge/pool_gauge_0bar.jpg` | https://commons.wikimedia.org/wiki/File:Man%C3%B3metro_3_psi_1.jpg | Amfeli | [CC BY 4.0](https://creativecommons.org/licenses/by/4.0) |
| `gauge/manometer_104026.jpg` | https://commons.wikimedia.org/wiki/File:Manometer_104026.jpg | Nord68 | [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0) |
| `gauge/round_thermometer.jpg` | https://commons.wikimedia.org/wiki/File:Round_dial_thermometer.jpg | Cjp24 | [CC BY-SA 3.0](https://creativecommons.org/licenses/by-sa/3.0) |
| `seven_segment/scale_lcd_112.jpg` | https://commons.wikimedia.org/wiki/File:2_carrots_on_a_digital_scale_measuring_112g.jpg | Datariumrex | [CC0](http://creativecommons.org/publicdomain/zero/1.0/deed.en) |
| `seven_segment/calculator_led.jpg` | https://commons.wikimedia.org/wiki/File:Commodore_calculator_-_model_SR7919_(18313124193).jpg | striegel | [CC BY 2.0](https://creativecommons.org/licenses/by/2.0) |
| `seven_segment/beckman_77.jpg` | https://commons.wikimedia.org/wiki/File:Beckman_SP-352.jpg | Wosch21149 | [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0) |
| `seven_segment/led_clock_238.jpg` | https://commons.wikimedia.org/wiki/File:LED-7-Segment-Display.jpg | RetroEditor | [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0) |
| `count/two_screws.jpg` | https://commons.wikimedia.org/wiki/File:Screws_EXP_054.JPG | Tomasz Sienicki（Commons 使用者 tsca） | [CC BY 4.0](https://creativecommons.org/licenses/by/4.0) |
| `count/bolts_and_nuts.jpg` | https://commons.wikimedia.org/wiki/File:18-03-16-Schrauben-M6x20_RRK3198.jpg | Ralf Roletschek | [GFDL 1.2](http://www.gnu.org/licenses/old-licenses/fdl-1.2.html) |

## 讀值與個數是怎麼來的

標註是我（Claude）逐張目視判讀，**不是儀器校準值**：指針錶量出圓心、刻度端點與指針的角度後線性內插（溫度計用兩種方式估出 23.0 與 23.8 °C，標註 23.5、容許 ±1.5）；七段顯示器與個數直接讀。裁切後放大再確認過數字。容許誤差約為滿刻度的 4–5%。

## 為什麼只有三個模組

`measure`（需要畫面中有已知尺寸的 ArUco 標記）、`assembly`（需要同一料號的黃金樣本與待測照片成對）、`colordiff`（需要有標準色的對照）、`shipping`（需要標籤上的料號／批號與預期值對應）無法從公開網路照片取得合用的資料，維持「待補真實照片」。
