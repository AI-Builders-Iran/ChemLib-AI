"""Dashboard: an overview, not a decorative landing page.

Every number here comes straight from the backend. Two things the brief
asked for are deliberately left out, with a note instead of a fake value:
"documents waiting for processing" and "OCR documents" — the backend
ingests synchronously and doesn't persist either of those as queryable
state once a file is indexed (or not). A global "recent activity" feed is
also not shown for the same reason — there's no activity log in the
backend; what IS shown instead is this *browser tab's own* chat activity,
labelled as such rather than implied to be global.

The page shell (title, quick actions) renders immediately; stats and the
system checklist are fetched in a worker thread (``run.io_bound``) and fill
in once ready, so a slow/first vector-store connection never blocks the UI.
"""

from __future__ import annotations

from nicegui import run, ui

from ..components import layout, status
from ..services import backend
from ..state import session


@ui.page("/")
async def dashboard_page() -> None:
    with layout.page("/"):
        ui.label("داشبورد").classes("text-2xl font-bold")
        ui.label("نمای کلی از کتابخانه و وضعیت سیستم").classes("dx-muted -mt-2")

        stats_box = ui.row().classes("w-full gap-3 flex-wrap")
        with stats_box:
            ui.spinner(size="md")

        # ---- Quick actions (no backend call needed — render immediately) ----
        ui.label("اقدامات سریع").classes("text-lg font-bold mt-2")
        with ui.row().classes("gap-3 flex-wrap"):
            ui.button("گفتگوی هوشمند", icon="chat", on_click=lambda: ui.navigate.to("/chat")).props(
                "color=primary unelevated"
            )
            ui.button("مشاهدهٔ اسناد", icon="description", on_click=lambda: ui.navigate.to("/documents")).props(
                "outline"
            )
            if session.is_admin():
                ui.button(
                    "افزودن سند به کتابخانه", icon="upload_file", on_click=lambda: ui.navigate.to("/documents")
                ).props("outline")

        # ---- System status (admin only) ----
        ui.label("وضعیت سیستم").classes("text-lg font-bold mt-2")
        system_box = ui.column().classes("w-full")
        if session.is_admin():
            with system_box:
                ui.spinner(size="md")
        else:
            layout.admin_only_notice("وضعیت سیستم")

        # Placeholder for this tab's own chat activity — filled in below.
        # session.chat_messages() reads app.storage.tab, which (per NiceGUI)
        # requires an active client connection; that doesn't exist yet during
        # this synchronous shell render, only after the await below.
        activity_box = ui.column().classes("w-full")

    # The shell above is enough for NiceGUI to answer the initial request;
    # wait for the real websocket before doing slower backend-bound work (and
    # before any app.storage.tab access), so that work reliably streams in
    # afterward instead of racing the page's response_timeout (see NiceGUI's
    # `page.py`) or hitting app.storage.tab before the connection exists.
    await ui.context.client.connected()

    # ---- This tab's own chat activity (not a global/persisted log) ----
    recent = (session.chat_messages("library") + session.chat_messages("private"))[-5:]
    if recent:
        with activity_box:
            ui.label("فعالیت این نشست").classes("text-lg font-bold mt-2")
            with ui.element("div").classes("dx-card p-3 w-full"):
                for message in reversed(recent):
                    if message["role"] != "user":
                        continue
                    with ui.row().classes("items-center gap-2 py-1"):
                        ui.icon("chat_bubble_outline", size="18px").classes("dx-muted")
                        ui.label(message["content"]).classes("text-sm truncate")

    # ---- Fill in the backend-backed parts off the event loop ----
    stats = await run.io_bound(backend.library_stats)
    stats_box.clear()
    with stats_box:
        status.stat_card("منابع کتابخانه", stats["documents"], icon="menu_book")
        status.stat_card("بخش‌های ایندکس‌شده", stats["chunks"], icon="dataset")
        with ui.element("div").classes("dx-card p-4 flex-1 min-w-[160px]"):
            with ui.row().classes("items-center gap-2"):
                ui.icon("hub").classes("text-lg dx-brand-text")
                ui.label("پایگاه دانش").classes("text-sm dx-muted")
            ui.label("متصل" if stats["available"] else "در دسترس نیست").classes(
                "text-lg font-bold mt-1 " + ("text-green-700" if stats["available"] else "text-negative")
            )

    if session.is_admin():
        checks = await run.io_bound(backend.system_checks)
        system_box.clear()
        with system_box:
            status.checklist(checks)
