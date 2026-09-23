"""把 DeepPCB 原始標註（x1,y1,x2,y2,type）轉成 YOLO 格式，供 M6 訓練用。

DeepPCB 官方只說明「1000 張當訓練集、其餘當測試集」，沒有附官方切分清單
（查證來源：https://github.com/tangsanli5201/DeepPCB README，2026-09-23），
所以這裡自己切（固定亂數種子，可重現），誠實記錄不是官方切分。

用法：
    python scripts/prepare_deeppcb.py
    → 輸出到 data/deeppcb_yolo/{train,val,test}/{images,labels} + data.yaml
"""

import random
import shutil
from pathlib import Path

from PIL import Image

PROJECT_ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = PROJECT_ROOT / "data" / "deeppcb" / "PCBData"
OUT_DIR = PROJECT_ROOT / "data" / "deeppcb_yolo"

# DeepPCB 官方類別編號（見 README）：1-open 2-short 3-mousebite 4-spur 5-copper 6-pin-hole
CLASS_NAMES = ["open", "short", "mousebite", "spur", "copper", "pin-hole"]

SPLIT_SEED = 42
N_TRAIN, N_VAL = 1000, 250  # 剩下的當 test；官方只給數量沒給清單，這是我們自己的切法


def find_pairs() -> list[tuple[Path, Path]]:
    pairs = []
    for test_img in sorted(RAW_DIR.glob("group*/**/*_test.jpg")):
        stem = test_img.stem.removesuffix("_test")
        # 標註檔在同一 group 底下的 <group>_not/ 資料夾
        group_dir = test_img.parent.parent  # .../group12000
        ann_path = group_dir / f"{group_dir.name.removeprefix('group')}_not" / f"{stem}.txt"
        if ann_path.exists():
            pairs.append((test_img, ann_path))
    return pairs


def convert_annotation(ann_path: Path, img_w: int, img_h: int) -> list[str]:
    lines = []
    for raw_line in ann_path.read_text().strip().splitlines():
        if not raw_line.strip():
            continue
        x1, y1, x2, y2, cls_id = (int(v) for v in raw_line.split())
        cls_idx = cls_id - 1  # 官方 1-indexed，YOLO 要 0-indexed
        cx = (x1 + x2) / 2 / img_w
        cy = (y1 + y2) / 2 / img_h
        w = abs(x2 - x1) / img_w
        h = abs(y2 - y1) / img_h
        lines.append(f"{cls_idx} {cx:.6f} {cy:.6f} {w:.6f} {h:.6f}")
    return lines


def main():
    pairs = find_pairs()
    print(f"找到 {len(pairs)} 對圖片+標註")
    if len(pairs) < N_TRAIN + N_VAL:
        raise RuntimeError(f"資料只有 {len(pairs)} 張，不夠切 {N_TRAIN} train + {N_VAL} val")

    rng = random.Random(SPLIT_SEED)
    rng.shuffle(pairs)
    splits = {
        "train": pairs[:N_TRAIN],
        "val": pairs[N_TRAIN:N_TRAIN + N_VAL],
        "test": pairs[N_TRAIN + N_VAL:],
    }

    if OUT_DIR.exists():
        shutil.rmtree(OUT_DIR)

    for split_name, split_pairs in splits.items():
        img_dir = OUT_DIR / split_name / "images"
        label_dir = OUT_DIR / split_name / "labels"
        img_dir.mkdir(parents=True, exist_ok=True)
        label_dir.mkdir(parents=True, exist_ok=True)

        for img_path, ann_path in split_pairs:
            with Image.open(img_path) as im:
                w, h = im.size
            new_name = f"{img_path.parent.parent.name}_{img_path.stem}"
            shutil.copy(img_path, img_dir / f"{new_name}.jpg")
            (label_dir / f"{new_name}.txt").write_text("\n".join(convert_annotation(ann_path, w, h)))

        print(f"{split_name}: {len(split_pairs)} 張")

    yaml_content = f"""# 由 scripts/prepare_deeppcb.py 產生
path: {OUT_DIR}
train: train/images
val: val/images
test: test/images
names:
{chr(10).join(f"  {i}: {name}" for i, name in enumerate(CLASS_NAMES))}
"""
    (OUT_DIR / "data.yaml").write_text(yaml_content)
    print(f"已寫入 {OUT_DIR / 'data.yaml'}")


if __name__ == "__main__":
    main()
