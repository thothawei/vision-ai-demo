# 外觀異常檢測：metal_nut（`anomaly-metal_nut`）

> 本檔由 `scripts/gen_model_cards.py` 依模型登錄表產生，請勿手改；模型或版本異動後重新產生。

## 用途

非監督式外觀異常檢測（PatchCore，固定 CPU）：只用良品照片擬合，回報整張影像的異常分數與熱力圖

## 目前啟用版本

- 版本：v1（登錄於 2026-09-29T13:50:44，登錄者 system:bootstrap）
- SHA-256：`fb0a72bd3b1b3a4d4d4c5cdc3d2dd29dc540766ac393ded9e3cb1c5c5699f9b2`
- 大小：238,152,287 bytes
- 備註：既有權重就地登錄為 v1

## 資料集與授權

- 資料集：MVTec AD（metal_nut）
- 授權：CC BY-NC-SA 4.0（非商用）：以此資料擬合的權重不得用於商業產線，正式導入需以自有良品照片重新擬合

## 指標（啟用版本）

| 指標 | 數值 |
|---|---|
| category | metal_nut |
| device | cpu |
| image_auroc | 0.9985 |
| fit_seconds | 322.2 |
| test_set_size | 115 |

## 版本歷史

| 版本 | 狀態 | 登錄時間 | 登錄者 | SHA-256（前 12 碼） | 備註 |
|---|---|---|---|---|---|
| v1 | active | 2026-09-29T13:50:44 | system:bootstrap | `fb0a72bd3b1b` | 既有權重就地登錄為 v1 |

## 已知限制

分數是 PatchCore 原始距離值，只有同一個模型版本內可比較；光源、角度與擬合照片不同會誤報；只能說哪裡異常，不能說是哪一種瑕疵。

## 不適用情境

拍攝條件與擬合照片明顯不同的場景；需要瑕疵分類的情境（請用監督式模型）。
