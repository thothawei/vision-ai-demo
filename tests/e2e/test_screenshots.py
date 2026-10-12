"""端到端：用 Playwright 跑過每個分頁並截圖到 docs/screenshots/（`scripts/capture_screenshots.py`）。

預設不跑（本機手動執行）：先啟動服務並建立帳號，再
    CAPTURE_USERNAME=... CAPTURE_PASSWORD=... [BASE_URL=http://127.0.0.1:8000] pytest -m e2e
"""

import os
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.e2e

SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"


def test_capture_every_tab_without_errors():
    pytest.importorskip("playwright.sync_api")
    if not (os.environ.get("CAPTURE_USERNAME") and os.environ.get("CAPTURE_PASSWORD")):
        pytest.skip("需要 CAPTURE_USERNAME／CAPTURE_PASSWORD 與已啟動的服務")
    sys.path.insert(0, str(SCRIPTS))
    import capture_screenshots

    capture_screenshots.main()
