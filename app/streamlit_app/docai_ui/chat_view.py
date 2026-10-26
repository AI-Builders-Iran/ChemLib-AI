"""The user-facing chat.

Two sources of answers, chosen with the switch at the top:

* **کتابخانه** (library): the books indexed by the library admin.
* **سند من** (my documents): a file or folder the user loads for this session
  only. It lives in memory (``SessionVectorStore``), never reaches the shared
  vector database and disappears with the session.
"""

from __future__ import annotations

import logging
from html import escape

import streamlit as st

from app import compare_intent
from app.text_helpers import display_name, element_symbol, page_label, tile_color_index, to_fa_digits, unique_sources

from . import components, ocr_choice, outcomes, services

logger = logging.getLogger(__name__)

USER_AVATAR = ":material/person:"
ASSISTANT_AVATAR = ":material/science:"

MODE_KEY = "dx_chat_mode"
MODE_LIBRARY = "کتابخانه"
MODE_PRIVATE = "سند من"

LIBRARY_MESSAGES_KEY = "dx_messages"
LIBRARY_SCOPE_KEY = "dx_scope"
PRIVATE_MESSAGES_KEY = "dx_private_messages"
PRIVATE_SCOPE_KEY = "dx_private_scope"
PRIVATE_OUTCOMES_KEY = "dx_private_outcomes"

GENERIC_ERROR = "پاسخ‌گویی در حال حاضر ممکن نیست. چند لحظهٔ دیگر دوباره تلاش کنید."

# A small colour cue before each citation's label — best-effort match to the
# t0..t5 tile palette in theme.py, so a citation hints at "which book" even
# before it's opened.
_DOTS = ("🟠", "🔵", "🟣", "🔴", "🟢", "🟡")


def render(is_admin: bool) -> None:
    documents, library_error = _load_library()

    valid_modes = (MODE_LIBRARY, MODE_PRIVATE)
    if st.session_state.get(MODE_KEY) not in valid_modes:
        # An empty library cannot answer anything: start on the private tab.
        st.session_state[MODE_KEY] = MODE_LIBRARY if documents else MODE_PRIVATE

    st.radio(
        "منبع پاسخ",
        list(valid_modes),
        horizontal=True,
        label_visibility="collapsed",
        key=MODE_KEY,
        format_func=lambda v: f"📚 {v}" if v == MODE_LIBRARY else f"📄 {v}",
    )

    if st.session_state[MODE_KEY] == MODE_PRIVATE:
        _render_private(is_admin)
    else:
        _render_library(documents, library_error, is_admin)


# ---------------------------------------------------------------------------
# Library mode
# ---------------------------------------------------------------------------

def _load_library():
    try:
        return services.library_documents(), None
    except Exception as exc:  # noqa: BLE001
        logger.exception("Could not read the library")
        return [], exc


def _render_library(documents, error, is_admin: bool) -> None:
    if error is not None:
        st.error("پایگاه دانش در دسترس نیست. با مدیر کتابخانه تماس بگیرید.")
        if is_admin:
            st.code(str(error))
        st.chat_input("پایگاه دانش در دسترس نیست", disabled=True)
        return

    if not documents:
        st.markdown(components.empty_library(is_admin), unsafe_allow_html=True)
        st.chat_input("کتابخانه هنوز منبعی ندارد", disabled=True)
        return

    _conversation(
        documents=documents,
        service_factory=services.get_rag_service,
        messages_key=LIBRARY_MESSAGES_KEY,
        scope_key=LIBRARY_SCOPE_KEY,
        hero_html=components.hero([(d.document_id, d.source_file) for d in documents]),
        placeholder="سؤال خود را بنویسید، مثلاً: پیوند کووالانسی چیست؟",
        is_admin=is_admin,
    )


# ---------------------------------------------------------------------------
# Private mode: the user's own file(s), memory only
# ---------------------------------------------------------------------------

