"""HTML fragments rendered with ``st.markdown(..., unsafe_allow_html=True)``.

Every function returns a single line of HTML with no blank lines and no
leading indentation, because Markdown would otherwise break the block apart.
All text that originates from files or users is escaped.
"""

from __future__ import annotations

from html import escape

from .helpers import (
    display_name,
    element_symbol,
    page_label,
    tile_color_index,
    to_fa_digits,
)

# How many shelf tiles the empty-chat screen shows before summarising the rest.
SHELF_LIMIT = 12


def _tile(file_name: str, page_no: str = "", *, large: bool = False, color_key: str | None = None) -> str:
    """One 'periodic-table' cell: colour = book, corner number = page, letters = symbol."""
    color = tile_color_index(color_key or file_name)
    size = " dx-tile-lg" if large else ""
    number = f'<span class="dx-no">{escape(page_no)}</span>' if page_no else ""
    label = f"{file_name}، صفحهٔ {page_no}" if page_no else file_name
    return (
        f'<div class="dx-tile t{color}{size}" title="{escape(label, quote=True)}">'
        f"{number}"
        f'<span class="dx-sym">{escape(element_symbol(file_name))}</span>'
        f'<span class="dx-nm">{escape(display_name(file_name))}</span>'
        f"</div>"
    )


def mini_tile(file_name: str) -> str:
    """Compact tile used in the admin document list."""
    color = tile_color_index(file_name)
    return (
        f'<div class="dx-tile dx-tile-mini t{color}">'
        f'<span class="dx-sym">{escape(element_symbol(file_name))}</span>'
        f"</div>"
    )


def brand() -> str:
    return (
        '<div class="dx-brand">'
        '<div class="dx-tile dx-tile-brand t4"><span class="dx-sym">شی</span></div>'
        "<div>"
        '<div class="dx-brand-title">کتابخانهٔ دانشکدهٔ شیمی</div>'
        '<div class="dx-brand-sub">پرسش و پاسخ از روی کتاب‌های کتابخانه</div>'
        "</div>"
        "</div>"
    )


def hero(documents: list[tuple[str, str]]) -> str:
    """Empty-chat screen: what this is, plus the real shelf of indexed books.

    ``documents`` is a list of ``(document_id, file_name)``.
    """
    shown = documents[:SHELF_LIMIT]
    tiles = "".join(_tile(name, large=True, color_key=name) for _, name in shown)
    rest = len(documents) - len(shown)
    more = f'<div class="dx-more">و {to_fa_digits(rest)} منبع دیگر</div>' if rest > 0 else ""

    return (
        '<div class="dx-hero">'
        '<div class="dx-hero-title" role="heading" aria-level="1">از کتاب‌های کتابخانه بپرسید</div>'
        '<p class="dx-hero-text">پاسخ فقط از متن منابع ایندکس‌شده ساخته می‌شود و منبع آن زیر پاسخ نشان داده می‌شود. '
        "اگر منبعی پیدا نشود، پاسخی حدس زده نمی‌شود. "
        "هر پرسش جداگانه جست‌وجو می‌شود؛ نام مفهوم را در خود سؤال بنویسید.</p>"
        '<div class="dx-shelf-label">منابع در دسترس</div>'
        f'<div class="dx-tiles">{tiles}{more}</div>'
        "</div>"
    )


