"""Phase 12：把已人工複判的檢驗紀錄匯出成可用標註工具校正的格式，供重訓用。

- M5 PPE／M6 PCB 瑕疵 → YOLO 格式（AI 當時的偵測框當預標註，需要人工校正框的位置/類別是否正確）
- M3 異常檢測 → MVTec 資料夾格式（good/、defect/，依人工複判結果分類）

校正標註用 Label Studio Community（Apache-2.0）或 CVAT（MIT）匯入/匯出，見 README「複判資料回流」章節，
兩者都不裝進本專案 venv（各自獨立安裝/執行，這支腳本只負責產生它們吃得懂的資料夾格式）。

用法：
    python scripts/export_reviewed.py --module ppe --out ./export_ppe
    python scripts/export_reviewed.py --module defect --out ./export_defect
    python scripts/export_reviewed.py --module anomaly --out ./export_anomaly [--category screw]
"""

import argparse
import json
import shutil
import sys
from pathlib import Path

from PIL import Image

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "backend"))

from core.inspection_log import query_inspections  # noqa: E402

# class id 順序要跟訓練時 data.yaml 的 names 順序一致（見 safety/service.py、defect/service.py）
PPE_CLASS_MAP = {"已戴安全帽": 0, "未戴安全帽": 1}
PPE_CLASS_NAMES = ["helmet", "head"]

DEFECT_CLASS_MAP = {
    "斷路 open": 0, "短路 short": 1, "缺口 mousebite": 2,
    "毛刺 spur": 3, "多餘銅箔 spurious copper": 4, "針孔 pin-hole": 5,
}
DEFECT_CLASS_NAMES = ["open", "short", "mousebite", "spur", "copper", "pin-hole"]


def _resolve_image_path(record: dict) -> Path | None:
    rel = record.get("image_path")
    if not rel:
        return None
    return PROJECT_ROOT / "data" / rel


def export_yolo(module: str, class_map: dict, class_names: list[str], out_dir: Path) -> dict:
    """AI 偵測框當預標註匯出，不是最終標註——匯出的 labels/*.txt 需要人工在標註工具裡校正
    框的位置與類別是否正確，才能拿去重訓，manifest.json 裡也會註明這件事。"""
    records = query_inspections(module=module, limit=100000)
    reviewed = [r for r in records if r.get("review_verdict")]

    images_dir = out_dir / "images"
    labels_dir = out_dir / "labels"
    images_dir.mkdir(parents=True, exist_ok=True)
    labels_dir.mkdir(parents=True, exist_ok=True)

    exported = 0
    skipped_no_image = 0
    for r in reviewed:
        img_path = _resolve_image_path(r)
        if img_path is None or not img_path.exists():
            skipped_no_image += 1
            continue
        with Image.open(img_path) as im:
            w, h = im.size
        stem = str(r["id"])
        shutil.copy(img_path, images_dir / f"{stem}{img_path.suffix}")

        lines = []
        for item in r["summary"]:
            for d in item.get("明細", []):
                label = d.get("類型") or d.get("瑕疵類型")
                if label not in class_map or "邊界框" not in d:
                    continue
                x1, y1, x2, y2 = d["邊界框"]
                cx, cy = (x1 + x2) / 2 / w, (y1 + y2) / 2 / h
                bw, bh = (x2 - x1) / w, (y2 - y1) / h
                lines.append(f"{class_map[label]} {cx:.6f} {cy:.6f} {bw:.6f} {bh:.6f}")
        (labels_dir / f"{stem}.txt").write_text("\n".join(lines))
        exported += 1

    (out_dir / "data.yaml").write_text(
        f"path: {out_dir.resolve()}\ntrain: images\nval: images\nnames:\n"
        + "\n".join(f"  {i}: {n}" for i, n in enumerate(class_names))
        + "\n"
    )
    manifest = {
        "module": module, "exported": exported, "skipped_no_image": skipped_no_image,
        "note": "AI 偵測框當預標註，框的位置/類別需要人工校正過才能拿去重訓，"
                "不是可以直接信任的最終標註。用 Label Studio Community 或 CVAT 匯入這個 YOLO 資料夾校正（見 README）。",
    }
    (out_dir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2))
    print(f"[{module}] 匯出 {exported} 張（{skipped_no_image} 張缺原圖跳過）到 {out_dir}")
    return manifest


def export_anomaly_mvtec(category: str | None, out_dir: Path) -> dict:
    records = query_inspections(module="anomaly", limit=100000)
    reviewed = [r for r in records if r.get("review_verdict")]
    if category:
        reviewed = [r for r in reviewed if any(item.get("類別") == category for item in r["summary"])]

    good_dir, defect_dir = out_dir / "good", out_dir / "defect"
    good_dir.mkdir(parents=True, exist_ok=True)
    defect_dir.mkdir(parents=True, exist_ok=True)

    counts = {"good": 0, "defect": 0, "skipped_no_image": 0}
    for r in reviewed:
        img_path = _resolve_image_path(r)
        if img_path is None or not img_path.exists():
            counts["skipped_no_image"] += 1
            continue
        is_good = r["review_verdict"] == "OK"
        target_dir = good_dir if is_good else defect_dir
        shutil.copy(img_path, target_dir / f"{r['id']}{img_path.suffix}")
        counts["good" if is_good else "defect"] += 1

    manifest = {"category": category, **counts}
    (out_dir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2))
    print(f"[anomaly] good={counts['good']} defect={counts['defect']}（{counts['skipped_no_image']} 張缺原圖跳過）到 {out_dir}")
    return manifest


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--module", required=True, choices=["ppe", "defect", "anomaly"])
    parser.add_argument("--out", required=True)
    parser.add_argument("--category", help="只匯出 anomaly 這個 category（選用）")
    args = parser.parse_args()

    out_path = Path(args.out)
    if args.module == "ppe":
        export_yolo("ppe", PPE_CLASS_MAP, PPE_CLASS_NAMES, out_path)
    elif args.module == "defect":
        export_yolo("defect", DEFECT_CLASS_MAP, DEFECT_CLASS_NAMES, out_path)
    else:
        export_anomaly_mvtec(args.category, out_path)
