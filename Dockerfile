# 製造業視覺品檢平台：多階段映像。權重（models/）與資料（data/）用 volume，不打包進映像。
# 基底只用官方免費映像 python:3.11-slim。

FROM python:3.11-slim AS builder
ENV PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
COPY backend/requirements.txt /tmp/requirements.txt
# torch 用 CPU 版輪子：預設的 PyPI 輪子在 x86_64 Linux 會帶 CUDA（數 GB），本產品固定 CPU 推論
RUN pip install --extra-index-url https://download.pytorch.org/whl/cpu -r /tmp/requirements.txt

FROM python:3.11-slim
ENV PATH="/opt/venv/bin:$PATH" PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
# tesseract：M4 的比較模式；libglib：opencv/zxing 執行期相依
RUN apt-get update \
    && apt-get install -y --no-install-recommends tesseract-ocr tesseract-ocr-chi-tra libglib2.0-0 libgl1 \
    && rm -rf /var/lib/apt/lists/*
COPY --from=builder /opt/venv /opt/venv

# 非 root 使用者；models/ 與 data/ 掛 volume，所以先建好目錄並交給該使用者
RUN useradd --create-home --uid 1000 app \
    && mkdir -p /app/models /app/data \
    && chown -R app:app /app
WORKDIR /app
COPY --chown=app:app backend ./backend
COPY --chown=app:app frontend ./frontend
COPY --chown=app:app scripts ./scripts
COPY --chown=app:app pyproject.toml pytest.ini README.md ./
USER app

VOLUME ["/app/models", "/app/data"]
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/healthz', timeout=4).status == 200 else 1)"
WORKDIR /app/backend
# 單一程序：同一個資料庫同一時間只允許一個服務程序（見 core/instance_lock.py），不要加 --workers
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
