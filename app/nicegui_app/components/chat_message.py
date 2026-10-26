"""Renders one chat message (user or assistant) from the same message-dict
shape the Streamlit UI used internally: {"role", "kind", "content", ...}.

Citations are real ``SourceItem``s returned by ``RAGService`` (source_file,
page, snippet) — nothing here invents a citation or a page number.
"""

from __future__ import annotations

from nicegui import ui

from app.text_helpers import display_name, element_symbol, page_label

from .. import theme


def _escape(text: str) -> str:
    from html import escape

    return escape(text).replace("\n", "<br>")


def user_bubble(text: str) -> None:
    with ui.row().classes("w-full justify-end"):
        ui.html(f'<div class="dx-bubble-user dx-rtl">{_escape(text)}</div>')


def _citation_chip(source: dict) -> None:
    color = theme.tile_color(source["file"])
    page = page_label(source.get("page"))
    label = f"{element_symbol(source['file'])}" + (f" · {page}" if page else "")
    with ui.button(label).props("flat dense no-caps").classes("dx-cite-chip").style(
        f"border-top: 3px solid {color}"
    ):
        with ui.menu().classes("dx-rtl"):
            with ui.card().classes("p-3 max-w-xs"):
                heading = display_name(source["file"])
                if page:
                    heading += f" — صفحهٔ {page}"
                ui.label(heading).classes("font-semibold text-sm")
                snippet = source.get("snippet")
                if snippet:
                    ui.label(f"«{snippet}»").classes("dx-cite-snippet mt-1")
                else:
                    ui.label("متنی برای پیش‌نمایش در دسترس نیست.").classes("text-xs dx-muted mt-1")


def sources_row(sources: list[dict], label: str = "منابع پاسخ") -> None:
    if not sources:
        return
    with ui.column().classes("gap-2 mt-2 dx-rtl"):
        ui.label(label).classes("text-xs font-bold dx-muted uppercase")
        with ui.row().classes("gap-2 flex-wrap"):
            for source in sources:
                _citation_chip(source)


def not_found(answer: str) -> None:
    with ui.element("div").classes("dx-card p-3 dx-rtl").style("border-inline-start: 4px solid #B5305F"):
        ui.label(answer).classes("leading-relaxed")
    ui.label("سؤال را با نام دقیق مفهوم بنویسید یا جست‌وجو را به منبع دیگری محدود کنید.").classes(
        "text-xs dx-muted mt-1 dx-rtl"
    )


def compare_card(summary: str, sections: list[dict]) -> None:
    with ui.element("div").classes("dx-card p-3 dx-rtl mb-2").style(
        f"background:{theme.BRAND_WASH}; border-color:{theme.BRAND_WASH}"
    ):
        ui.label(summary).classes("leading-relaxed")

    with ui.row().classes("w-full gap-3 flex-wrap"):
        for section in sections:
            with ui.element("div").classes("dx-card p-3 flex-1 min-w-[260px] dx-rtl"):
                with ui.row().classes("items-center gap-2 pb-2").style(
                    f"border-bottom: 1px dashed {theme.BRAND_WASH}"
                ):
                    ui.icon("science").classes("dx-brand-text")
                    ui.label(section["title"]).classes("font-bold dx-brand-text")
                ui.label("تعریف").classes("text-xs font-bold dx-muted uppercase mt-2")
                ui.label(section["definition"]).classes("text-sm leading-relaxed")
                ui.label("توضیح").classes("text-xs font-bold dx-muted uppercase mt-2")
                ui.label(section["explanation"]).classes("text-sm leading-relaxed")
                sources_row(section.get("sources", []), label="منابع")


def error_bubble(message: str, detail: str | None = None, on_retry=None) -> None:
    with ui.element("div").classes("dx-rtl"):
        ui.label(message).classes("text-negative")
        with ui.row().classes("gap-2 mt-1"):
            if on_retry:
                ui.button("تلاش دوباره", icon="refresh", on_click=on_retry).props("flat dense color=negative")
            if detail:
                with ui.expansion("جزئیات فنی").classes("text-xs"):
                    ui.label(detail).classes("text-xs font-mono")


def assistant_body(message: dict) -> None:
    kind = message.get("kind", "answer")
    with ui.column().classes("dx-bubble-assistant gap-1"):
        if kind == "answer":
            ui.markdown(message["content"]).classes("dx-rtl")
            sources_row(message.get("sources", []))
        elif kind == "compare":
            compare_card(message["content"], message.get("sections", []))
        elif kind == "not_found":
            not_found(message["content"])
        else:
            error_bubble(message["content"], message.get("detail"))
