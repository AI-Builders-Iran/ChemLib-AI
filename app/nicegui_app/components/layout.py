"""Composes header + sidebar + main content area for every authenticated page."""

from __future__ import annotations

from collections.abc import Callable
from contextlib import contextmanager

from nicegui import ui

from .. import theme
from ..state import session
from . import header, sidebar


@contextmanager
def page(current_path: str):
    """Usage: ``with layout.page('/chat'): ...page content...``

    Every page here is open to any visitor — the backend has no multi-user
    accounts, only a single shared admin password gating *library
    management* (see ``app/auth.py``). Pages that contain admin-only actions
    (adding/removing shared-library documents, system status) check
    ``state.session.is_admin()`` inline and show :func:`admin_only_notice`
    instead, exactly like the Streamlit admin panel did.
    """
    theme.apply()

    def logout() -> None:
        session.set_admin(False)
        ui.navigate.to("/")

    drawer = sidebar.render(current_path)
    header.render(drawer=drawer, on_logout=logout if session.is_admin() else None)

    with ui.column().classes("w-full max-w-6xl mx-auto p-4 gap-4 dx-rtl"):
        yield


def admin_only_notice(action: str = "این بخش") -> None:
    """Shown instead of an admin-only control when the visitor isn't logged in."""
    with ui.element("div").classes("dx-card p-3 dx-rtl").style(f"border-inline-start:4px solid {theme.WARN}"):
        ui.label(f"{action} فقط برای مدیر کتابخانه در دسترس است.").classes("text-sm")
        ui.link("ورود مدیر", "/login").classes("text-sm").style(f"color:{theme.BRAND_INK}")
