"""Renders a ``SummaryResponse`` (title, overview, key points, key terms) with copy / download.

Everything shown comes from the response: nothing is invented here. Numbers about coverage are
shown only when the backend reports the summary is partial.
"""

from __future__ import annotations

from nicegui import ui

from app.text_helpers import summary_download_name, summary_to_markdown, to_fa_digits

from .. import theme


def render(summary) -> None:
    markdown = summary_to_markdown(summary)

    with ui.element("div").classes("dx-card p-4 w-full dx-rtl gap-2"):
        with ui.row().classes("items-start justify-between w-full no-wrap gap-2"):
            ui.label(summary.title).classes("text-xl font-bold flex-1").style("word-break: break-word;")
            with ui.row().classes("gap-1 no-wrap"):
                ui.button(icon="content_copy", on_click=lambda: _copy(markdown)).props(
                    "flat round dense"
                ).tooltip("کپی خلاصه")
                ui.button(
                    icon="download",
                    on_click=lambda: ui.download.content(
                        markdown.encode("utf-8"), summary_download_name(summary.source_file), "text/markdown"
                    ),
                ).props("flat round dense").tooltip("دانلود خلاصه (Markdown)")

        with ui.row().classes("gap-2 items-center flex-wrap"):
            ui.badge(summary.source_file, color="grey-3").props("text-color=grey-9")
            if summary.strategy == "map_reduce":
                ui.badge(
                    f"سند بلند: {to_fa_digits(summary.sections_summarized)} از "
                    f"{to_fa_digits(summary.sections_total)} بخش",
                    color="teal-1",
                ).props("text-color=teal-9")
            if summary.cached:
                ui.badge("از حافظهٔ موقت (بدون فراخوانی مدل)", color="grey-3").props("text-color=grey-9")

        if summary.coverage < 1.0 or summary.warnings:
            _partial_notice(summary)

        ui.label("خلاصه").classes("text-xs font-bold dx-muted uppercase mt-2")
        ui.label(summary.overview).classes("leading-loose").style("white-space: pre-wrap;")

        if summary.key_points:
            ui.label("نکات کلیدی").classes("text-xs font-bold dx-muted uppercase mt-3")
            with ui.column().classes("gap-1"):
                for point in summary.key_points:
                    with ui.row().classes("items-start gap-2 no-wrap"):
                        ui.icon("check_circle", size="18px").classes("mt-1").style(f"color:{theme.BRAND}")
                        ui.label(point).classes("leading-relaxed")

        if summary.key_terms:
            ui.label("اصطلاحات مهم").classes("text-xs font-bold dx-muted uppercase mt-3")
            with ui.column().classes("gap-1"):
                for term in summary.key_terms:
                    ui.label(f"• {term}").classes("leading-relaxed")


def _partial_notice(summary) -> None:
    with ui.element("div").classes("dx-card p-3").style(f"border-inline-start:4px solid {theme.WARN}"):
        if summary.coverage < 1.0:
            ui.label(
                f"این خلاصه تنها حدود {to_fa_digits(round(summary.coverage * 100))}٪ از متن سند را پوشش می‌دهد."
            ).classes("text-sm")
        if summary.warnings:
            with ui.expansion("جزئیات فنی").classes("text-xs"):
                for warning in summary.warnings:
                    ui.label(warning).classes("text-xs font-mono").style("direction:ltr; text-align:left;")


def _copy(text: str) -> None:
    ui.clipboard.write(text)
    ui.notify("خلاصه کپی شد.", type="positive")
