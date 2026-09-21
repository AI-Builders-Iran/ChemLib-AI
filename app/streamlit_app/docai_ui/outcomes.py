"""Shows the result of indexing files (used by the admin panel and the private upload)."""

from __future__ import annotations

from collections.abc import Iterable

import streamlit as st

from rag.schemas import IngestFileResult

from .helpers import to_fa_digits

# Above this many files, successes are summarised instead of listed one by one.
DETAIL_LIMIT = 8


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
                st.success(f"«{r.filename}» {verb}: {to_fa_digits(r.chunks)} بخش ایندکس شد.")
        else:
            st.success(
                f"{to_fa_digits(len(added))} فایل اضافه شد ({to_fa_digits(total_chunks)} بخش ایندکس شد)."
            )
            with st.expander("فهرست فایل‌های اضافه‌شده"):
                st.markdown("\n".join(f"- {r.filename}" for r in added))

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
            "اگر فایل اسکن‌شده است، کلید Gemini و Poppler را بررسی کنید."
        )
    else:
        st.error(f"افزودن «{name}» ناموفق بود.{removed_note}")
        if r.detail:
            with st.expander("جزئیات فنی"):
                st.code(r.detail)
