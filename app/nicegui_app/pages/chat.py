"""AI Chat — the main RAG conversation, over the shared library or the
tab's private documents. Mirrors the Streamlit chat_view.py logic exactly
(same compare-intent detection, same source citations) on top of NiceGUI.
"""

from __future__ import annotations

import logging

from nicegui import run, ui

from app import compare_intent
from app.text_helpers import display_name, unique_sources

from ..components import chat_message, layout, upload
from ..services import backend
from ..state import session

logger = logging.getLogger(__name__)

GENERIC_ERROR = "پاسخ‌گویی در حال حاضر ممکن نیست. چند لحظهٔ دیگر دوباره تلاش کنید."


@ui.page("/chat")
async def chat_page() -> None:
    with layout.page("/chat"):
        ui.label("گفتگوی هوشمند").classes("text-2xl font-bold")

        mode_toggle = ui.toggle({"library": "📚 کتابخانه", "private": "📄 سند من"}, value="library").props(
            "no-caps"
        )

        body = ui.column().classes("w-full gap-3")

    async def rebuild() -> None:
        body.clear()
        with body:
            ui.spinner(size="md")
        await _render_mode(mode_toggle.value, body)

    mode_toggle.on_value_change(rebuild)

    # See the matching note in pages/dashboard.py.
    await ui.context.client.connected()
    await rebuild()


async def _render_mode(mode: str, body) -> None:
    if mode == "private":
        try:
            store = session.private_store()
        except Exception:  # noqa: BLE001
            logger.exception("Could not create a private document store")
            body.clear()
            with body:
                ui.label("سرویس سند خصوصی در حال حاضر در دسترس نیست.").classes("text-negative")
            return
        documents = await run.io_bound(backend.private_documents, store)
        service_factory = lambda: backend.make_rag_service(store)  # noqa: E731
    else:
        try:
            # Cheap after the first call (metadata only, no embedding model
            # load — see src/embedding/embedding.py) but still real I/O on
            # the very first Chroma connection, so it stays off the event loop.
            documents = await run.io_bound(backend.library_documents)
        except Exception:  # noqa: BLE001
            logger.exception("Could not read the library")
            body.clear()
            with body:
                ui.label("پایگاه دانش در دسترس نیست.").classes("text-negative")
            return
        service_factory = backend.get_rag_service

    body.clear()
    with body:
        if mode == "private":
            _render_private_intro(store)

        if not documents:
            ui.label(
                "کتابخانه هنوز منبعی ندارد." if mode == "library" else "ابتدا یک سند بارگذاری کنید."
            ).classes("dx-muted")
            return

        _conversation(mode=mode, documents=documents, service_factory=service_factory)


def _render_private_intro(store) -> None:
    with ui.expansion("📤 بارگذاری سند خصوصی", value=not session.has_private_store()).classes("w-full"):
        ui.label(
            "این سند فقط در حافظهٔ همین مرورگر نگه داشته می‌شود؛ با بستن یا تازه‌کردن صفحه از بین می‌رود."
        ).classes("text-xs dx-muted")
        upload.upload_zone(store=store, on_done=lambda _: ui.navigate.reload())


def _conversation(*, mode: str, documents, service_factory) -> None:
    messages = session.chat_messages(mode)

    # ---- toolbar: scope selector + clear ----
    with ui.row().classes("w-full items-center gap-3"):
        scope_value = {"id": session.scope(mode)}
        if len(documents) > 1:
            options = {None: "همهٔ منابع"} | {d.document_id: d.source_file for d in documents}
            select = ui.select(options, value=session.scope(mode)).classes("flex-1")
            select.on_value_change(lambda e: session.set_scope(mode, e.value))
        else:
            ui.space()
        if messages:
            ui.button("گفتگوی جدید", icon="refresh_right", on_click=lambda: (
                session.clear_chat(mode), ui.navigate.reload()
            )).props("flat dense")

    history_box = ui.column().classes("w-full gap-3")

    def render_history() -> None:
        history_box.clear()
        with history_box:
            if not messages:
                _empty_state(documents, on_prompt=ask)
            for message in messages:
                if message["role"] == "user":
                    chat_message.user_bubble(message["content"])
                else:
                    with ui.row().classes("w-full"):
                        ui.icon("science", color="primary").classes("mt-1")
                        chat_message.assistant_body(message)

    async def ask(question: str) -> None:
        question = question.strip()
        if not question:
            return
        text_input.set_value("")
        send_button.props("loading disable")
        messages.append({"role": "user", "content": question})
        render_history()

        with history_box:
            with ui.row().classes("w-full"):
                ui.icon("science", color="primary").classes("mt-1")
                with ui.column().classes("dx-bubble-assistant"):
                    with ui.row().classes("items-center gap-2"):
                        ui.spinner(size="sm")
                        ui.label("در حال جست‌وجو در منابع…").classes("text-sm dx-muted")

        try:
            # The RAG/LLM call is blocking I/O; run it off the event loop so
            # it never freezes the UI for other connected tabs.
            reply = await run.io_bound(_ask, question, session.scope(mode), service_factory, documents)
        finally:
            send_button.props(remove="loading disable")
        messages.append(reply)
        render_history()

    # ---- input ----
    with ui.row().classes("w-full items-end gap-2 sticky bottom-0 bg-white py-2"):
        text_input = ui.input(placeholder="سؤال خود را بنویسید…").classes("flex-1").props("outlined dense")
        send_button = ui.button(icon="send").props("round color=primary")

    send_button.on_click(lambda: ask(text_input.value))
    text_input.on("keydown.enter", lambda: ask(text_input.value))

    render_history()


def _empty_state(documents, on_prompt) -> None:
    from .. import theme

    with ui.column().classes("items-center text-center py-10 gap-2 w-full"):
        ui.icon("science", size="48px").style(f"color:{theme.BRAND}")
        ui.label("از منابع بپرسید").classes("text-xl font-bold")
        ui.label("پاسخ فقط از متن منابع ایندکس‌شده ساخته می‌شود.").classes("dx-muted")

        prompts = ["این مقاله را خلاصه کن"]
        if len(documents) >= 2:
            a, b = display_name(documents[0].source_file), display_name(documents[1].source_file)
            prompts.append(f"«{a}» و «{b}» را مقایسه کن")
        prompts += ["روش آزمایش استفاده‌شده در این مقاله چیست؟", "منابع مرتبط با این موضوع را پیدا کن"]

        with ui.row().classes("gap-2 flex-wrap justify-center mt-2"):
            for prompt in prompts:
                ui.button(prompt, on_click=lambda p=prompt: on_prompt(p)).props(
                    "outline dense no-caps"
                ).classes("text-xs")


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
