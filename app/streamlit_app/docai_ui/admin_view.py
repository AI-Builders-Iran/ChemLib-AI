"""Library-admin area: sign in, add documents to the vector database, manage them.

Nothing here is reachable by regular users: the panel is only drawn after a
successful password check stored in this browser session, and every function
that changes the library re-checks that flag.
"""

from __future__ import annotations

import logging
import time

import streamlit as st

from . import auth, components, outcomes, services
from .helpers import to_fa_digits

logger = logging.getLogger(__name__)

ADMIN_KEY = "dx_is_admin"
VIEW_KEY = "dx_view"
CONFIRM_DELETE_KEY = "dx_confirm_delete"
OUTCOMES_KEY = "dx_last_outcomes"

VIEW_CHAT = "گفتگو"
VIEW_LIBRARY = "مدیریت منابع"


def is_admin() -> bool:
    return bool(st.session_state.get(ADMIN_KEY))


# ---------------------------------------------------------------------------
# Sign-in / navigation
# ---------------------------------------------------------------------------

def render_login() -> None:
    st.markdown(components.section_title("ورود مدیر کتابخانه"), unsafe_allow_html=True)

    if not auth.admin_configured():
        st.warning(
            "ورود مدیر غیرفعال است. برای فعال‌سازی، `ADMIN_PASSWORD` را در فایل `.env` "
            "تنظیم و برنامه را دوباره اجرا کنید."
        )
    else:
        with st.form("dx_login_form"):
            password = st.text_input("رمز عبور", type="password")
            submitted = st.form_submit_button("ورود", type="primary", use_container_width=True)

        if submitted:
            if auth.verify_admin_password(password):
                st.session_state[ADMIN_KEY] = True
                st.rerun()
            time.sleep(1)  # slows down password guessing
            st.error("رمز عبور نادرست است.")

    if st.button("بازگشت به گفتگو"):
        st.query_params.clear()
        st.rerun()


def render_nav() -> str:
    """Switch between chat and library management; returns the chosen view."""
    nav_col, exit_col = st.columns([5, 1], vertical_alignment="center")
    with nav_col:
        view = st.radio(
            "بخش",
            [VIEW_CHAT, VIEW_LIBRARY],
            horizontal=True,
            label_visibility="collapsed",
            key=VIEW_KEY,
        )
    with exit_col:
        if st.button("خروج", use_container_width=True):
            for key in (ADMIN_KEY, VIEW_KEY, CONFIRM_DELETE_KEY, OUTCOMES_KEY):
                st.session_state.pop(key, None)
            st.query_params.clear()
            st.rerun()
    return view


# ---------------------------------------------------------------------------
# Library management
# ---------------------------------------------------------------------------

def render_library() -> None:
    if not is_admin():  # defence in depth: never draw this for a normal session
        return

    _show_last_outcomes()

    try:
        documents = services.library_documents()
    except Exception as exc:  # noqa: BLE001
        logger.exception("Could not read the library")
        st.error("پایگاه دانش در دسترس نیست.")
        st.code(str(exc))
        return

    st.markdown(
        components.stats_row(
            [
                ("منبع در کتابخانه", len(documents)),
                ("بخش ایندکس‌شده", sum(d.chunks for d in documents)),
            ]
        ),
        unsafe_allow_html=True,
    )

    _render_upload()
    _render_document_list(documents)
    _render_status()


def _render_upload() -> None:
    st.markdown(components.section_title("افزودن منبع جدید"), unsafe_allow_html=True)

    files_tab, folder_tab = st.tabs(["فایل یا ZIP", "پوشه روی این رایانه"])
    with files_tab:
        _render_files_form()
    with folder_tab:
        _render_folder_form()


def _finish(results: list[services.IngestOutcome]) -> None:
    services.refresh_library()
    st.session_state[OUTCOMES_KEY] = results
    st.rerun()


