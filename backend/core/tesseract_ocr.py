"""Tesseract OCR：Phase 4 改用 RapidOCR 當主要引擎後，保留這個當比較選項（mode=tesseract）。"""

import pytesseract
from PIL import Image


def extract_text(image: Image.Image) -> str:
    return pytesseract.image_to_string(image, lang="chi_tra+eng")
