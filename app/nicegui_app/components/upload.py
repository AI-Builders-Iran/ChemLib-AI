"""Upload zone: drag-and-drop file picker, OCR-mode choice, progress and a
per-file outcome report — wired to the real ingestion pipeline
(``services/backend.py``). No stage is shown that the backend doesn't
actually report (see ``rag.schemas.IngestFileResult``).
"""

from __future__ import annotations

import logging

from nicegui import events, run, ui

from app.text_helpers import ocr_summary, to_fa_digits

from ..services import backend
from ..state import session

logger = logging.getLogger(__name__)


def ocr_mode_select() -> ui.radio:
    """Radio bound to the shared per-tab OCR preference (state/session.py) —
    changing it here or on the Settings page updates the same value, so it
    actually affects the next upload rather than being a disconnected control."""
    radio = ui.radio(backend.OCR_MODE_LABELS, value=session.ocr_mode()).props("inline")
    radio.on_value_change(lambda e: session.set_ocr_mode(e.value))
    if not backend.local_ocr_ready():
        ui.label("OCR محلی نصب نیست: `pip install rapidocr-onnxruntime`").classes("text-xs dx-muted")
    return radio


def outcome_row(result) -> None:
    """One line per IngestFileResult — mirrors the Streamlit outcomes.py logic."""
    icon_by_status = {
        "added": ("check_circle", "positive"),
        "replaced": ("check_circle", "positive"),
        "skipped": ("info", "grey"),
        "empty": ("warning", "warning"),
        "duplicate_name": ("warning", "warning"),
        "failed": ("error", "negative"),
        "error": ("error", "negative"),
    }
    icon, color = icon_by_status.get(result.status, ("info", "grey"))
    with ui.row().classes("items-center gap-2 dx-rtl"):
        ui.icon(icon, color=color)
        ui.label(result.filename).classes("font-medium")
        if result.status in ("added", "replaced"):
            verb = "جایگزین شد" if result.status == "replaced" else "اضافه شد"
            ui.label(f"✅ پردازش کامل شد — {verb}؛ آمادهٔ پرسش و پاسخ.").classes("text-sm text-positive")
        elif result.status == "skipped":
            ui.label("از قبل ایندکس شده بود (رد شد).").classes("text-sm dx-muted")
        elif result.status == "empty":
            ui.label("متنی برای ایندکس استخراج نشد.").classes("text-sm text-orange-700")
        elif result.status == "duplicate_name":
            ui.label(result.detail or "نام تکراری.").classes("text-sm text-orange-700")
        else:
            ui.label(f"❌ پردازش ناموفق بود. دلیل: {result.detail or 'نامشخص'}").classes("text-sm text-negative")
    if result.status in ("added", "replaced"):
        for line in metrics_lines(result):
            ui.label(line).classes("text-xs dx-muted dx-rtl")


# Files being processed right now: (store identity, file name). A second upload of the same
# name into the same store is refused instead of racing the first one.
_IN_FLIGHT: set[tuple[int, str]] = set()

_STAGE_LABELS = {
    "upload": "⏳ در حال بارگذاری…",
    "loading": "⏳ در حال خواندن فایل…",
    "reading": "⏳ استخراج متن: صفحه {cur} از {total}",
    "ocr": "⏳ OCR / تحلیل چیدمان: صفحه {cur} از {total}",
    "chunking": "⏳ ساخت بخش‌ها (chunking)…",
    "embedding": "⏳ تولید embedding: {cur} از {total} بخش",
    "saving": "⏳ ذخیره در پایگاه برداری…",
}


def stage_text(stage: str, current: int, total: int) -> str:
    template = _STAGE_LABELS.get(stage, "⏳ در حال پردازش…")
    return template.format(cur=to_fa_digits(current), total=to_fa_digits(total))


def stage_fraction(stage: str, current: int, total: int) -> float | None:
    """Real progress only: page or chunk counts when the backend reports them, else None
    (the bar then stays indeterminate instead of showing a made-up percentage)."""
    if stage in ("reading", "ocr", "embedding") and total > 0:
        return min(1.0, current / total)
    return None


def metrics_lines(result) -> list[str]:
    """Summary lines built only from values the pipeline measured (zeros are not shown)."""
    lines = [f"فایل: {result.filename}"]
    if result.pages:
        lines.append(f"صفحات: {to_fa_digits(result.pages)}")
    if result.text_layer_pages:
        lines.append(f"صفحات با متن دیجیتال: {to_fa_digits(result.text_layer_pages)}")
    if result.ocr_pages:
        lines.append(f"صفحات OCR: {to_fa_digits(sum(result.ocr_pages.values()))} ({ocr_summary(result.ocr_pages)})")
    if result.skipped_figure_pages or result.figure_regions_skipped:
        skipped = result.skipped_figure_pages + result.figure_regions_skipped
        lines.append(f"شکل‌های ردشده: {to_fa_digits(skipped)}")
    if result.tables:
        lines.append(f"جدول‌های پردازش‌شده: {to_fa_digits(result.tables)}")
    if result.failed_pages or result.unread_pages:
        lines.append(f"صفحات ناموفق/ناخوانده: {to_fa_digits(max(result.failed_pages, result.unread_pages))}")
    lines.append(f"بخش‌های ایجادشده: {to_fa_digits(result.chunks)}")
    if result.embeddings:
        lines.append(f"Embeddingهای تولیدشده: {to_fa_digits(result.embeddings)}")
    if result.seconds:
        lines.append(f"زمان پردازش: {result.seconds:.1f} ثانیه")
    return lines


