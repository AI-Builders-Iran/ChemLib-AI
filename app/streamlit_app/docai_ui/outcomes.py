"""Shows the result of indexing files (used by the admin panel and the private upload)."""

from __future__ import annotations

from collections.abc import Iterable

import streamlit as st

from rag.schemas import IngestFileResult

from app.text_helpers import ocr_summary, to_fa_digits

# Above this many files, successes are summarised instead of listed one by one.
DETAIL_LIMIT = 8


def ocr_note(result: IngestFileResult) -> str:
    """" OCR: OpenRouter (آنلاین) ۳ صفحه." or an empty string when no page was OCR'd."""
    return f" OCR: {ocr_summary(result.ocr_pages)}." if result.ocr_pages else ""


def skipped_note(result: IngestFileResult) -> str:
    """" ۲ صفحه به‌دلیل شکل/نمودار پیچیده رد شد." or an empty string."""
    if not result.skipped_figure_pages:
        return ""
    return f" {to_fa_digits(result.skipped_figure_pages)} صفحه به‌دلیل شکل/نمودار پیچیده رد شد (OCR نشد)."


def show(results: Iterable[IngestFileResult]) -> None:
    results = list(results)
    if not results:
        return

    added = [r for r in results if r.status in ("added", "replaced")]
    problems = [r for r in results if r.status not in ("added", "replaced")]

    if added:
        total_chunks = sum(r.chunks for r in added)
        if len(added) <= DETAIL_LIMIT:
            for r in added:
                verb = "جایگزین شد" if r.status == "replaced" else "اضافه شد"
                st.success(
                    f"«{r.filename}» {verb}: {to_fa_digits(r.chunks)} بخش ایندکس شد."
                    f"{ocr_note(r)}{skipped_note(r)}"
                )
                if r.unread_pages:
                    st.warning(
                        f"«{r.filename}»: {to_fa_digits(r.unread_pages)} صفحهٔ اسکن‌شده خوانده نشد "
                        "(هیچ موتور OCR نتیجهٔ قابل‌قبول نداد). وضعیت موتورها را در «وضعیت تنظیمات» ببینید."
                    )
        else:
            st.success(
                f"{to_fa_digits(len(added))} فایل اضافه شد ({to_fa_digits(total_chunks)} بخش ایندکس شد)."
            )
            with st.expander("فهرست فایل‌های اضافه‌شده"):
                st.markdown("\n".join(f"- {r.filename}{ocr_note(r)}{skipped_note(r)}" for r in added))
            unread = sum(r.unread_pages for r in added)
            if unread:
                st.warning(f"{to_fa_digits(unread)} صفحهٔ اسکن‌شده در این فایل‌ها خوانده نشد (هیچ موتور OCR نتیجهٔ قابل‌قبول نداد).")

    for r in problems:
        _show_problem(r)


def _show_problem(r: IngestFileResult) -> None:
    name = r.filename
    removed_note = " نسخهٔ قبلی این فایل حذف شده است." if r.old_version_removed else ""

    if r.status == "skipped":
        st.info(f"«{name}» از قبل در کتابخانه است. برای جایگزینی، گزینهٔ جایگزینی را فعال کنید.")
    elif r.status == "duplicate_name":
        st.warning(f"«{name}» نام تکراری دارد و اضافه نشد (در پوشه‌ای دیگر فایلی با همین نام هست).")
    elif r.status == "empty":
        st.warning(
            f"از «{name}» متنی استخراج نشد.{removed_note} "
            "اگر فایل اسکن‌شده است، موتورهای OCR را در بخش «وضعیت تنظیمات» بررسی کنید."
        )
    else:
        st.error(f"افزودن «{name}» ناموفق بود.{removed_note}")
        if r.detail:
            with st.expander("جزئیات فنی"):
                st.code(r.detail)
