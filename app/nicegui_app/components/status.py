"""Status dots/badges — every value shown here comes from a real backend
check (``services/backend.py``); nothing is simulated."""

from __future__ import annotations

from nicegui import ui


def status_line(label: str, ok: bool, ok_text: str = "فعال", off_text: str = "غیرفعال") -> None:
    with ui.row().classes("items-center gap-2 py-1"):
        ui.html(f'<span class="dx-dot {"dx-dot-ok" if ok else "dx-dot-off"}"></span>')
        ui.label(label).classes("text-sm")
        ui.space()
        ui.label(ok_text if ok else off_text).classes(
            "text-xs font-medium " + ("text-green-700" if ok else "text-orange-700")
        )


def checklist(items: list[tuple[str, bool]]) -> None:
    """A vertical list of status_line rows inside a card."""
    with ui.element("div").classes("dx-card w-full p-4"):
        if not items:
            ui.label("بررسی‌ای در دسترس نیست.").classes("dx-muted text-sm")
        for label, ok in items:
            status_line(label, ok)


def stat_card(label: str, value: int | str, icon: str | None = None) -> None:
    with ui.element("div").classes("dx-card p-4 flex-1 min-w-[160px]"):
        with ui.row().classes("items-center gap-2"):
            if icon:
                ui.icon(icon).classes("text-lg dx-brand-text")
            ui.label(label).classes("text-sm dx-muted")
        ui.label(str(value)).classes("text-2xl font-bold mt-1")
