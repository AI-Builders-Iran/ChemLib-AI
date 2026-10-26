"""Left navigation. Collapses to a drawer toggled from the header on small
screens (NiceGUI's ``ui.left_drawer`` handles the responsive behaviour)."""

from __future__ import annotations

from nicegui import ui

from .. import theme

NAV_ITEMS = [
    ("/", "dashboard", "داشبورد"),
    ("/chat", "chat", "گفتگوی هوشمند"),
    ("/summary", "summarize", "خلاصه‌سازی سند"),
    ("/documents", "description", "اسناد"),
    ("/settings", "settings", "تنظیمات"),
]


def render(current_path: str) -> ui.left_drawer:
    drawer = ui.left_drawer(value=True, bordered=True).props("width=240").style(
        f"background:{theme.PAPER};"
    )
    with drawer:
        with ui.column().classes("gap-1 w-full p-2"):
            for path, icon, label in NAV_ITEMS:
                active = path == current_path
                with ui.link(target=path).classes("no-underline w-full"):
                    with ui.row().classes("items-center gap-3 w-full px-3 py-2 rounded-lg").style(
                        f"background:{theme.BRAND_WASH if active else 'transparent'};"
                        f"color:{theme.BRAND_INK if active else theme.INK};"
                    ):
                        ui.icon(icon)
                        ui.label(label).classes("text-sm font-medium")
    return drawer