def _render_private(is_admin: bool) -> None:
    documents = services.private_documents()

    _render_private_upload(has_documents=bool(documents), is_admin=is_admin)

    last_results = st.session_state.pop(PRIVATE_OUTCOMES_KEY, None)
    if last_results:
        outcomes.show(last_results)

    if not documents:
        st.markdown(components.private_hero([]), unsafe_allow_html=True)
        st.chat_input("ابتدا فایل یا پوشهٔ خود را بارگذاری کنید", disabled=True)
        return

    _conversation(
        documents=documents,
        service_factory=lambda: services.make_rag_service(services.private_store()),
        messages_key=PRIVATE_MESSAGES_KEY,
        scope_key=PRIVATE_SCOPE_KEY,
        hero_html=components.private_hero([(d.document_id, d.source_file) for d in documents]),
        placeholder="دربارهٔ سندهای خودتان بپرسید",
        is_admin=is_admin,
    )


def _render_private_upload(has_documents: bool, is_admin: bool) -> None:
    title = "📤 افزودن فایل یا پوشهٔ دیگر" if has_documents else "📤 بارگذاری فایل یا پوشه"
    with st.expander(title, expanded=not has_documents):
        with st.form("dx_private_form", clear_on_submit=True):
            files = st.file_uploader(
                "یک فایل، چند فایل یا یک پوشه (به‌صورت ZIP)",
                type=["pdf", "docx", "txt", "zip"],
                accept_multiple_files=True,
                help=(
                    "برای بارگذاری پوشه، آن را ZIP کنید و همان فایل را انتخاب کنید. "
                    "فقط PDF، DOCX و TXT خوانده می‌شود. فایل‌های اسکن‌شده با OCR خوانده می‌شوند و کندترند."
                ),
            )
            ocr_mode = ocr_choice.render("dx_ocr_private")
            submitted = st.form_submit_button("بارگذاری موقت", type="primary", use_container_width=True)

        if submitted:
            _ingest_private(files, is_admin, ocr_mode)

    if has_documents and st.button("پاک‌کردن سندهای من"):
        services.clear_private_store()
        st.session_state[PRIVATE_MESSAGES_KEY] = []
        st.session_state.pop(PRIVATE_SCOPE_KEY, None)
        st.rerun()


def _ingest_private(files, is_admin: bool, ocr_mode: str) -> None:
    if not files:
        st.warning("ابتدا یک فایل یا ZIP انتخاب کنید.")
        return

    progress = st.progress(0.0)
    note = st.empty()
    results = []
    try:
        store = services.private_store()
        for index, uploaded in enumerate(files, start=1):
            note.info(
                f"در حال پردازش «{uploaded.name}» "
                f"({to_fa_digits(index)} از {to_fa_digits(len(files))}). این کار ممکن است چند دقیقه طول بکشد."
            )
            if uploaded.name.lower().endswith(".zip"):

                def report(i: int, total: int, name: str, archive_name: str = uploaded.name) -> None:
                    note.info(f"«{archive_name}»: پردازش «{name}» ({to_fa_digits(i)} از {to_fa_digits(total)})…")

                # Same name again replaces the earlier copy: nothing here is shared.
                results.extend(
                    services.ingest_zip(
                        uploaded.name, uploaded.getvalue(), True, store=store, on_progress=report, ocr_mode=ocr_mode
                    )
                )
            else:
                results.append(
                    services.ingest_upload(uploaded.name, uploaded.getvalue(), True, store=store, ocr_mode=ocr_mode)
                )
            progress.progress(index / len(files))
    except Exception as exc:  # noqa: BLE001
        logger.exception("Private upload failed")
        st.error("بارگذاری انجام نشد. چند لحظهٔ دیگر دوباره تلاش کنید.")
        if is_admin:
            st.code(str(exc))
        return

    st.session_state[PRIVATE_OUTCOMES_KEY] = results
    st.rerun()


# ---------------------------------------------------------------------------
# Shared conversation
# ---------------------------------------------------------------------------

