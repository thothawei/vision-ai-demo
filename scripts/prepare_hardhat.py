"""把 Hard Hat Workers 資料集（Pascal VOC XML）轉成 YOLO 格式，供 M5 PPE 訓練用。

資料集：CC0 1.0，https://doi.org/10.7910/DVN/7CBGOS（查證紀錄見 docs/licenses.md）。
只有 helmet／head 兩類（沒有反光背心），這是這個資料集的限制，不是我們漏做。
"""

import shutil
import xml.etree.ElementTree as ET
from pathlib import Path

from PIL import Image

PROJECT_ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = PROJECT_ROOT / "data" / "hardhat" / "Hardhat"
OUT_DIR = PROJECT_ROOT / "data" / "hardhat_yolo"

CLASS_NAMES = ["helmet", "head"]  # 忽略資料集裡極少數的 person/others 類別


def convert_split(split_name: str, raw_split_dir: str):
    ann_dir = RAW_DIR / raw_split_dir / "Annotation"
    img_dir = RAW_DIR / raw_split_dir / "JPEGImage"
    out_img_dir = OUT_DIR / split_name / "images"
    out_label_dir = OUT_DIR / split_name / "labels"
    out_img_dir.mkdir(parents=True, exist_ok=True)
    out_label_dir.mkdir(parents=True, exist_ok=True)

    n_images, n_boxes, n_skipped_classes = 0, 0, 0
    for xml_path in sorted(ann_dir.glob("*.xml")):
        root = ET.parse(xml_path).getroot()
        filename = root.findtext("filename")
        img_path = img_dir / filename
        if not img_path.exists():
            continue

        size = root.find("size")
        img_w, img_h = int(size.findtext("width")), int(size.findtext("height"))
        if img_w <= 0 or img_h <= 0:
            with Image.open(img_path) as im:
                img_w, img_h = im.size

        lines = []
        for obj in root.findall("object"):
            name = obj.findtext("name")
            if name not in CLASS_NAMES:
                n_skipped_classes += 1
                continue
            box = obj.find("bndbox")
            x1, y1 = float(box.findtext("xmin")), float(box.findtext("ymin"))
            x2, y2 = float(box.findtext("xmax")), float(box.findtext("ymax"))
            cls_idx = CLASS_NAMES.index(name)
            cx, cy = (x1 + x2) / 2 / img_w, (y1 + y2) / 2 / img_h
            w, h = (x2 - x1) / img_w, (y2 - y1) / img_h
            lines.append(f"{cls_idx} {cx:.6f} {cy:.6f} {w:.6f} {h:.6f}")
            n_boxes += 1

        if not lines:
            continue  # 這張圖沒有 helmet/head 標註，跳過

        shutil.copy(img_path, out_img_dir / filename)
        (out_label_dir / f"{xml_path.stem}.txt").write_text("\n".join(lines))
        n_images += 1

    print(f"{split_name}: {n_images} 張圖、{n_boxes} 個標註框（跳過 {n_skipped_classes} 個非 helmet/head 的框）")


def main():
    if OUT_DIR.exists():
        shutil.rmtree(OUT_DIR)

    # 沿用資料集自帶的 Train/Test 切分（不是我們自己亂切的）
    convert_split("train", "Train")
    convert_split("val", "Test")  # 官方只有 Train/Test，沒有另外的 val，這裡把 Test 當 val 用

    yaml_content = f"""# 由 scripts/prepare_hardhat.py 產生
path: {OUT_DIR}
train: train/images
val: val/images
names:
{chr(10).join(f"  {i}: {name}" for i, name in enumerate(CLASS_NAMES))}
"""
    (OUT_DIR / "data.yaml").write_text(yaml_content)
    print(f"已寫入 {OUT_DIR / 'data.yaml'}")


if __name__ == "__main__":
    main()
