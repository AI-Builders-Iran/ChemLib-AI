"""The OCR choice shown next to every upload (admin and user): online or local."""

from __future__ import annotations

import os

import streamlit as st

ONLINE_FIRST = "online_first"
LOCAL_ONLY = "local_only"

LABELS = {
    ONLINE_FIRST: "آنلاین، و اگر نشد محلی",
    LOCAL_ONLY: "فقط محلی (بدون ارسال به اینترنت)",
}

HELP = (
    "فقط صفحه‌های اسکن‌شده OCR می‌شوند؛ صفحه‌هایی که خودشان متن دارند اصلاً OCR نمی‌شوند. "
    "صفحه‌هایی که عمدتاً شکل، نمودار یا ساختار شیمیایی پیچیده‌اند (و جدول ندارند) از OCR رد می‌شوند. "
    "آنلاین: تصویر صفحه به سرویس ابری (Azure یا OpenRouter) فرستاده می‌شود و اگر خطا داد، OCR محلی جایگزین می‌شود. "
    "فقط محلی: تصویر صفحه‌ها از این رایانه بیرون نمی‌رود. "
    "OCR محلی سبک است و برای متن انگلیسی ساخته شده؛ برای PDF فارسی اسکن‌شده از حالت آنلاین استفاده کنید. "
    "توجه: پاسخ‌گویی به سؤال‌ها در هر دو حالت همچنان از مدل زبانی (OpenRouter) انجام می‌شود."
)


def default_mode() -> str:
    return LOCAL_ONLY if os.getenv("OCR_MODE") == LOCAL_ONLY else ONLINE_FIRST


def local_engine_ready() -> bool:
    from src.ocr import engine_status

    return any(ready for name, ready, _ in engine_status() if name in ("rapidocr", "paddle"))


def render(key: str) -> str:
    """Radio for the OCR mode; returns ``online_first`` or ``local_only``."""
    options = list(LABELS)
    mode = st.radio(
        "روش OCR برای صفحه‌های اسکن‌شده",
        options,
        index=options.index(default_mode()),
        format_func=LABELS.get,
        horizontal=True,
        help=HELP,
        key=key,
    )
    if not local_engine_ready():
        st.caption("OCR محلی نصب نیست: `pip install rapidocr-onnxruntime` (سبک و بدون نیاز به برنامهٔ جانبی).")
    return mode