def _conversation(
    *,
    documents,
    service_factory,
    messages_key: str,
    scope_key: str,
    hero_html: str,
    placeholder: str,
    is_admin: bool,
) -> None:
    st.session_state.setdefault(messages_key, [])
    messages: list[dict] = st.session_state[messages_key]
    pending_key = f"{messages_key}_pending"

    # The input is pinned to the bottom of the page wherever it is called, so
    # read it first: a new question must be in the history before we draw it.
    submitted = st.chat_input(placeholder, max_chars=1000)
    question = submitted.strip() if submitted else ""
    if not question:
        # A suggested-prompt chip was clicked on the previous run (see
        # _render_suggested_prompts): it stashed its text here and reran.
        question = st.session_state.pop(pending_key, "")
    if question:
        messages.append({"role": "user", "content": question})

    scope = _render_toolbar(documents, messages_key, scope_key)

    if not messages:
        st.markdown(hero_html, unsafe_allow_html=True)
        _render_suggested_prompts(pending_key, documents)
        st.markdown(components.footer_note(), unsafe_allow_html=True)

    for index, message in enumerate(messages):
        _render_message(f"{messages_key}-{index}", message, is_admin)

    if question:
        _reply(question, scope, service_factory, messages_key, is_admin, documents)


def _render_toolbar(documents, messages_key: str, scope_key: str) -> str | None:
    """Scope selector (only useful with 2+ documents) and the new-chat button."""
    has_messages = bool(st.session_state.get(messages_key))
    show_scope = len(documents) > 1
    if not (show_scope or has_messages):
        return None

    scope: str | None = None
    scope_col, reset_col = st.columns([3, 1], vertical_alignment="bottom")

    if show_scope:
        names = {d.document_id: d.source_file for d in documents}
        options: list[str | None] = [None, *names]
        if st.session_state.get(scope_key) not in options:
            st.session_state[scope_key] = None  # the selected document is gone
        with scope_col:
            scope = st.selectbox(
                "جست‌وجو در",
                options,
                format_func=lambda value: "همهٔ منابع" if value is None else names[value],
                key=scope_key,
            )

    if has_messages:
        with reset_col:
            if st.button("گفتگوی جدید ↻", use_container_width=True, key=f"{messages_key}_reset"):
                st.session_state[messages_key] = []
                st.rerun()

    return scope


def _suggested_prompts(documents) -> list[str]:
    """A handful of ready-made prompts for the empty-chat state — one of them
    always demonstrates Compare Sources, using two of the real document names
    so it's guaranteed to resolve (see compare_intent.detect_compare)."""
    prompts = ["این مقاله را خلاصه کن"]
    if len(documents) >= 2:
        a = display_name(documents[0].source_file)
        b = display_name(documents[1].source_file)
        prompts.append(f"«{a}» و «{b}» را مقایسه کن")
    prompts.append("روش آزمایش استفاده‌شده در این مقاله چیست؟")
    prompts.append("منابع مرتبط با این موضوع را پیدا کن")
    return prompts


def _render_suggested_prompts(pending_key: str, documents) -> None:
    prompts = _suggested_prompts(documents)
    with st.container(key=f"{pending_key}_chips"):
        st.markdown('<div class="dx-chip-anchor"></div>', unsafe_allow_html=True)
        cols = st.columns(len(prompts))
        for col, prompt in zip(cols, prompts):
            with col:
                if st.button(prompt, key=f"{pending_key}_{prompt}", use_container_width=True):
                    st.session_state[pending_key] = prompt
                    st.rerun()


def _reply(question: str, scope: str | None, service_factory, messages_key: str, is_admin: bool, documents) -> None:
    """Run the question through the RAG service (or Compare, if detected) and draw (and store) the reply."""
    with st.chat_message("assistant", avatar=ASSISTANT_AVATAR):
        with st.spinner("در حال جست‌وجو در منابع…"):
            reply = _ask(question, scope, service_factory, documents)
        st.session_state[messages_key].append(reply)
        msg_id = f"{messages_key}-{len(st.session_state[messages_key]) - 1}"
        _render_body(msg_id, reply, is_admin)


def _ask(question: str, scope: str | None, service_factory, documents) -> dict:
    pair = compare_intent.detect_compare(question, documents)
    if pair is not None:
        return _ask_compare(question, service_factory, pair)

    try:
        response = service_factory().answer_question(question, scope)
    except Exception as exc:  # noqa: BLE001
        logger.exception("Chat failed")
        return {"role": "assistant", "kind": "error", "content": GENERIC_ERROR, "detail": str(exc)}

    sources = unique_sources(
        {"file": s.source_file, "page": s.page, "snippet": s.snippet} for s in response.sources
    )
    return {
        "role": "assistant",
        "kind": "answer" if response.grounded else "not_found",
        "content": response.answer,
        "sources": sources,
    }


