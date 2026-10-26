"""Settings.

Only sections that map to something real in the backend are shown:

* **Account** — there are no user profiles (name/email/role) in this
  backend, only "logged in as admin or not", so that's exactly what this
  shows — no fabricated profile fields.
* **AI** — read-only: which LLM provider is configured (OpenRouter) and
  whether its key is set. There is no per-user model choice to expose.
* **OCR** — the one setting a visitor can actually change, same OCR-mode
  choice every upload form in the Streamlit UI had.
* **System status** — admin-only, identical to the Streamlit admin panel's
  checklist.
"""

from __future__ import annotations

import os

from nicegui import run, ui

from app import auth

from ..components import layout, status, upload
from ..services import backend
from ..state import session


@ui.page("/settings")
async def settings_page() -> None:
    with layout.page("/settings"):
        ui.label("تنظیمات").classes("text-2xl font-bold")

        _account_section()
        _ai_section()
        _ocr_section()

        ui.label("وضعیت سیستم").classes("text-lg font-bold mt-2")
        system_box = ui.column().classes("w-full")
        if session.is_admin():
            with system_box:
                ui.spinner(size="md")
        else:
            layout.admin_only_notice("وضعیت سیستم")

    if session.is_admin():
        # See the matching note in pages/dashboard.py.
        await ui.context.client.connected()
        checks = await run.io_bound(backend.system_checks)
        system_box.clear()
        with system_box:
            status.checklist(checks)


def _account_section() -> None:
    ui.label("حساب").classes("text-lg font-bold mt-2")
    with ui.element("div").classes("dx-card p-4 w-full"):
        with ui.row().classes("items-center gap-2"):
            ui.icon("admin_panel_settings" if session.is_admin() else "person")
            ui.label("مدیر کتابخانه" if session.is_admin() else "مهمان (بدون ورود)").classes("font-medium")
        if session.is_admin():
            ui.button("خروج", icon="logout", on_click=lambda: (session.set_admin(False), ui.navigate.to("/"))).props(
                "flat dense color=negative"
            ).classes("mt-2")
        else:
            ui.link("ورود مدیر کتابخانه", "/login").classes("text-sm mt-2").style(f"color:{_brand_ink()}")


def _ai_section() -> None:
    ui.label("هوش مصنوعی").classes("text-lg font-bold mt-2")
    with ui.element("div").classes("dx-card p-4 w-full"):
        with ui.row().classes("items-center gap-2"):
            ui.label("ارائه‌دهندهٔ مدل زبانی").classes("text-sm dx-muted")
            ui.space()
            ui.badge("OpenRouter", color="teal-1").props("text-color=teal-9")
        status.status_line("کلید OpenRouter", bool(os.getenv("OPENROUTER_API_KEY")))


def _ocr_section() -> None:
    ui.label("OCR صفحه‌های اسکن‌شده").classes("text-lg font-bold mt-2")
    with ui.element("div").classes("dx-card p-4 w-full"):
        ui.label(
            "فقط صفحه‌های اسکن‌شده OCR می‌شوند. این انتخاب برای بارگذاری‌های بعدی شما در همین مرورگر به‌کار می‌رود."
        ).classes("text-xs dx-muted mb-2")
        upload.ocr_mode_select()


def _brand_ink() -> str:
    from .. import theme

    return theme.BRAND_INK
