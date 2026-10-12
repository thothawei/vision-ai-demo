"""跑 tests/real_samples/<action>/ 的真實照片評估集，更新 docs/evaluation.md。

    python scripts/evaluate.py --module gauge
    python scripts/evaluate.py --all

沒有照片的模組寫成「待補真實照片」，不會用合成圖冒充。評估用暫存資料庫，不會寫進真實檢驗紀錄。
"""

import argparse
import json
import os
import sys
import tempfile
import time
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SAMPLES_DIR = ROOT / "tests" / "real_samples"
DOC_PATH = ROOT / "docs" / "evaluation.md"
IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}
# 規劃書 23.1 列出的評估模組；M12 = shipping
MODULES = ["count", "measure", "seven_segment", "gauge", "assembly", "colordiff", "shipping"]
PENDING = "待補真實照片"
PENDING_NOTES = {
    "measure": "公開網路上找不到「ArUco 標記＋已知尺寸工件」的照片；拍攝與標註流程見 tests/real_samples/measure/README.md",
}
# 合成壓力測試（不是真實照片）：改動前後的數字，見 tests/test_measure_stress.py
STRESS = {
    "measure": [
        ("光照漸變（左暗右亮）", "130.1×128.0（錯）", "50.6×20.3"),
        ("灰色背景＋淺灰工件", "130.0×130.0（錯）", "50.6×20.3"),
        ("灰色背景＋亮工件", "130.1×130.1（錯）", "50.6×20.3"),
        ("大工件 150×40 mm（標記 30 mm）", "59.5×40.5（無聲截斷）", "150.3×40.2"),
        ("大工件 100×60 mm", "60.7×59.5（無聲截斷）", "100.2×60.2"),
        ("整張旋轉 15°", "52.5×20.8", "50.8×20.4"),
        ("基準（正視、白底）", "50.6×20.3", "50.2×20.2"),
        ("工件被畫面截掉一部分", "回報偏小的數字", "422 拒絕並說明"),
    ],
}
# 演算法改動前後的數字（改完重跑要保留前後，不覆蓋）
HISTORY = [
    (
        "2026-10-12",
        "seven_segment",
        "0/8",
        "5/8",
        "重寫判讀流程：兩種極性都試、分組（線段不相連）、覆蓋率判斷、較嚴格的門檻對付光暈。仍失敗的 3 張：計數器近拍"
        "（3 個暗淡數字標成 ?，整體判 NG 交人工，沒有讀錯）、兩張完整場景照（顯示器只占畫面一小塊，須近拍）。",
    ),
]


def _isolate_data(tmp: Path) -> None:
    os.environ["INSPECTION_DB"] = str(tmp / "inspections.db")
    os.environ["INSPECTION_IMAGES_DIR"] = str(tmp / "images")
    os.environ["GOLDEN_SAMPLES_DIR"] = str(tmp / "golden_samples")
    os.environ.setdefault("SESSION_SECRET", "evaluate-script-" + "x" * 32)
    sys.path.insert(0, str(ROOT / "backend"))


def _matches(actual, expected, tolerance: float) -> tuple[bool, float | None]:
    if isinstance(expected, (int, float)) and not isinstance(expected, bool):
        if not isinstance(actual, (int, float)):
            return False, None
        error = abs(actual - expected)
        return error <= tolerance, error
    return actual == expected, None


def evaluate_module(action: str) -> dict:
    """回傳 {status: 'pending'|'done', ...}；沒有標註或沒有照片就是 pending。"""
    folder = SAMPLES_DIR / action
    labels_path = folder / "labels.json"
    if not labels_path.is_file():
        return {"status": "pending", "reason": "沒有 labels.json"}
    labels = json.loads(labels_path.read_text(encoding="utf-8"))
    samples = [s for s in labels.get("samples", []) if (folder / s["file"]).suffix.lower() in IMAGE_EXTS]
    samples = [s for s in samples if (folder / s["file"]).is_file()]
    if not samples:
        return {"status": "pending", "reason": "labels.json 沒有可用的照片"}

    from core import registry

    spec = registry.get_action(action)
    if spec is None or spec.handler is None:
        raise SystemExit(f"找不到可執行的動作：{action}")
    rows, errors, times = [], [], []
    for s in samples:
        params = spec.params(**{**labels.get("params", {}), **s.get("params", {})}) if spec.params else None
        started = time.perf_counter()
        try:
            item = spec.handler((folder / s["file"]).read_bytes(), params).items[0]
        except Exception as e:  # noqa: BLE001 — 單張失敗要記錄，不能讓整批評估中斷
            refused = getattr(e, "status_code", None) == 422
            if s.get("expect_refusal"):
                rows.append(
                    (s["file"], refused, f"明確拒絕（設計內的行為）：{e}" if refused else f"預期要拒絕，但是：{e}")
                )
            else:
                rows.append((s["file"], False, f"執行失敗：{e}"))
            continue
        if s.get("expect_refusal"):
            rows.append((s["file"], False, "預期要拒絕（沒有可參考的背景），但回報了數字"))
            continue
        times.append(time.perf_counter() - started)
        ok_all, detail = True, []
        for key, expected in s["expected"].items():
            ok, error = _matches(item.get(key), expected, s.get("tolerance", 0))
            ok_all &= ok
            if error is not None:
                errors.append(error)
            detail.append(f"{key}: 預期 {expected}／實際 {item.get(key)}")
        rows.append((s["file"], ok_all, "；".join(detail)))
    passed = sum(1 for _, ok, _ in rows if ok)
    return {
        "status": "done",
        "device": labels.get("device", "未註明"),
        "total": len(rows),
        "passed": passed,
        "mean_abs_error": sum(errors) / len(errors) if errors else None,
        "mean_seconds": sum(times) / len(times) if times else None,
        "rows": rows,
    }


