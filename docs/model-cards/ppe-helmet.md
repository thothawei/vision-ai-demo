# 安全帽偵測（`ppe-helmet`）

> 本檔由 `scripts/gen_model_cards.py` 依模型登錄表產生，請勿手改；模型或版本異動後重新產生。

## 用途

監督式物件偵測（YOLO11n）：已戴安全帽（helmet）與未戴安全帽（head）

## 目前啟用版本

- 版本：v1（登錄於 2026-09-29T13:50:43，登錄者 system:bootstrap）
- SHA-256：`3b54cc7e1feb5db3a5c0b5b5e1b9200a6ab4a393b8b6722a399c891759939e97`
- 大小：5,455,322 bytes
- 備註：既有權重就地登錄為 v1

## 資料集與授權

- 資料集：Hard Hat Workers（5297 張訓練、1766 張測試，沿用資料集官方切分）
- 授權：資料集 CC0 1.0；權重衍生自 Ultralytics YOLO11n（AGPL-3.0）；散佈與網路服務義務見 docs/licenses.md

## 指標（啟用版本）

| 指標 | 數值 |
|---|---|
| mAP50 | 0.977 |
| mAP50-95 | 0.68 |
| precision | 0.948 |
| recall | 0.942 |
| test_set_size | 1766 |
| 來源 | docs/dev/test-log.md「Phase 5：功能驗證」（官方測試集） |

## 版本歷史

| 版本 | 狀態 | 登錄時間 | 登錄者 | SHA-256（前 12 碼） | 備註 |
|---|---|---|---|---|---|
| v1 | active | 2026-09-29T13:50:43 | system:bootstrap | `3b54cc7e1feb` | 既有權重就地登錄為 v1 |

## 已知限制

只有 helmet／head 兩類，沒有反光背心等其他防護具；召回率 0.942，約 6% 的未戴安全帽可能漏判。

## 不適用情境

不可當作唯一的工安判定；遠距離或遮擋嚴重的場景。
