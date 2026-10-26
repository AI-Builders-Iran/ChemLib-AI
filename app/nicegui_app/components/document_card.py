"""Document card — the periodic-table-style tile plus a card around it,
used on the Documents page. Only fields the backend actually returns
(filename, extension, indexed chunk count) are shown; no fabricated status."""

from __future__ import annotations

from pathlib import Path

from nicegui import ui

from app.text_helpers import display_name, element_symbol, to_fa_digits

from .. import theme


def tile(file_name: str) -> None:
    color = theme.tile_color(file_name)
    with ui.element("div").classes("dx-tile").style(f"--c: {color}"):
        ui.html(f'<span class="dx-tile-sym">{element_symbol(file_name)}</span>')
        ui.html(f'<span class="dx-tile-nm">{display_name(file_name)}</span>')


def document_card(
    document_id: str,
    file_name: str,
    chunks: int,
    *,
    on_delete=None,
    on_chat=None,
    on_summarize=None,
) -> None:
    ext = (Path(file_name).suffix.lstrip(".").upper()) or "FILE"
    with ui.element("div").classes("dx-card p-3 w-full"):
        with ui.row().classes("items-center gap-3 w-full no-wrap"):
            tile(file_name)
            with ui.column().classes("gap-1 flex-1 min-w-0"):
                ui.label(file_name).classes("font-semibold dx-rtl").style("word-break: break-word;")
                with ui.row().classes("gap-2 items-center"):
                    ui.badge(ext, color="grey-3").props("text-color=grey-9")
                    ui.badge(f"{to_fa_digits(chunks)} بخش ایندکس‌شده", color="teal-1").props(
                        "text-color=teal-9"
                    )
                    ui.badge("✓ ایندکس‌شده", color="green-1").props("text-color=green-9")
            with ui.row().classes("gap-1"):
                if on_chat:
                    ui.button(icon="chat", on_click=lambda: on_chat(document_id)).props(
                        "flat round dense"
                    ).tooltip("گفتگو دربارهٔ همین سند")
                if on_summarize:
                    ui.button(icon="summarize", on_click=lambda: on_summarize(document_id)).props(
                        "flat round dense"
                    ).tooltip("خلاصهٔ همین سند")
                if on_delete:
                    ui.button(icon="delete", on_click=lambda: on_delete(document_id, file_name)).props(
                        "flat round dense color=negative"
                    ).tooltip("حذف از کتابخانه")
