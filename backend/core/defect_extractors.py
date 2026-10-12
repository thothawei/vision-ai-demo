"""NG 原因柏拉圖用：各模組怎麼從 summary（record_result 存進去的 items）抽出缺陷標籤。

抽取在查詢時才執行（`inspection_log.get_stats`），所以規則補上後歷史紀錄也會一起反映
（前提是舊紀錄的 summary 內含足夠資訊）。掛在 `core/registry.py` 的 ActionSpec 上。"""


def _details(summary):
    for item in summary:
        yield from item.get("明細", [])


def defect_pcb(summary):
    return [d["瑕疵類型"] for d in _details(summary) if "瑕疵類型" in d]


def defect_ppe(summary):
    return ["未戴安全帽" for d in _details(summary) if d.get("類型") == "未戴安全帽"]


def defect_anomaly(summary):
    return [f"外觀異常（{i.get('類別', '未知類別')}）" for i in summary if i.get("判定") == "異常"]


def defect_safety(summary):
    return ["危險區域入侵" for p in _details(summary) if p.get("是否入侵")]


def defect_packaging(summary):
    return [f"包裝不一致：{p}" for i in summary for p in i.get("問題") or []]


def defect_shipping(summary):
    return [f"出貨標籤不符：{p}" for i in summary for p in i.get("問題") or []]


def defect_assembly(summary):
    # SSIM 只能說「這個區域和黃金樣本不一樣」，分不出缺件或裝反，所以標籤不做臆測
    return [f"組裝異常：ROI {d.get('ROI編號')}" for d in _details(summary) if d.get("判定") == "NG"]


def defect_colordiff(summary):
    return ["色差超標" for i in summary if i.get("判定") == "不合格"]


def defect_codes(summary):
    return ["追溯碼已過期" for i in summary if i.get("效期狀態") == "已過期"]


def defect_measure(summary):
    labels = []
    for item in summary:
        expected = item.get("預期數量")
        if expected is not None and item.get("計數結果") != expected:
            labels.append("數量不符")
        for name in item.get("超差項目") or []:
            labels.append(f"尺寸超差：{name}")
    return labels


def _validation_labels(prefix, item):
    return [f"{prefix}：{e.get('欄位', '未知欄位')}" for e in item.get("_驗證錯誤") or []]


def defect_docs(summary):
    return [label for i in summary for label in _validation_labels("文件欄位驗證失敗", i)]


def defect_nameplate(summary):
    """銘牌（欄位驗證失敗）與七段顯示器（有無法判讀的字元）共用 module=nameplate。"""
    labels = []
    for item in summary:
        labels += _validation_labels("銘牌欄位驗證失敗", item)
        if "?" in str(item.get("讀值", "")):
            labels.append("七段顯示器判讀失敗")
    return labels