def _ask_compare(question: str, service_factory, pair) -> dict:
    """Compare two sources within the same chat (no separate page/screen).

    Reuses the existing Compare backend (``RAGService.compare_sources``, the
    same logic behind ``POST /api/v1/compare``) — this is only the chat-side
    integration: detect the intent, resolve the two sources, call the
    service, and render the result as one assistant message.
    """
    doc_a, doc_b = pair
    try:
        result = service_factory().compare_sources(question, doc_a.document_id, doc_b.document_id)
    except Exception as exc:  # noqa: BLE001
        logger.exception("Compare failed")
        return {"role": "assistant", "kind": "error", "content": GENERIC_ERROR, "detail": str(exc)}

    def section(document, book) -> dict:
        return {
            "title": document.source_file,
            "definition": book.definition,
            "explanation": book.explanation,
            "sources": unique_sources(
                {"file": s.source_file, "page": s.page, "snippet": s.snippet} for s in book.sources
            ),
        }

    return {
        "role": "assistant",
        "kind": "compare",
        "content": result.comparison,
        "sections": [section(doc_a, result.book_a), section(doc_b, result.book_b)],
    }


def _render_message(msg_id: str, message: dict, is_admin: bool) -> None:
    if message["role"] == "user":
        with st.chat_message("user", avatar=USER_AVATAR):
            st.markdown(components.user_text(message["content"]), unsafe_allow_html=True)
        return

    with st.chat_message("assistant", avatar=ASSISTANT_AVATAR):
        _render_body(msg_id, message, is_admin)


def _render_body(msg_id: str, message: dict, is_admin: bool) -> None:
    kind = message.get("kind", "answer")

    if kind == "answer":
        st.markdown(message["content"])
        _render_sources(f"{msg_id}-src", message.get("sources", []))
    elif kind == "compare":
        st.markdown(components.compare_summary(message["content"]), unsafe_allow_html=True)
        sections = message.get("sections", [])
        cols = st.columns(len(sections)) if sections else []
        for i, (col, section) in enumerate(zip(cols, sections)):
            with col:
                st.markdown(
                    components.compare_section(
                        section["title"], section["definition"], section["explanation"]
                    ),
                    unsafe_allow_html=True,
                )
                _render_sources(f"{msg_id}-c{i}", section.get("sources", []), label="منابع")
    elif kind == "not_found":
        st.markdown(components.not_found(message["content"]), unsafe_allow_html=True)
    else:
        st.error(message["content"])
        if is_admin and message.get("detail"):
            with st.expander("جزئیات فنی (فقط برای مدیر)"):
                st.code(message["detail"])


def _render_sources(msg_id: str, sources: list[dict], label: str = "منابع پاسخ") -> None:
    """Citations as small clickable chips (not a wall of tiles): each opens a
    popover with the book name, page, and a short excerpt of the cited
    passage — so a claim can be checked without leaving the chat."""
    if not sources:
        return

    st.markdown(f'<div class="dx-shelf-label">{label}</div>', unsafe_allow_html=True)
    per_row = 6
    for row_start in range(0, len(sources), per_row):
        row = sources[row_start : row_start + per_row]
        cols = st.columns(len(row))
        for offset, (col, source) in enumerate(zip(cols, row)):
            index = row_start + offset
            page = page_label(source.get("page"))
            dot = _DOTS[tile_color_index(source["file"]) % len(_DOTS)]
            caption = f'{dot} {element_symbol(source["file"])}' + (f" · {page}" if page else "")
            with col:
                with st.popover(caption, use_container_width=True, key=f"{msg_id}-{index}"):
                    heading = display_name(source["file"])
                    if page:
                        heading += f" — صفحهٔ {page}"
                    st.markdown(f"**{heading}**")
                    snippet = source.get("snippet")
                    if snippet:
                        st.markdown(
                            f'<div class="dx-cite-snippet">«{escape(snippet)}»</div>', unsafe_allow_html=True
                        )
                    else:
                        st.caption("متنی برای پیش‌نمایش در دسترس نیست.")
