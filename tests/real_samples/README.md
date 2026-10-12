# 真實照片評估集

放「確認可公開」的真實照片（手機或相機拍攝），不可用合成圖冒充。每個模組一個資料夾，內含照片與 `labels.json`：

```
tests/real_samples/<action>/
├── labels.json
└── *.jpg
```

`<action>` 是註冊表的動作代號：`count`、`measure`、`seven_segment`、`gauge`、`assembly`、`colordiff`、`shipping`。

```json
{
  "params": {"min_value": 0, "max_value": 10},
  "device": "iPhone 15 手機相機",
  "samples": [
    {"file": "g1.jpg", "expected": {"讀值": 3.2}, "tolerance": 0.3},
    {"file": "g2.jpg", "expected": {"讀值": 7.5}, "tolerance": 0.3, "params": {"max_value": 10}}
  ]
}
```

- `expected`：與辨識結果第一個項目（`items[0]`）比對的欄位。數字用 `tolerance`（絕對誤差）判定，其餘用完全相等。
- `params`：套用到該模組的動作參數；單張的 `params` 覆蓋整體的。
- `device`：拍攝裝置，會寫進 `docs/evaluation.md`。

執行：`python scripts/evaluate.py --module gauge`（或 `--all`），結果更新 `docs/evaluation.md`。
照片與標註不進版控時請在這裡說明來源與授權。
