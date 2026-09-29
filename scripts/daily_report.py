"""產生品質日報／週報（Excel 與可列印 HTML），直接讀資料庫，不需要伺服器在執行。

用法：
    python scripts/daily_report.py                       # 昨天的日報 → reports/
    python scripts/daily_report.py --period week --date 2026-09-29 --out /path/to/dir

排程：本專案不內建排程器，請用作業系統的排程（macOS launchd、Windows 工作排程器），
範例見 docs/admin-guide.md。輸出資料夾 `reports/` 已加入 .gitignore。
"""

import argparse
import sys
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))

from core import reports  # noqa: E402


def generate(period: str, day: date, out_dir: Path) -> list[Path]:
    report = reports.build_report(period, day)
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = f"report-{period}-{report['date_from']}"
    xlsx, page = out_dir / f"{stem}.xlsx", out_dir / f"{stem}.html"
    xlsx.write_bytes(reports.to_xlsx(report))
    page.write_text(reports.to_html(report), encoding="utf-8")
    return [xlsx, page]


def main() -> None:
    parser = argparse.ArgumentParser(description="產生品質日報／週報")
    parser.add_argument("--period", choices=["day", "week"], default="day")
    parser.add_argument("--date", type=date.fromisoformat, default=date.today() - timedelta(days=1),
                        help="基準日 YYYY-MM-DD（預設昨天；週報是包含該日的那一週，週一到週日）")
    parser.add_argument("--out", type=Path, default=ROOT / "reports")
    args = parser.parse_args()
    for path in generate(args.period, args.date, args.out):
        print(f"已產生 {path}")


if __name__ == "__main__":
    main()
