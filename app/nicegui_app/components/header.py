"""Top header bar."""

from __future__ import annotations

from nicegui import ui

from .. import theme
from ..state import session


def render(*, drawer: ui.left_drawer, on_logout=None) -> None:
    with ui.header().classes("items-center justify-between").style(
        f"background:{theme.CARD}; color:{theme.INK}; border-bottom:1px solid {theme.LINE};"
    ):
        with ui.row().classes("items-center gap-2"):
            ui.button(icon="menu", on_click=drawer.toggle).props("flat dense round").classes("lg:hidden")
            ui.icon("science").classes("text-2xl").style(f"color:{theme.BRAND}")
            with ui.row().classes("items-baseline gap-1"):
                ui.label("ChemLib").classes("font-bold text-lg")
                ui.label("-AI").classes("font-bold text-lg").style(f"color:{theme.BRAND_INK}")

        with ui.row().classes("items-center gap-3"):
            if session.is_admin():
                ui.badge("مدیر کتابخانه", color="teal-1").props("text-color=teal-9")
            if on_logout:
                ui.button("خروج", icon="logout", on_click=on_logout).props("flat dense")
