"""由模型登錄表產生模型說明卡 `docs/model-cards/<模型 id>.md`（用途、資料集與授權、指標、版本歷史、已知限制、
不適用情境）。內容來自登錄表、登錄時讀入的 metrics.json，以及 `core/model_catalog.py` 的靜態說明；
沒有出處的數字不會出現。

用法：
    python scripts/gen_model_cards.py            # 寫到 docs/model-cards/
    python scripts/gen_model_cards.py --check    # 只檢查說明卡是否為最新
"""

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))

from core import model_catalog, model_registry  # noqa: E402

CARDS_DIR = ROOT / "docs" / "model-cards"
_SKIP_KEYS = {"weights_path"}  # metrics.json 裡的路徑是訓練當時的本機路徑，不放進說明卡


def _metric_rows(metrics: dict) -> list[str]:
    rows = []
    for key, value in metrics.items():
        if key in _SKIP_KEYS:
            continue
        rows.append(f"| {key} | {value} |")
    return rows


def render_card(model: dict) -> str:
    info = model_catalog.describe(model["model_id"])
    versions = model["versions"]
    active = next((v for v in versions if v["status"] == "active"), None)
    lines = [
        f"# {info['title']}（`{model['model_id']}`）", "",
        "> 本檔由 `scripts/gen_model_cards.py` 依模型登錄表產生，請勿手改；模型或版本異動後重新產生。", "",
        "## 用途", "", info["task"] or "（尚無說明）", "",
        "## 目前啟用版本", "",
    ]
    if active:
        lines += [f"- 版本：v{active['version']}（登錄於 {active['created_at']}，登錄者 {active['registered_by']}）",
                  f"- SHA-256：`{active['sha256']}`", f"- 大小：{active['size_bytes']:,} bytes", f"- 備註：{active['note'] or '—'}", ""]
    else:
        lines += ["沒有啟用中的版本。", ""]
    lines += ["## 資料集與授權", "", f"- 資料集：{info['dataset'] or '—'}", f"- 授權：{info['dataset_license'] or '—'}", "",
              "## 指標（啟用版本）", ""]
    rows = _metric_rows(active["metrics"]) if active else []
    lines += (["| 指標 | 數值 |", "|---|---|", *rows] if rows else ["尚無機器可讀的指標紀錄。"]) + [""]
    lines += ["## 版本歷史", "", "| 版本 | 狀態 | 登錄時間 | 登錄者 | SHA-256（前 12 碼） | 備註 |", "|---|---|---|---|---|---|"]
    lines += [f"| v{v['version']} | {v['status']} | {v['created_at']} | {v['registered_by']} | `{v['sha256'][:12]}` | {v['note'] or '—'} |"
              for v in versions]
    lines += ["", "## 已知限制", "", info["limitations"] or "—", "", "## 不適用情境", "", info["not_for"] or "—", ""]
    return "\n".join(lines)


def render_index(models: list[dict]) -> str:
    lines = ["# 模型說明卡", "", "由 `scripts/gen_model_cards.py` 產生。", "", "| 模型 | 啟用版本 | 說明卡 |", "|---|---|---|"]
    lines += [f"| {m['title']} | v{m['active_version']} | [{m['model_id']}.md]({m['model_id']}.md) |" for m in models]
    return "\n".join(lines) + "\n"


def generate(out_dir: Path = CARDS_DIR, check: bool = False) -> list[Path]:
    models = model_registry.list_models()
    expected = {f"{m['model_id']}.md": render_card(m) for m in models}
    expected["README.md"] = render_index(models)
    stale = [n for n, text in expected.items() if not (out_dir / n).exists() or (out_dir / n).read_text(encoding="utf-8") != text]
    if check:
        return [out_dir / n for n in stale]
    out_dir.mkdir(parents=True, exist_ok=True)
    for name, text in expected.items():
        (out_dir / name).write_text(text, encoding="utf-8")
    return [out_dir / n for n in expected]


def main() -> None:
    parser = argparse.ArgumentParser(description="產生模型說明卡")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    paths = generate(check=args.check)
    if args.check:
        if paths:
            sys.exit("說明卡已過期：" + "、".join(p.name for p in paths) + "；請執行 python scripts/gen_model_cards.py")
        print("說明卡為最新")
        return
    for p in paths:
        print(f"已產生 {p.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
