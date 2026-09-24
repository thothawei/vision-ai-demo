"""Phase 8 收尾：用 Playwright 自動跑過每個分頁，實際上傳測試圖、點擊、等結果，截圖存到 docs/screenshots/。

這是一次性文件用腳本（不進 requirements.txt，只在 venv 額外裝 playwright）：
    python scripts/capture_screenshots.py
"""

import time
from pathlib import Path

from playwright.sync_api import sync_playwright

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SAMPLES = PROJECT_ROOT / "tests" / "samples"
OUT_DIR = PROJECT_ROOT / "docs" / "screenshots"
BASE_URL = "http://127.0.0.1:8000"

# (tab_index_1based, 截圖檔名, 檔案input選擇器, 上傳的圖, 按鈕文字, 等待秒數, 上傳前的額外設定)
STEPS = [
    (1, "01_general.png", "#general-file", "warning_sign.png", "#general-btn", 25, None),
    (2, "02_docs.png", "#docs-file", "shipping_order.png", "#docs-btn", 25, None),
    (3, "03_anomaly.png", "#anomaly-file", None, "#anomaly-btn", 15, "anomaly"),
    (4, "04_codes.png", "#codes-file", "gs1_valid.png", "#codes-btn", 5, None),
    (5, "05_measure.png", "#measure-file", "measure_scene.png", "#measure-btn", 5, "measure"),
    (6, None, "#safety-file", None, None, 3, "safety"),  # 特殊流程，見下方 capture_safety
    (7, "07_ppe.png", "#ppe-file", None, "#ppe-btn", 5, "ppe"),
    (8, "08_defect.png", "#defect-file", None, "#defect-btn", 5, "defect"),
    (9, "09_nameplate.png", "#nameplate-file", "nameplate.png", "#nameplate-btn", 15, None),
    (10, "10_sevenseg.png", "#sevenseg-file", "seven_segment.png", "#sevenseg-btn", 5, None),
    (11, "11_gauge.png", "#gauge-file", "gauge.png", "#gauge-btn", 5, None),
    (12, "12_packaging.png", "#packaging-file", "packaging_mismatch.png", "#packaging-btn", 15, None),
    (13, "13_pneumonia.png", "#pneumonia-file", "pneumonia_sample.png", "#pneumonia-btn", 5, None),
]


def click_tab(page, n: int):
    page.locator(".tab-btn").nth(n - 1).click()
    page.wait_for_timeout(300)


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1280, "height": 900})
        page.goto(BASE_URL, wait_until="networkidle")
        page.wait_for_timeout(500)

        for tab_index, filename, file_selector, image_name, btn_selector, wait_s, special in STEPS:
            click_tab(page, tab_index)

            if special == "measure":
                # M2 有兩張卡片：計數 + 量測，用第二個 file input（量測）
                file_selector = "#measure-file"
            if special == "safety":
                capture_safety(page)
                continue

            # M3/M7-PPE/M6 用真實資料集圖片（不是隨便塞無關圖），screenshot 才有意義
            if special == "anomaly":
                img_path = PROJECT_ROOT / "data" / "mvtec_ad" / "screw" / "test" / "scratch_head" / "000.png"
            elif special == "ppe":
                img_path = PROJECT_ROOT / "data" / "hardhat_yolo" / "val" / "images" / "005298.jpg"
            elif special == "defect":
                img_path = PROJECT_ROOT / "data" / "deeppcb_yolo" / "test" / "images" / "group00041_00041001_test.jpg"
            else:
                img_path = SAMPLES / image_name

            page.set_input_files(file_selector, str(img_path))
            page.wait_for_timeout(300)
            if special == "anomaly":
                page.select_option("#anomaly-category", "screw")

            page.locator(btn_selector).click()
            page.wait_for_timeout(wait_s * 1000)

            out_path = OUT_DIR / filename
            page.screenshot(path=str(out_path), full_page=True)
            print(f"[{tab_index}] 已存 {out_path.relative_to(PROJECT_ROOT)}")

        browser.close()


def capture_safety(page):
    """M5 危險區域入侵：canvas 要先點幾個點畫多邊形，再按開始偵測。用真人照片示範。"""
    live_sample = PROJECT_ROOT / "tests" / "live_samples" / "factory_worker.jpg"
    if not live_sample.exists():
        print("[6] 跳過（tests/live_samples/factory_worker.jpg 不存在，見 tests/live_samples/README.md）")
        return

    page.set_input_files("#safety-file", str(live_sample))
    canvas = page.locator("#safety-canvas")
    canvas.wait_for(state="visible", timeout=10000)
    # canvas 的實際寬高要等圖片 onload 後才會設定，用輪詢確認尺寸穩定再讀 bounding_box
    page.wait_for_function(
        "document.querySelector('#safety-canvas').width > 0", timeout=10000
    )
    page.wait_for_timeout(500)
    box = canvas.bounding_box()
    if not box:
        print("[6] 跳過（canvas 沒有顯示）")
        return

    # 用 locator.click(position=...) 而不是 page.mouse.click(絕對座標)：
    # canvas 比 viewport 高，絕對座標點擊下半部會落在畫面捲動範圍外點不到；
    # position 是相對 canvas 左上角，click() 每次都會自動把 canvas 捲進可視範圍再點。
    # y 下緣要到 1.0（畫布底部）：人員的「腳底參考點」在原圖裡非常接近下緣（fraction≈0.989），
    # 之前用 0.98 只差一點點就沒蓋到，畫出來像是涵蓋人物，但 pointPolygonTest 其實判定沒入侵。
    w, h = box["width"], box["height"]
    points = [(w * 0.03, h * 0.05), (w * 0.45, h * 0.05),
              (w * 0.45, h * 0.995), (w * 0.03, h * 0.995)]
    for x, y in points:
        canvas.click(position={"x": x, "y": y})
        page.wait_for_timeout(150)

    page.locator("#safety-zone-done-btn").click()
    page.wait_for_timeout(300)
    page.locator("#safety-btn").click()
    page.wait_for_timeout(6000)

    out_path = OUT_DIR / "06_safety.png"
    page.screenshot(path=str(out_path), full_page=True)
    print(f"[6] 已存 {out_path.relative_to(PROJECT_ROOT)}")


if __name__ == "__main__":
    main()
