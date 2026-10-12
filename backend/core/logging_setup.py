"""統一日誌格式（key=value，方便人工 grep）並在每行帶上 request_id。

不可記錄 API key 與圖片內容；呼叫端只傳識別碼、耗時、判定這類摘要。"""

import logging
import time
from contextlib import contextmanager

from core import request_scope


class RequestIdFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_scope.get_request_id() or "-"
        return True


class KeyValueFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        message = record.getMessage().replace('"', "'")
        line = (
            f"ts={self.formatTime(record, '%Y-%m-%dT%H:%M:%S')} level={record.levelname} "
            f'logger={record.name} request_id={record.request_id} msg="{message}"'
        )
        if record.exc_info:
            line += "\n" + self.formatException(record.exc_info)
        return line


def setup_logging(level: str = "INFO") -> None:
    root = logging.getLogger()
    root.setLevel(level.upper())
    for handler in root.handlers:
        if getattr(handler, "_vision_handler", False):
            return  # 已設定過（uvicorn --reload 或測試重複匯入）
    handler = logging.StreamHandler()
    handler.setFormatter(KeyValueFormatter())
    handler.addFilter(RequestIdFilter())
    handler._vision_handler = True
    root.addHandler(handler)


@contextmanager
def log_model_load(name: str):
    """記錄模型載入耗時（首次呼叫才載入，這是使用者感受到第一次很慢的原因）。"""
    logger = logging.getLogger("vision.model")
    started = time.perf_counter()
    logger.info("模型載入開始 model=%s", name)
    try:
        yield
    except Exception:
        logger.exception("模型載入失敗 model=%s", name)
        raise
    logger.info("模型載入完成 model=%s elapsed_ms=%s", name, int((time.perf_counter() - started) * 1000))
