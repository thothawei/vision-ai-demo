"""掃描全專案是否出現不該出現的定位用語（本專案是正式產品）。有命中就列出並以非 0 結束。"""

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# 禁用詞：描述系統定位時不可使用
BANNED = ["作品集", "面試", "應徵", "求職", "Demo 腳本", "展示用 demo"]
PATTERN = re.compile("|".join(re.escape(w) for w in BANNED), re.IGNORECASE)

# 排除：虛擬環境、資料、模型、規劃文件與本腳本自身
EXCLUDE_DIRS = {"venv", "data", "models", "runs", "node_modules", ".git", "__pycache__"}
EXCLUDE_FILES = {"docs/product-hardening-plan.md", "scripts/check_wording.py"}
EXCLUDE_SUFFIXES = {".png", ".jpg", ".jpeg", ".pdf", ".pt", ".onnx", ".db", ".gif", ".ico", ".zip"}


def tracked_files() -> list[Path]:
    # 用 git 列出「已追蹤＋未被忽略的新檔」，自動略過 .gitignore 內容
    out = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.splitlines()
    return [ROOT / p for p in out]


def main() -> int:
    hits = []
    for path in tracked_files():
        rel = path.relative_to(ROOT).as_posix()
        if not path.is_file() or rel in EXCLUDE_FILES or path.suffix.lower() in EXCLUDE_SUFFIXES:
            continue
        if EXCLUDE_DIRS & set(path.relative_to(ROOT).parts):
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        for no, line in enumerate(text.splitlines(), 1):
            if PATTERN.search(line):
                hits.append(f"{rel}:{no}: {line.strip()[:120]}")
    for h in hits:
        print(h)
    print(f"命中 {len(hits)} 筆")
    return 1 if hits else 0


if __name__ == "__main__":
    sys.exit(main())
