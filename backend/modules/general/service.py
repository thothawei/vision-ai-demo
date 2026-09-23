"""M9 開放式辨識：現場照片（機台、工具、零件、標示、安全狀況）的開放式描述。"""

import time

from core import llm
from core.image_io import load_image
from core.inspection_log import record_result
from core.schemas import InspectionResult

MODULE = "general"

DESCRIBE_PROMPT = """你是製造業現場的影像辨識助手。仔細觀察這張照片，回答「這是什麼」。
照片可能是工廠現場、機台設備、手工具、零件（螺絲、齒輪、CNC 加工件等）、標示或銘牌。

請用繁體中文回覆，只回傳一個 JSON 物件，格式如下：

{
  "主要物件": "照片中最主要的東西是什麼（機台種類、工具名稱、零件名稱、品牌型號等）",
  "類別": "機台設備／工具／零件／標示文字／現場環境／其他 擇一",
  "詳細描述": "更完整的描述，包含外觀特徵、材質、用途推測",
  "可見文字": ["照片中看得到的文字，逐項列出；沒有就給空陣列"],
  "安全觀察": "現場安全相關的觀察（缺少防護、未戴安全帽、雜物堆放等）；看不出來就寫「無明顯異常」",
  "信心程度": "高／中／低，以及簡短說明為何"
}

只描述照片中實際看得到的東西，看不清楚的不要猜測具體型號。
"""


def describe_image(image_bytes: bytes) -> InspectionResult:
    started = time.perf_counter()
    image = load_image(image_bytes)
    result, engine = llm.generate_json(DESCRIBE_PROMPT, image)
    return record_result(MODULE, "INFO", [result], engine, started)