def render(results: dict[str, dict]) -> str:
    lines = [
        "# 真實照片評估結果",
        "",
        "由 `python scripts/evaluate.py --all` 產生。照片放在 `tests/real_samples/<動作>/`（格式見該目錄 README）。"
        "**表現差就照實寫**，不調整標註或門檻去配合數字。",
        "",
        f"更新日期：{date.today().isoformat()}",
        "",
        "| 模組 | 狀態 | 張數 | 正確 | 準確率 | 平均絕對誤差 | 平均耗時 | 拍攝裝置 |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for action in MODULES:
        r = results[action]
        if r["status"] == "pending":
            reason = PENDING_NOTES.get(action, r["reason"])
            lines.append(f"| {action} | {PENDING}（{reason}） | — | — | — | — | — | — |")
            continue
        err = f"{r['mean_abs_error']:.3f}" if r["mean_abs_error"] is not None else "—"
        sec = f"{r['mean_seconds']:.2f} 秒" if r["mean_seconds"] is not None else "—"
        lines.append(
            f"| {action} | 真實照片實測 | {r['total']} | {r['passed']} | {r['passed'] / r['total']:.0%} | {err} | {sec} | {r['device']} |"
        )
    lines += [
        "",
        "## 合成壓力測試（**不是真實照片**）",
        "",
        "沒有真實照片的模組，用合成場景加上真實拍攝常見的退化（透視、旋轉、噪點、模糊、JPEG、光照漸變、灰色背景、"
        "大工件）檢查會不會出大錯；這只能抓出明顯的缺陷，**不能代表真實照片的準確度**。",
        "",
        "### measure（尺寸量測，標記 30 mm，真值 50×20 mm／150×40 mm／100×60 mm）",
        "",
        "| 情境 | 改動前 長×寬 mm | 改動後 長×寬 mm |",
        "|---|---|---|",
    ]
    lines += [f"| {c} | {b} | {a} |" for c, b, a in STRESS["measure"]]
    lines += ["", "## 演算法改動紀錄", "", "| 日期 | 模組 | 改動前 | 改動後 | 說明 |", "|---|---|---|---|---|"]
    lines += [f"| {d} | {m} | {b} | {a} | {note} |" for d, m, b, a, note in HISTORY]
    for action in MODULES:
        r = results[action]
        if r["status"] == "done":
            lines += ["", f"## {action}", "", "| 照片 | 結果 | 明細 |", "|---|---|---|"]
            lines += [f"| {f} | {'通過' if ok else '未通過'} | {d} |" for f, ok, d in r["rows"]]
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--module", choices=MODULES)
    group.add_argument("--all", action="store_true")
    args = parser.parse_args()
    targets = MODULES if args.all else [args.module]

    with tempfile.TemporaryDirectory() as tmp:
        _isolate_data(Path(tmp))
        fresh = {m: evaluate_module(m) for m in targets}

    # 只重跑部分模組時，保留文件裡其他模組的既有結果有困難（文件是產生的）；--module 時其餘模組一併重跑
    results = fresh
    if not args.all:
        with tempfile.TemporaryDirectory() as tmp:
            _isolate_data(Path(tmp))
            results = {m: fresh.get(m) or evaluate_module(m) for m in MODULES}
    DOC_PATH.write_text(render(results), encoding="utf-8")
    for m in targets:
        r = results[m]
        print(f"{m}: {PENDING if r['status'] == 'pending' else str(r['passed']) + '/' + str(r['total'])}")
    print(f"已更新 {DOC_PATH.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
