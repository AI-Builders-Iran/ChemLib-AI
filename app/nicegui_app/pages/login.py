"""Admin login.

The backend has no user-account system — ``app/auth.py`` checks one shared
``ADMIN_PASSWORD`` from the environment. This page reflects exactly that: a
password field, nothing else. No email/username field, no "forgot password"
link — the backend doesn't have either, and the brief says not to invent
functionality that isn't there.
"""

from __future__ import annotations

from nicegui import ui

from app import auth

from .. import theme
from ..state import session


@ui.page("/login")
def login_page() -> None:
    theme.apply()

    with ui.column().classes("w-full h-screen items-center justify-center dx-rtl"):
        with ui.column().classes("dx-card p-8 gap-3 items-stretch").style("width: 360px;"):
            with ui.row().classes("items-center gap-2 justify-center"):
                ui.icon("science").classes("text-3xl").style(f"color:{theme.BRAND}")
                ui.label("ChemLib-AI").classes("text-xl font-bold")
            ui.label("دستیار هوشمند کتابخانهٔ شیمی").classes("text-sm dx-muted text-center")

            ui.separator().classes("my-2")

            if session.is_admin():
                ui.label("شما وارد شده‌اید.").classes("text-sm text-center")
                ui.button("رفتن به داشبورد", on_click=lambda: ui.navigate.to("/")).props(
                    "color=primary unelevated"
                ).classes("w-full")
                return

            if not auth.admin_configured():
                ui.label(
                    "ورود مدیر غیرفعال است. برای فعال‌سازی، ADMIN_PASSWORD را در فایل .env تنظیم و "
                    "برنامه را دوباره اجرا کنید."
                ).classes("text-sm text-orange-700")
                ui.button("بازگشت به داشبورد", on_click=lambda: ui.navigate.to("/")).props("flat").classes(
                    "w-full"
                )
                return

            ui.label("ورود مدیر کتابخانه").classes("font-semibold")
            password = ui.input("گذرواژه", password=True, password_toggle_button=True).classes("w-full")
            error_label = ui.label("").classes("text-sm text-negative")

            def try_login() -> None:
                if auth.verify_admin_password(password.value or ""):
                    session.set_admin(True)
                    ui.navigate.to("/")
                else:
                    error_label.set_text("گذرواژه نادرست است.")

            password.on("keydown.enter", try_login)
            ui.button("ورود", on_click=try_login).props("color=primary unelevated").classes("w-full")
            ui.link("ادامه بدون ورود (گفتگوی عادی)", "/").classes("text-xs text-center").style(
                f"color:{theme.MUTED}"
            )
