"""Reusable dialogs."""

from __future__ import annotations

from collections.abc import Callable

from nicegui import ui


def confirm(title: str, message: str, *, on_confirm: Callable[[], None], confirm_label: str = "حذف") -> None:
    """A destructive-action confirmation dialog, shown immediately."""
    with ui.dialog() as dialog, ui.card().classes("dx-rtl p-4"):
        ui.label(title).classes("text-lg font-bold")
        ui.label(message).classes("dx-muted mt-1")
        with ui.row().classes("justify-end gap-2 mt-4 w-full"):
            ui.button("انصراف", on_click=dialog.close).props("flat")

            def confirmed() -> None:
                dialog.close()
                on_confirm()

            ui.button(confirm_label, on_click=confirmed).props("color=negative")
    dialog.open()