def private_hero(documents: list[tuple[str, str]]) -> str:
    """Empty-chat screen for a user's private, temporary documents."""
    tiles = "".join(_tile(name, large=True, color_key=name) for _, name in documents[:SHELF_LIMIT])
    if documents:
        title = "از سندهای خودتان بپرسید"
        shelf = (
            '<div class="dx-shelf-label">سندهای بارگذاری‌شده</div>'
            f'<div class="dx-tiles">{tiles}</div>'
        )
    else:
        title = "سند خودتان را بارگذاری کنید"
        shelf = ""

    return (
        '<div class="dx-hero">'
        f'<div class="dx-hero-title" role="heading" aria-level="1">{title}</div>'
        '<p class="dx-hero-text">فایل یا پوشهٔ شما فقط در حافظهٔ همین صفحه نگه داشته می‌شود. '
        "در پایگاه دانش کتابخانه ذخیره نمی‌شود و با بستن یا تازه‌کردن صفحه از بین می‌رود. "
        "برای ساختن پاسخ، بخش‌های مرتبط با سؤال به سرویس مدل زبانی (Gemini یا OpenRouter) فرستاده می‌شود.</p>"
        f"{shelf}"
        "</div>"
    )


def empty_library(is_admin: bool) -> str:
    action = (
        "از بخش «مدیریت منابع» اولین کتاب را اضافه کنید. تا آن موقع می‌توانید از «سند من» استفاده کنید."
        if is_admin
        else "مدیر کتابخانه باید ابتدا کتاب‌ها را اضافه کند. تا آن موقع می‌توانید فایل خودتان را در «سند من» بارگذاری کنید."
    )
    return (
        '<div class="dx-hero">'
        '<div class="dx-hero-title" role="heading" aria-level="1">کتابخانه هنوز منبعی ندارد</div>'
        f'<p class="dx-hero-text">{escape(action)}</p>'
        "</div>"
    )


def sources_row(sources: list[dict]) -> str:
    """Tiles under an answer. ``sources`` items: ``{"file": str, "page": int | None}``."""
    if not sources:
        return ""
    tiles = "".join(_tile(s["file"], page_label(s.get("page"))) for s in sources)
    return (
        '<div class="dx-sources">'
        '<div class="dx-shelf-label">منابع پاسخ</div>'
        f'<div class="dx-tiles">{tiles}</div>'
        "</div>"
    )


def user_text(text: str) -> str:
    """User message shown literally (no Markdown interpretation)."""
    return f'<div class="dx-user-text">{escape(text).replace(chr(10), "<br>")}</div>'


def not_found(answer: str) -> str:
    """Assistant reply when the library has no grounded answer."""
    return (
        f'<div class="dx-miss">{escape(answer)}</div>'
        '<div class="dx-hint">سؤال را با نام دقیق مفهوم بنویسید یا جست‌وجو را به منبع دیگری محدود کنید.</div>'
    )


def doc_line(file_name: str, chunks: int) -> str:
    """Name and size of an indexed book (admin list); the name is escaped."""
    return (
        '<div class="dx-doc">'
        f'<div class="dx-doc-name">{escape(file_name)}</div>'
        f'<div class="dx-doc-meta">{to_fa_digits(chunks)} بخش</div>'
        "</div>"
    )


def stat(label: str, value: int) -> str:
    return (
        '<div class="dx-stat">'
        f'<div class="dx-stat-value">{to_fa_digits(value)}</div>'
        f'<div class="dx-stat-label">{escape(label)}</div>'
        "</div>"
    )


def stats_row(items: list[tuple[str, int]]) -> str:
    return '<div class="dx-stats">' + "".join(stat(label, value) for label, value in items) + "</div>"


def status_pills(checks: list[tuple[str, bool]]) -> str:
    """Environment checklist for the admin: green when ready, amber when not."""
    pills = "".join(
        f'<span class="dx-pill {"ok" if ok else "warn"}">'
        f'{"آماده" if ok else "تنظیم نشده"}: {escape(label)}</span>'
        for label, ok in checks
    )
    return f'<div class="dx-pills">{pills}</div>'


def section_title(text: str) -> str:
    return f'<div class="dx-section-title" role="heading" aria-level="2">{escape(text)}</div>'


def footer_note() -> str:
    return (
        '<div class="dx-foot">پاسخ‌ها از متن کتاب‌های ایندکس‌شده ساخته می‌شوند. '
        "برای کارهای مهم، خود منبع را بررسی کنید.</div>"
    )
