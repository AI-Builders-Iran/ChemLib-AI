"""HTML fragments rendered with ``st.markdown(..., unsafe_allow_html=True)``.

Every function returns a single line of HTML with no blank lines and no
leading indentation, because Markdown would otherwise break the block apart.
All text that originates from files or users is escaped.
"""

from __future__ import annotations

from html import escape
from pathlib import Path

from app.text_helpers import (
    display_name,
    element_symbol,
    tile_color_index,
    to_fa_digits,
)

# How many shelf tiles the empty-chat screen shows before summarising the rest.
SHELF_LIMIT = 12

# A small inline "molecule / knowledge-graph" motif for the hero — a benzene
# ring with three substituent bonds. No external asset, no new dependency;
# colours come from the CSS custom properties so it follows the theme.
_HERO_GRAPHIC = (
    '<svg class="dx-hero-graphic" viewBox="0 0 220 200" aria-hidden="true" '
    'xmlns="http://www.w3.org/2000/svg">'
    '<g fill="none" stroke="var(--brand)" stroke-width="1.6" opacity=".55">'
    '<polygon points="110,20 160,50 160,110 110,140 60,110 60,50" />'
    '<line x1="110" y1="140" x2="110" y2="180" />'
    '<line x1="160" y1="110" x2="205" y2="130" />'
    '<line x1="60" y1="110" x2="15" y2="130" />'
    "</g>"
    '<g fill="var(--brand)">'
    '<circle cx="110" cy="20" r="5"/><circle cx="160" cy="50" r="5"/>'
    '<circle cx="160" cy="110" r="5"/><circle cx="110" cy="140" r="5"/>'
    '<circle cx="60" cy="110" r="5"/><circle cx="60" cy="50" r="5"/>'
    "</g>"
    '<g fill="var(--t3)">'
    '<circle cx="110" cy="180" r="6"/><circle cx="205" cy="130" r="6"/><circle cx="15" cy="130" r="6"/>'
    "</g>"
    "</svg>"
)


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


def tile(file_name: str) -> str:
    """Card-sized tile (bigger than mini_tile) — used for the admin document list."""
    return _tile(file_name)


def mini_tile(file_name: str) -> str:
    """Compact tile — kept for any spot that needs the smallest footprint."""
    color = tile_color_index(file_name)
    return (
        f'<div class="dx-tile dx-tile-mini t{color}">'
        f'<span class="dx-sym">{escape(element_symbol(file_name))}</span>'
        f"</div>"
    )


def brand() -> str:
    return (
        '<div class="dx-brand">'
        '<div class="dx-tile dx-tile-brand t5"><span class="dx-sym">Cl</span></div>'
        "<div>"
        '<div class="dx-brand-word"><b>ChemLib</b>-AI</div>'
        '<div class="dx-brand-sub">کتابخانهٔ هوشمند دانشکدهٔ شیمی — پرسش و پاسخ از روی کتاب‌های کتابخانه</div>'
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
        f"{_HERO_GRAPHIC}"
        '<div class="dx-hero-badge">⚗️ ChemLib-AI</div>'
        '<div class="dx-hero-title" role="heading" aria-level="1">از کتاب‌های کتابخانه بپرسید</div>'
        '<p class="dx-hero-text">پاسخ فقط از متن منابع ایندکس‌شده ساخته می‌شود و منبع آن زیر پاسخ نشان داده می‌شود. '
        "اگر منبعی پیدا نشود، پاسخی حدس زده نمی‌شود. "
        "هر پرسش جداگانه جست‌وجو می‌شود؛ نام مفهوم را در خود سؤال بنویسید. "
        "برای مقایسهٔ دو منبع همین‌جا بنویسید، مثلاً: «فلان و بهمان را مقایسه کن».</p>"
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
        f"{_HERO_GRAPHIC}"
        '<div class="dx-hero-badge">⚗️ ChemLib-AI</div>'
        f'<div class="dx-hero-title" role="heading" aria-level="1">{title}</div>'
        '<p class="dx-hero-text">فایل یا پوشهٔ شما فقط در حافظهٔ همین صفحه نگه داشته می‌شود. '
        "در پایگاه دانش کتابخانه ذخیره نمی‌شود و با بستن یا تازه‌کردن صفحه از بین می‌رود. "
        "برای ساختن پاسخ، بخش‌های مرتبط با سؤال به سرویس مدل زبانی (OpenRouter) فرستاده می‌شود.</p>"
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
        '<div class="dx-hero-badge">⚗️ ChemLib-AI</div>'
        '<div class="dx-hero-title" role="heading" aria-level="1">کتابخانه هنوز منبعی ندارد</div>'
        f'<p class="dx-hero-text">{escape(action)}</p>'
        "</div>"
    )


def user_text(text: str) -> str:
    """User message shown literally (no Markdown interpretation)."""
    return f'<div class="dx-user-text">{escape(text).replace(chr(10), "<br>")}</div>'


def compare_section(title: str, definition: str, explanation: str) -> str:
    """One side of a Compare-Sources answer shown in the chat: source name +
    its own definition/explanation, kept visually separate from the other side."""
    return (
        '<div class="dx-compare-section">'
        f'<div class="dx-compare-title">🧪 {escape(title)}</div>'
        '<div class="dx-compare-label">تعریف</div>'
        f'<div class="dx-compare-def">{escape(definition)}</div>'
        '<div class="dx-compare-label">توضیح</div>'
        f'<div class="dx-compare-exp">{escape(explanation)}</div>'
        "</div>"
    )


def compare_summary(text: str) -> str:
    """The overall comparison paragraph, shown above the two per-source cards."""
    return f'<div class="dx-compare-summary">{escape(text)}</div>'


def not_found(answer: str) -> str:
    """Assistant reply when the library has no grounded answer."""
    return (
        f'<div class="dx-miss">{escape(answer)}</div>'
        '<div class="dx-hint">سؤال را با نام دقیق مفهوم بنویسید یا جست‌وجو را به منبع دیگری محدود کنید.</div>'
    )


def doc_card(file_name: str, chunks: int) -> str:
    """Name, file-type badge, status and size of an indexed book (admin list)."""
    ext = Path(file_name).suffix.lstrip(".").upper() or "FILE"
    return (
        '<div class="dx-doc">'
        f'<div class="dx-doc-name">{escape(file_name)}</div>'
        f'<div class="dx-doc-meta">{to_fa_digits(chunks)} بخش ایندکس‌شده</div>'
        '<div class="dx-doc-badges">'
        f'<span class="dx-badge">{escape(ext)}</span>'
        '<span class="dx-badge ok">✓ ایندکس‌شده</span>'
        "</div>"
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