def _render_files_form() -> None:
    with st.form("dx_upload_form", clear_on_submit=True):
        files = st.file_uploader(
            "یک یا چند فایل، یا یک پوشه به‌صورت ZIP",
            type=["pdf", "docx", "txt", "zip"],
            accept_multiple_files=True,
            help=(
                "متن فایل خوانده، تمیز و به بخش‌های کوچک تقسیم می‌شود و در پایگاه برداری ذخیره می‌شود. "
                "برای افزودن یک پوشه، آن را ZIP کنید: همهٔ PDF، DOCX و TXTهای داخل آن (با زیرپوشه‌ها) اضافه می‌شوند. "
                "صفحه‌های اسکن‌شده با OCR خوانده می‌شوند و زمان بیشتری می‌برند."
            ),
        )
        overwrite = st.checkbox(
            "اگر منبعی با همین نام وجود دارد، جایگزین شود",
            help="نسخهٔ قبلی حذف و فایل تازه دوباره ایندکس می‌شود.",
            key="dx_overwrite_files",
        )
        submitted = st.form_submit_button("افزودن به کتابخانه", type="primary", use_container_width=True)

    if not submitted:
        return
    if not files:
        st.warning("ابتدا یک فایل انتخاب کنید.")
        return

    progress = st.progress(0.0)
    note = st.empty()
    results: list[services.IngestOutcome] = []
    for index, uploaded in enumerate(files, start=1):
        note.info(
            f"در حال پردازش «{uploaded.name}» "
            f"({to_fa_digits(index)} از {to_fa_digits(len(files))}). این کار ممکن است چند دقیقه طول بکشد."
        )
        if uploaded.name.lower().endswith(".zip"):

            def report(i: int, total: int, name: str, archive_name: str = uploaded.name) -> None:
                note.info(f"«{archive_name}»: پردازش «{name}» ({to_fa_digits(i)} از {to_fa_digits(total)})…")

            results.extend(services.ingest_zip(uploaded.name, uploaded.getvalue(), overwrite, on_progress=report))
        else:
            results.append(services.ingest_upload(uploaded.name, uploaded.getvalue(), overwrite))
        progress.progress(index / len(files))

    _finish(results)


def _render_folder_form() -> None:
    st.caption(
        "پوشه‌ای را که روی همین رایانه (سروری که برنامه روی آن اجرا می‌شود) هست مستقیم ایندکس کنید. "
        "برای پوشه‌های بزرگ، از آپلود ZIP سریع‌تر و مطمئن‌تر است."
    )
    with st.form("dx_folder_form"):
        path_text = st.text_input("مسیر پوشه", placeholder=r"D:\Books\Chemistry", key="dx_folder_path")
        recursive = st.checkbox("زیرپوشه‌ها هم خوانده شود", value=True, key="dx_folder_recursive")
        overwrite = st.checkbox("منبع هم‌نام جایگزین شود", key="dx_overwrite_folder")
        submitted = st.form_submit_button("افزودن پوشه", type="primary", use_container_width=True)

    if not submitted:
        return
    if not path_text.strip():
        st.warning("مسیر پوشه را وارد کنید.")
        return

    progress = st.progress(0.0)
    note = st.empty()

    def report(index: int, total: int, name: str) -> None:
        note.info(f"در حال پردازش «{name}» ({to_fa_digits(index)} از {to_fa_digits(total)})…")
        progress.progress((index - 1) / total)

    try:
        results = services.ingest_folder(path_text, recursive, overwrite, on_progress=report)
    except NotADirectoryError:
        progress.empty()
        note.empty()
        st.error("این مسیر وجود ندارد یا پوشه نیست.")
        return
    except Exception as exc:  # noqa: BLE001
        logger.exception("Folder ingestion failed")
        progress.empty()
        note.empty()
        st.error("افزودن پوشه ناموفق بود.")
        st.code(str(exc))
        return

    if not results:
        progress.empty()
        note.empty()
        st.warning("در این پوشه فایل PDF، DOCX یا TXT پیدا نشد.")
        return

    _finish(results)


def _show_last_outcomes() -> None:
    results = st.session_state.pop(OUTCOMES_KEY, None)
    if results:
        outcomes.show(results)


def _render_document_list(documents) -> None:
    st.markdown(components.section_title("منابع ایندکس‌شده"), unsafe_allow_html=True)

    if not documents:
        st.info("هنوز فایلی اضافه نشده است. از بخش بالا اولین منبع را اضافه کنید.")
        return

    for document in documents:
        with st.container(border=True):
            tile_col, info_col, action_col = st.columns([1, 6, 2], vertical_alignment="center")
            with tile_col:
                st.markdown(components.mini_tile(document.source_file), unsafe_allow_html=True)
            with info_col:
                st.markdown(components.doc_line(document.source_file, document.chunks), unsafe_allow_html=True)

            if st.session_state.get(CONFIRM_DELETE_KEY) == document.document_id:
                st.warning(f"«{document.source_file}» و همهٔ بخش‌های آن از کتابخانه حذف می‌شود. ادامه می‌دهید؟")
                yes_col, no_col = st.columns(2)
                if yes_col.button("حذف کن", key=f"dx_del_yes_{document.document_id}", type="primary"):
                    services.delete_document(document.document_id)
                    st.session_state.pop(CONFIRM_DELETE_KEY, None)
                    st.rerun()
                if no_col.button("انصراف", key=f"dx_del_no_{document.document_id}"):
                    st.session_state.pop(CONFIRM_DELETE_KEY, None)
                    st.rerun()
            elif action_col.button("حذف", key=f"dx_del_{document.document_id}", use_container_width=True):
                st.session_state[CONFIRM_DELETE_KEY] = document.document_id
                st.rerun()


def _render_status() -> None:
    st.markdown(components.section_title("وضعیت تنظیمات"), unsafe_allow_html=True)
    st.markdown(components.status_pills(services.system_checks()), unsafe_allow_html=True)