def upload_zone(*, store, on_done=None) -> None:
    """A drag-and-drop zone that ingests PDF/DOCX/TXT/ZIP into ``store``
    (``None`` means the shared library; pass a private ``SessionVectorStore``
    for the per-tab "my documents" mode)."""
    ocr_radio = ocr_mode_select()
    store_key = id(store) if store is not None else 0

    # Progress is written by the worker thread and read by a UI timer: NiceGUI elements are
    # only touched from the event loop.
    state = {"stage": "upload", "current": 0, "total": 0, "file": "", "busy": 0}

    def on_stage(stage: str, current: int, total: int) -> None:  # runs in the worker thread
        state.update(stage=stage, current=current, total=total)

    status_box = ui.column().classes("w-full gap-1 mt-2")
    status_box.set_visibility(False)
    with status_box:
        status_label = ui.label("").classes("text-sm dx-rtl")
        progress = ui.linear_progress(value=0, show_value=False).props("instant-feedback")
    results_box = ui.column().classes("w-full gap-1 mt-2")

    def refresh_status() -> None:
        if not state["busy"]:
            return
        status_label.set_text(f"{state['file']}: {stage_text(state['stage'], state['current'], state['total'])}")
        fraction = stage_fraction(state["stage"], state["current"], state["total"])
        if fraction is None:
            progress.props("indeterminate")
        else:
            progress.props(remove="indeterminate")
            progress.set_value(fraction)

    timer = ui.timer(0.5, refresh_status, active=True)

    async def handle_upload(e: events.UploadEventArguments) -> None:
        # NiceGUI >= 3: the file is ``e.file`` (name / content_type / async read()); the old
        # ``e.content`` / ``e.name`` attributes no longer exist.
        filename = e.file.name
        key = (store_key, filename)
        if key in _IN_FLIGHT:
            ui.notify(f"«{filename}» هم‌اکنون در حال پردازش است.", type="warning")
            return

        _IN_FLIGHT.add(key)
        results_box.clear()
        state.update(stage="upload", current=0, total=0, file=filename)
        state["busy"] += 1
        status_box.set_visibility(True)
        refresh_status()
        try:
            try:
                data = await e.file.read()
            except Exception as exc:  # noqa: BLE001 - the temp upload file vanished, etc.
                logger.exception("Could not read the uploaded file %s", filename)
                _show_failure(results_box, filename, f"خواندن فایل بارگذاری‌شده ممکن نشد: {exc}")
                return

            state.update(stage="loading")
            try:
                # Real work here: OCR, embedding, vector-store writes - genuinely slow, and the
                # first call in a process also pays for loading the embedding model. A worker
                # thread keeps the UI responsive for every connected tab.
                if filename.lower().endswith(".zip"):
                    results = await run.io_bound(
                        backend.ingest_zip, filename, data, True,
                        store=store, ocr_mode=ocr_radio.value, on_stage=on_stage,
                    )
                else:
                    result = await run.io_bound(
                        backend.ingest_upload, filename, data, True,
                        store=store, ocr_mode=ocr_radio.value, on_stage=on_stage,
                    )
                    results = [result]
            except Exception as exc:  # noqa: BLE001
                logger.exception("Processing failed for %s", filename)
                _show_failure(results_box, filename, str(exc))
                return
            finally:
                data = None  # release the upload bytes

            # ``run.io_bound`` returns None (instead of a result) when the call was cancelled or
            # the app is shutting down; never treat that as a finished ingestion.
            if not results or any(r is None for r in results):
                logger.warning("Processing of %s was cancelled before it finished", filename)
                _show_failure(results_box, filename, "پردازش پیش از پایان لغو شد.")
                return
        finally:
            _IN_FLIGHT.discard(key)
            state["busy"] -= 1
            if not state["busy"]:
                status_box.set_visibility(False)

        with results_box:
            for result in results:
                outcome_row(result)

        ok = [r for r in results if r.status in ("added", "replaced")]
        if ok:
            ui.notify(f"✅ پردازش کامل شد: {to_fa_digits(len(ok))} فایل آمادهٔ پرسش و پاسخ است.", type="positive")
        elif any(r.status == "failed" for r in results):
            ui.notify(f"❌ پردازش «{filename}» ناموفق بود.", type="negative")
        if on_done:
            # ``on_done`` reloads the page so the document list/selectors pick up the new file.
            # Reloading immediately would erase the result shown above the moment it appears, so
            # the user sees the outcome first and refreshes when ready.
            with results_box:
                ui.button(
                    "به‌روزرسانی فهرست اسناد", icon="refresh", on_click=lambda: on_done(results)
                ).props("flat dense color=primary")

    ui.upload(
        label="فایل را اینجا رها کنید یا انتخاب کنید (PDF، DOCX، TXT یا ZIP)",
        auto_upload=True,
        on_upload=handle_upload,
    ).props('accept=".pdf,.docx,.txt,.zip"').classes("w-full")


def _show_failure(box, filename: str, reason: str) -> None:
    with box:
        with ui.row().classes("items-center gap-2 dx-rtl"):
            ui.icon("error", color="negative")
            ui.label(f"❌ پردازش ناموفق بود: {filename}").classes("font-medium")
        ui.label(f"دلیل: {reason}").classes("text-sm text-negative dx-rtl")
    ui.notify(f"❌ پردازش «{filename}» ناموفق بود.", type="negative")
