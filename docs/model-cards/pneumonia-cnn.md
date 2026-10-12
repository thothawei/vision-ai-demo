# 醫學影像分類展示（肺炎）（`pneumonia-cnn`）

> 本檔由 `scripts/gen_model_cards.py` 依模型登錄表產生，請勿手改；模型或版本異動後重新產生。

## 用途

小型 CNN 二元分類（normal／pneumonia），僅供技術展示

## 目前啟用版本

- 版本：v1（登錄於 2026-09-29T13:50:43，登錄者 system:bootstrap）
- SHA-256：`35755566c105f838c79d6f3e4b98ff7770850096f37a2f54aa151481d2437444`
- 大小：424,241 bytes
- 備註：既有權重就地登錄為 v1

## 資料集與授權

- 資料集：PneumoniaMNIST（MedMNIST，28x28 灰階；train 4708／val 524／test 624）
- 授權：CC BY 4.0（需署名）；官方註明非臨床用途

## 指標（啟用版本）

| 指標 | 數值 |
|---|---|
| dataset | PneumoniaMNIST（CC BY 4.0，僅供技術展示，非醫療診斷用途） |
| test_acc | 0.8862 |
| test_auc | 0.9346 |
| test_set_size | 624 |
| normal_recall | 0.7479 |
| pneumonia_recall | 0.9692 |
| epochs | 15 |
| fit_seconds | 19.7 |
| pos_weight_used | 0.3475 |

## 版本歷史

| 版本 | 狀態 | 登錄時間 | 登錄者 | SHA-256（前 12 碼） | 備註 |
|---|---|---|---|---|---|
| v1 | active | 2026-09-29T13:50:43 | system:bootstrap | `35755566c105` | 既有權重就地登錄為 v1 |

## 已知限制

僅供技術展示，非醫療診斷用途。normal 召回率僅約 74.8%，約每 4 張正常影像有 1 張被誤判為肺炎樣態。

## 不適用情境

任何臨床或診斷用途。
