"""由 backend/core/settings.py 產生 docs/admin-guide.md 的設定表，避免文件與程式不一致。

用法：
    python scripts/gen_settings_doc.py          # 更新 admin-guide.md 內標記之間的表格
    python scripts/gen_settings_doc.py --check  # 只檢查是否最新（不是最新就以非 0 結束）
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))

from core.settings import Settings  # noqa: E402

DOC = ROOT / "docs" / "admin-guide.md"
BEGIN = "<!-- settings-table:begin -->"
END = "<!-- settings-table:end -->"


def render_table() -> str:
    rows = ["| 變數 | 預設 | 用途 | 生效 |", "|---|---|---|---|"]
    for name, field in Settings.model_fields.items():
        default = "無" if field.default is None else ("空" if field.default == "" else f"`{field.default}`")
        apply = "**需重啟**" if (field.json_schema_extra or {}).get("apply") == "restart" else "即時"
        rows.append(f"| `{name.upper()}` | {default} | {field.description} | {apply} |")
    return "\n".join(rows)


def render_section() -> str:
    return f"{BEGIN}\n{render_table()}\n{END}"


def updated_doc(text: str) -> str:
    start, end = text.index(BEGIN), text.index(END) + len(END)
    return text[:start] + render_section() + text[end:]


def main() -> int:
    text = DOC.read_text(encoding="utf-8")
    new = updated_doc(text)
    if "--check" in sys.argv:
        if new != text:
            print("docs/admin-guide.md 的設定表已過期，請執行 python scripts/gen_settings_doc.py")
            return 1
        print("設定表為最新")
        return 0
    DOC.write_text(new, encoding="utf-8")
    print("已更新設定表")
    return 0


if __name__ == "__main__":
    sys.exit(main())
