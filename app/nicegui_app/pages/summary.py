"""Document Summary — pick a document (library, or one uploaded for this tab only), get a
structured summary: title, overview, key points, key terms.

The page only collects the choice and shows the result. The work — fetching the stored chunks,
long-document map-reduce, caching, language, error typing — is ``rag/summarizer.py`` behind
``services/backend.summarize_document``; nothing of it is reimplemented here.
"""

from __future__ import annotations

import logging

from nicegui import run, ui

from app.text_helpers import display_name

from ..components import chat_message, layout, summary_card, upload
from ..services import backend
from ..state import session

logger = logging.getLogger(__name__)


@ui.page("/summary")
async def summary_page() -> None:
    with layout.page("/summary"):
        ui.label("خلاصه‌سازی سند").classes("text-2xl font-bold")
        ui.label(
            "یک سند را انتخاب کنید تا عنوان، خلاصه، نکات کلیدی و اصطلاحات مهم آن ساخته شود. "
            "خلاصه فقط از متن همان سند ساخته می‌شود."
        ).classes("text-sm dx-muted dx-rtl")

        mode_toggle = ui.toggle({"library": "📚 کتابخانه", "private": "📄 سند من"}, value="library").props("no-caps")
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
    store = None
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
    else:
        try:
            documents = await run.io_bound(backend.library_documents)
        except Exception:  # noqa: BLE001
            logger.exception("Could not read the library")
            body.clear()
            with body:
                ui.label("پایگاه دانش در دسترس نیست.").classes("text-negative")
            return

    body.clear()
    with body:
        if mode == "private":
            with ui.expansion("📤 بارگذاری سند", value=not documents).classes("w-full"):
                ui.label(
                    "این سند فقط در حافظهٔ همین مرورگر نگه داشته می‌شود؛ با بستن یا تازه‌کردن صفحه از بین می‌رود."
                ).classes("text-xs dx-muted")
                upload.upload_zone(store=store, on_done=lambda _: ui.navigate.reload())

        if not documents:
            ui.label(
                "کتابخانه هنوز منبعی ندارد." if mode == "library" else "ابتدا یک سند بارگذاری کنید."
            ).classes("dx-muted")
            return

        _summary_panel(mode=mode, store=store, documents=documents)


def _summary_panel(*, mode: str, store, documents) -> None:
    by_id = {d.document_id: d for d in documents}
    options = {d.document_id: display_name(d.source_file) for d in documents}
    remembered = session.summary_doc(mode)  # also set by the summary button on the Documents page
    selected = {"id": remembered if remembered in by_id else documents[0].document_id}

    with ui.row().classes("w-full items-center gap-3 no-wrap"):
        select = ui.select(options, value=selected["id"], label="سند").classes("flex-1")
        button = ui.button("خلاصه کن", icon="summarize").props("color=primary no-caps")

    result_box = ui.column().classes("w-full gap-3")

    def on_select(event) -> None:
        selected["id"] = event.value
        session.set_summary_doc(mode, event.value)
        result_box.clear()

    select.on_value_change(on_select)

    async def summarize() -> None:
        document_id = selected["id"]
        if not document_id:
            return
        button.props("loading disable")
        select.props("disable")
        result_box.clear()
        with result_box:
            with ui.row().classes("items-center gap-2 dx-rtl"):
                ui.spinner(size="sm")
                ui.label(
                    "در حال خلاصه‌سازی… برای سندهای بلند ممکن است چند دقیقه طول بکشد."
                ).classes("text-sm dx-muted")

        error: Exception | None = None
        summary = None
        try:
            # Blocking LLM work: a worker thread keeps the UI (and other tabs) responsive.
            summary = await run.io_bound(backend.summarize_document, document_id, store)
        except Exception as exc:  # noqa: BLE001 - every failure is shown, typed, to the user
            logger.exception("Summarization failed for %s", document_id)
            error = exc
        finally:
            button.props(remove="loading disable")
            select.props(remove="disable")

        result_box.clear()
        with result_box:
            if error is not None:
                chat_message.error_bubble(
                    backend.summary_error_message(error), detail=str(error), on_retry=summarize
                )
            elif summary is None:  # run.io_bound returns None when the call was cancelled
                chat_message.error_bubble("خلاصه‌سازی پیش از پایان لغو شد.", on_retry=summarize)
            else:
                summary_card.render(summary)

    button.on_click(summarize)
