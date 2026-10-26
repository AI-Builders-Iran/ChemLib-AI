"""Documents — the shared library (admin-managed) and this tab's private,
temporary documents. Both existed in the Streamlit UI as two chat-mode
tabs; here they're two tabs of one page, which better fits "Document
Management" as its own section.

Every status shown ("✓ ایندکس‌شده") is real: a document only appears here
once ``IngestionPipeline`` has actually added its chunks to the vector
store. There is no "pending/processing" queue in the backend to reflect —
ingestion is synchronous — so no such status is shown.

Opening this page never starts ingestion and never embeds anything: listing
documents reads Chroma metadata only (see ``src/embedding/embedding.py`` —
the embedding model loads lazily, on an actual query/add, not on listing),
and is still fetched in a worker thread (``run.io_bound``) so even a slow
first vector-store connection can't block the page.
"""

from __future__ import annotations

import logging

from nicegui import run, ui

from ..components import dialogs, document_card, layout, upload
from ..services import backend
from ..state import session

logger = logging.getLogger(__name__)


@ui.page("/documents")
async def documents_page() -> None:
    with layout.page("/documents"):
        ui.label("اسناد").classes("text-2xl font-bold")

        with ui.tabs().classes("w-full") as tabs:
            library_tab = ui.tab("کتابخانه", icon="menu_book")
            private_tab = ui.tab("سند من", icon="description")

        with ui.tab_panels(tabs, value=library_tab).classes("w-full"):
            with ui.tab_panel(library_tab):
                library_list_box = await _library_panel()
            with ui.tab_panel(private_tab):
                private_list_box, private_store_ok, clear_all_box = await _private_panel()

    # Wait for the real websocket before the slower backend-bound fetches —
    # see the matching note in pages/dashboard.py.
    await ui.context.client.connected()

    # ---- Fetch document lists off the event loop, fill in after the shell is up ----
    if library_list_box is not None:
        try:
            documents = await run.io_bound(backend.library_documents)
        except Exception:  # noqa: BLE001
            logger.exception("Could not read the library")
            library_list_box.clear()
            with library_list_box:
                ui.label("پایگاه دانش در دسترس نیست.").classes("text-negative")
        else:
            library_list_box.clear()
            with library_list_box:
                _document_list(documents, allow_delete=session.is_admin(), store=None)

    if private_store_ok is not None and private_list_box is not None:
        documents = await run.io_bound(backend.private_documents, private_store_ok)
        private_list_box.clear()
        with private_list_box:
            _document_list(documents, allow_delete=True, store=private_store_ok)

        if documents:
            def clear_all() -> None:
                session.clear_private_store()
                ui.navigate.reload()

            with clear_all_box:
                ui.button(
                    "پاک‌کردن همهٔ سندهای من",
                    icon="delete_sweep",
                    on_click=lambda: dialogs.confirm(
                        "پاک‌کردن سندهای من",
                        "همهٔ سندهای بارگذاری‌شده در این نشست حذف می‌شوند. این کار قابل بازگشت نیست.",
                        on_confirm=clear_all,
                    ),
                ).props("flat dense color=negative")


async def _library_panel():
    """Renders the upload box immediately; returns a placeholder container
    for the document list, filled in by the caller after an async fetch."""
    if session.is_admin():
        with ui.expansion("🧪 افزودن منبع به کتابخانه").classes("w-full"):
            upload.upload_zone(store=None, on_done=lambda _: ui.navigate.reload())
    else:
        layout.admin_only_notice("افزودن یا حذف منبع")

    list_box = ui.column().classes("w-full gap-2 mt-2")
    with list_box:
        ui.spinner(size="md")
    return list_box


async def _private_panel():
    ui.label(
        "این سندها فقط در حافظهٔ همین مرورگر نگه داشته می‌شوند؛ با بستن یا تازه‌کردن صفحه از بین می‌روند."
    ).classes("text-xs dx-muted")

    try:
        store = session.private_store()
    except Exception:  # noqa: BLE001
        logger.exception("Could not create a private document store")
        ui.label("سرویس بارگذاری سند در حال حاضر در دسترس نیست.").classes("text-negative mt-3")
        return None, None, None

    with ui.expansion("📤 بارگذاری سند", value=not session.has_private_store()).classes("w-full"):
        upload.upload_zone(store=store, on_done=lambda _: ui.navigate.reload())

    list_box = ui.column().classes("w-full gap-2 mt-2")
    with list_box:
        ui.spinner(size="md")

    clear_all_box = ui.row().classes("mt-2")
    return list_box, store, clear_all_box


def _document_list(documents, *, allow_delete: bool, store) -> None:
    if not documents:
        with ui.column().classes("items-center text-center py-10 gap-2 w-full"):
            ui.icon("inventory_2", size="40px").classes("dx-muted")
            ui.label("هنوز سندی وجود ندارد").classes("font-bold")
            ui.label("برای شروع، یک سند بارگذاری کنید.").classes("dx-muted text-sm")
        return

    search = ui.input(placeholder="جست‌وجوی نام فایل…").props("outlined dense clearable").classes("w-full mb-2")
    list_box = ui.column().classes("w-full gap-2")

    def render(filter_text: str = "") -> None:
        list_box.clear()
        needle = filter_text.strip().lower()
        shown = [d for d in documents if not needle or needle in d.source_file.lower()]
        with list_box:
            if not shown:
                ui.label("نتیجه‌ای یافت نشد.").classes("dx-muted text-sm")
            for doc in shown:
                def delete(document_id: str = doc.document_id, name: str = doc.source_file) -> None:
                    def confirmed() -> None:
                        backend.delete_document(document_id, store=store)
                        ui.notify(f"«{name}» حذف شد.", type="positive")
                        ui.navigate.reload()

                    dialogs.confirm("حذف سند", f"«{name}» برای همیشه از این فهرست حذف می‌شود.", on_confirm=confirmed)

                def go_chat(document_id: str = doc.document_id) -> None:
                    session.set_scope("library" if store is None else "private", document_id)
                    ui.navigate.to("/chat")

                def go_summary(document_id: str = doc.document_id) -> None:
                    session.set_summary_doc("library" if store is None else "private", document_id)
                    ui.navigate.to("/summary")

                document_card.document_card(
                    doc.document_id,
                    doc.source_file,
                    doc.chunks,
                    on_delete=delete if allow_delete else None,
                    on_chat=go_chat,
                    on_summarize=go_summary,
                )

    search.on_value_change(lambda e: render(e.value or ""))
    render()
