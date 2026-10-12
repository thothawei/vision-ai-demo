"""登錄模型新版本、列出登錄表、切換啟用版本（伺服器端操作；權重不透過網頁上傳，因為異常檢測的權重是 pickle 檔）。

用法：
    python scripts/register_model.py list
    python scripts/register_model.py register --model-id pcb-defect --weights runs/.../best.pt \\
        --metrics-json metrics.json --note "加入 2026-10 產線照片重訓" --activate
    python scripts/register_model.py register --model-id anomaly-screw --weights <root>/weights/torch/model.pt --activate
    python scripts/register_model.py activate --model-id pcb-defect --version 1

規則：權重會被複製進 `models/registry/<模型 id>/v<N>/`（不可覆寫）；`--adopt` 則就地登錄、不複製
（只適合已在穩定位置的既有權重）。異常檢測（`anomaly-*`）要指向 `<root>/weights/torch/model.pt`，
會連同同一個 root 底下的門檻、評分、指標檔整個複製。
"""

import argparse
import json
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from core import audit, model_registry  # noqa: E402

ACTOR = "script:register_model"


def register(
    model_id: str,
    weights: Path,
    metrics: dict | None = None,
    note: str = "",
    activate: bool = False,
    adopt: bool = False,
) -> dict:
    weights = Path(weights).resolve()
    if not weights.is_file():
        raise ValueError(f"找不到權重檔：{weights}")
    if adopt:
        entry = model_registry.register_version(model_id, weights, metrics, note or "就地登錄", ACTOR, activate=False)
    else:
        version, target_dir = model_registry.new_version_dir(model_id)
        try:
            if model_id.startswith("anomaly-"):
                if len(weights.parents) < 3 or weights.name != "model.pt" or weights.parent.name != "torch":
                    raise ValueError("異常檢測要指向 <root>/weights/torch/model.pt")
                root = weights.parents[2]
                shutil.copytree(root, target_dir, dirs_exist_ok=True, ignore=shutil.ignore_patterns("_engine_logs"))
                copied = target_dir / "weights" / "torch" / "model.pt"
            else:
                copied = target_dir / weights.name
                shutil.copy2(weights, copied)
            entry = model_registry.register_version(
                model_id, copied, metrics, note, ACTOR, activate=False, version=version
            )
        except Exception:
            shutil.rmtree(target_dir, ignore_errors=True)
            raise
    audit.record(
        ACTOR, "model.register", "model", model_id, after={"version": entry["version"], "sha256": entry["sha256"][:12]}
    )
    if activate:
        activate_version(model_id, entry["version"])
        entry = model_registry.get_version(model_id, entry["version"])
    return entry


def activate_version(model_id: str, version: int) -> dict:
    target = model_registry.get_version(model_id, version)
    if target is None:
        raise ValueError(f"找不到模型 {model_id} 的版本 v{version}")
    path = Path(target["weights_abs"])
    if not path.is_file() or model_registry.sha256_file(path) != target["sha256"]:
        raise ValueError(f"v{version} 的權重檔不存在或 SHA-256 與登錄不符，不能啟用")
    previous, current = model_registry.activate_version(model_id, version)
    audit.record(
        ACTOR,
        "model.activate",
        "model",
        model_id,
        before={"version": previous["version"] if previous else None},
        after={"version": version},
    )
    return current


def main() -> None:
    parser = argparse.ArgumentParser(description="模型登錄")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("list", help="列出登錄表")
    reg = sub.add_parser("register", help="登錄新版本")
    reg.add_argument("--model-id", required=True)
    reg.add_argument("--weights", required=True, type=Path)
    reg.add_argument("--metrics-json", type=Path, help="指標 JSON 檔（例如訓練腳本輸出的 metrics.json）")
    reg.add_argument("--note", default="")
    reg.add_argument("--activate", action="store_true", help="登錄後立即啟用")
    reg.add_argument("--adopt", action="store_true", help="就地登錄、不複製權重")
    act = sub.add_parser("activate", help="切換啟用版本")
    act.add_argument("--model-id", required=True)
    act.add_argument("--version", required=True, type=int)
    args = parser.parse_args()
    try:
        if args.command == "list":
            for m in model_registry.list_models():
                print(f"{m['model_id']}（{m['title']}）啟用 v{m['active_version']}")
                for v in m["versions"]:
                    print(
                        f"  v{v['version']} {v['status']:8} {v['sha256'][:12]} {v['size_bytes']:>11,}B {v['weights_path']}"
                    )
        elif args.command == "register":
            metrics = json.loads(args.metrics_json.read_text(encoding="utf-8")) if args.metrics_json else None
            e = register(args.model_id, args.weights, metrics, args.note, args.activate, args.adopt)
            print(f"已登錄 {e['model_id']} v{e['version']}（{e['status']}）sha256={e['sha256'][:12]}…")
        else:
            e = activate_version(args.model_id, args.version)
            print(f"已啟用 {e['model_id']} v{e['version']}")
    except (ValueError, LookupError) as e:
        sys.exit(f"失敗：{e}")


if __name__ == "__main__":
    main()
